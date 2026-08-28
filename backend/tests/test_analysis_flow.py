import shutil
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from app.core.database import SessionLocal
from app.core.security import create_access_token
from app.main import app
from app.models.analysis import Analysis, Dimension, Finding
from app.models.repository import Repository
from app.models.user import User

client = TestClient(app)

TEST_EMAIL = "analisis@example.com"
TEST_GITHUB_ID = 910000042

git_available = pytest.mark.skipif(shutil.which("git") is None, reason="git no disponible")


def _delete_test_user() -> None:
    db = SessionLocal()
    try:
        db.execute(delete(User).where(User.email == TEST_EMAIL))
        db.commit()
    finally:
        db.close()


@pytest.fixture(autouse=True)
def _clean():
    # Se limpia antes y despues para que la suite sea repetible aunque una
    # ejecucion anterior se interrumpiera a medias.
    _delete_test_user()
    yield
    _delete_test_user()


@pytest.fixture
def user_with_repo():
    db = SessionLocal()
    try:
        user = User(id=uuid.uuid4(), email=TEST_EMAIL, github_id=TEST_GITHUB_ID)
        db.add(user)
        db.flush()
        repo = Repository(
            id=uuid.uuid4(),
            user_id=user.id,
            github_id=1296269,
            name="Hello-World",
            full_name="octocat/Hello-World",
            default_branch="master",
            is_private=False,
        )
        db.add(repo)
        db.commit()
        return user.id, repo.id
    finally:
        db.close()


def test_analyze_endpoint_queues_an_analysis(user_with_repo, monkeypatch):
    user_id, repo_id = user_with_repo
    queued = {}
    from app.api import repositories as repositories_module

    monkeypatch.setattr(
        repositories_module,
        "queue_repository_analysis",
        lambda analysis_id: queued.setdefault("id", analysis_id),
    )

    response = client.post(
        f"/api/repositories/{repo_id}/analyze",
        headers={"Authorization": f"Bearer {create_access_token(user_id)}"},
    )

    assert response.status_code == 202
    analysis_id = response.json()["analysis_id"]
    assert queued["id"] == analysis_id

    db = SessionLocal()
    try:
        analysis = db.get(Analysis, uuid.UUID(analysis_id))
        assert analysis.status == "pending"
        assert analysis.analysis_type == "repository"
    finally:
        db.close()


def test_analyze_rejects_a_repository_of_another_user(user_with_repo):
    _, repo_id = user_with_repo
    response = client.post(
        f"/api/repositories/{repo_id}/analyze",
        headers={"Authorization": f"Bearer {create_access_token(uuid.uuid4())}"},
    )
    # 401 porque el usuario del token no existe; nunca 200.
    assert response.status_code in (401, 404)


def test_analyze_without_token_is_rejected(user_with_repo):
    _, repo_id = user_with_repo
    assert client.post(f"/api/repositories/{repo_id}/analyze").status_code == 401


@git_available
def test_full_pipeline_produces_a_real_score(user_with_repo):
    """Corre el pipeline completo contra un repositorio publico real."""
    from app.services.analysis_service import run_repository_analysis

    user_id, repo_id = user_with_repo
    db = SessionLocal()
    try:
        analysis = Analysis(
            id=uuid.uuid4(),
            user_id=user_id,
            repository_id=repo_id,
            analysis_type="repository",
            status="pending",
        )
        db.add(analysis)
        db.commit()
        analysis_id = analysis.id
    finally:
        db.close()

    run_repository_analysis(str(analysis_id))

    db = SessionLocal()
    try:
        analysis = db.get(Analysis, analysis_id)
        assert analysis.status == "completed", f"estado {analysis.status}: {analysis.error_message}"
        assert analysis.overall_score is not None
        assert 0 <= float(analysis.overall_score) <= 100
        assert len(analysis.commit_hash) == 40
        assert analysis.raw_data

        dimensions = db.scalars(select(Dimension).where(Dimension.analysis_id == analysis_id)).all()
        assert {d.name for d in dimensions} == {
            "maintainability",
            "functional_suitability",
            "reliability",
            "security",
            "portability",
            "project_activity",
        }
        # Cada dimension se guarda una sola vez aunque varios analizadores la
        # alimenten (estructura y calidad de codigo aportan ambos a
        # mantenibilidad).
        assert len(dimensions) == len({d.name for d in dimensions})

        findings = db.scalars(select(Finding).where(Finding.analysis_id == analysis_id)).all()
        # Hello-World no tiene tests ni licencia: los hallazgos son reales.
        assert len(findings) > 0
    finally:
        db.close()


def test_failed_analysis_is_marked_failed_not_left_pending(user_with_repo, monkeypatch):
    from app.services import analysis_service

    user_id, repo_id = user_with_repo

    def _explode(*args, **kwargs):
        raise RuntimeError("fallo simulado en C:\\Users\\alguien\\AppData\\Local\\Temp\\qaliti-clone-x")

    monkeypatch.setattr(analysis_service, "clone_repository", _explode)

    db = SessionLocal()
    try:
        analysis = Analysis(
            id=uuid.uuid4(),
            user_id=user_id,
            repository_id=repo_id,
            analysis_type="repository",
            status="pending",
        )
        db.add(analysis)
        db.commit()
        analysis_id = analysis.id
    finally:
        db.close()

    analysis_service.run_repository_analysis(str(analysis_id))

    db = SessionLocal()
    try:
        analysis = db.get(Analysis, analysis_id)
        assert analysis.status == "failed"
        assert analysis.error_message
        # El mensaje no debe filtrar rutas internas del servidor.
        assert "qaliti-clone-" not in analysis.error_message
        assert "Temp" not in analysis.error_message
    finally:
        db.close()


@git_available
def test_get_analysis_returns_the_result(user_with_repo):
    from app.services.analysis_service import run_repository_analysis

    user_id, repo_id = user_with_repo
    db = SessionLocal()
    try:
        analysis = Analysis(
            id=uuid.uuid4(),
            user_id=user_id,
            repository_id=repo_id,
            analysis_type="repository",
            status="pending",
        )
        db.add(analysis)
        db.commit()
        analysis_id = analysis.id
    finally:
        db.close()

    run_repository_analysis(str(analysis_id))

    response = client.get(
        f"/api/analyses/{analysis_id}",
        headers={"Authorization": f"Bearer {create_access_token(user_id)}"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "completed"
    assert 0 <= body["overall_score"] <= 100
    assert len(body["dimensions"]) == 6
    assert body["findings"]
    # Los hallazgos llegan ordenados por gravedad, lo mas grave primero.
    orden = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}
    severidades = [orden[f["severity"]] for f in body["findings"]]
    assert severidades == sorted(severidades)


def test_get_analysis_of_another_user_returns_404(user_with_repo):
    user_id, repo_id = user_with_repo
    db = SessionLocal()
    try:
        analysis = Analysis(
            id=uuid.uuid4(),
            user_id=user_id,
            repository_id=repo_id,
            analysis_type="repository",
            status="pending",
        )
        db.add(analysis)
        db.commit()
        analysis_id = analysis.id
    finally:
        db.close()

    otro = SessionLocal()
    try:
        intruso = User(id=uuid.uuid4(), email="intruso-analisis@example.com", github_id=910000099)
        otro.add(intruso)
        otro.commit()
        intruso_id = intruso.id
    finally:
        otro.close()

    try:
        response = client.get(
            f"/api/analyses/{analysis_id}",
            headers={"Authorization": f"Bearer {create_access_token(intruso_id)}"},
        )
        assert response.status_code == 404
    finally:
        limpieza = SessionLocal()
        try:
            limpieza.execute(delete(User).where(User.id == intruso_id))
            limpieza.commit()
        finally:
            limpieza.close()
