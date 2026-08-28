"""Exportación del informe a PDF."""

import uuid
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete

from app.core.database import SessionLocal
from app.core.security import create_access_token
from app.main import app
from app.models.analysis import Analysis, Dimension, Finding
from app.models.repository import Repository
from app.models.user import User

client = TestClient(app)

TEST_EMAIL = "informe-pdf@example.com"


def _limpiar() -> None:
    db = SessionLocal()
    try:
        db.execute(delete(User).where(User.email == TEST_EMAIL))
        db.commit()
    finally:
        db.close()


@pytest.fixture(autouse=True)
def _clean():
    _limpiar()
    yield
    _limpiar()


@pytest.fixture
def analisis_completo():
    db = SessionLocal()
    try:
        user = User(id=uuid.uuid4(), email=TEST_EMAIL, github_id=950000001)
        db.add(user)
        db.flush()
        repo = Repository(
            id=uuid.uuid4(), user_id=user.id, github_id=7770001, name="demo",
            full_name="alguien/demo", default_branch="main", is_private=False,
        )
        db.add(repo)
        db.flush()
        analysis = Analysis(
            id=uuid.uuid4(), user_id=user.id, repository_id=repo.id,
            analysis_type="repository", status="completed",
            overall_score=67.8, confidence_level=100.0,
            commit_hash="c" * 40, commit_message="mensaje del commit", branch="main",
            completed_at=datetime.now(timezone.utc),
        )
        db.add(analysis)
        db.flush()
        for nombre, score, peso in [
            ("security", 62.0, 0.20),
            ("reliability", 46.0, 0.20),
            ("maintainability", 49.0, 0.20),
        ]:
            db.add(Dimension(id=uuid.uuid4(), analysis_id=analysis.id, name=nombre,
                             score=score, weight=peso, raw_metrics={}))
        db.add(Finding(
            id=uuid.uuid4(), analysis_id=analysis.id, type="security", severity="critical",
            title="Secreto expuesto en <config> & credenciales",
            description="Una descripción con caracteres especiales: <script> & \"comillas\".",
            file_path="src/config.py:12", recommendation="Rota la credencial.",
        ))
        db.add(Finding(
            id=uuid.uuid4(), analysis_id=analysis.id, type="test_coverage", severity="medium",
            title="Pocos tests", description="d", file_path=None, recommendation=None,
        ))
        db.commit()
        return user.id, analysis.id
    finally:
        db.close()


def test_report_returns_a_real_pdf(analisis_completo):
    user_id, analysis_id = analisis_completo
    r = client.get(
        f"/api/analyses/{analysis_id}/report.pdf",
        headers={"Authorization": f"Bearer {create_access_token(user_id)}"},
    )

    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    # Cabecera magica de un PDF valido, no solo bytes cualesquiera.
    assert r.content.startswith(b"%PDF-")
    assert r.content.rstrip().endswith(b"%%EOF")
    assert len(r.content) > 2000


def test_report_is_offered_as_a_download_with_a_meaningful_name(analisis_completo):
    user_id, analysis_id = analisis_completo
    r = client.get(
        f"/api/analyses/{analysis_id}/report.pdf",
        headers={"Authorization": f"Bearer {create_access_token(user_id)}"},
    )
    disposicion = r.headers["content-disposition"]
    assert disposicion.startswith("attachment;")
    assert "qalitiradar-demo-" in disposicion
    assert disposicion.endswith('.pdf"')


def test_special_characters_do_not_corrupt_the_pdf(analisis_completo):
    """Un hallazgo con <, > o & no debe romper el marcado interno."""
    user_id, analysis_id = analisis_completo
    r = client.get(
        f"/api/analyses/{analysis_id}/report.pdf",
        headers={"Authorization": f"Bearer {create_access_token(user_id)}"},
    )
    assert r.status_code == 200
    assert r.content.startswith(b"%PDF-")


def test_report_of_an_unfinished_analysis_is_rejected():
    db = SessionLocal()
    try:
        user = User(id=uuid.uuid4(), email=TEST_EMAIL, github_id=950000002)
        db.add(user)
        db.flush()
        repo = Repository(id=uuid.uuid4(), user_id=user.id, github_id=7770002, name="d",
                          full_name="a/d", default_branch="main", is_private=False)
        db.add(repo)
        db.flush()
        analysis = Analysis(id=uuid.uuid4(), user_id=user.id, repository_id=repo.id,
                            analysis_type="repository", status="running")
        db.add(analysis)
        db.commit()
        user_id, analysis_id = user.id, analysis.id
    finally:
        db.close()

    r = client.get(
        f"/api/analyses/{analysis_id}/report.pdf",
        headers={"Authorization": f"Bearer {create_access_token(user_id)}"},
    )
    assert r.status_code == 400


def test_report_of_another_users_analysis_returns_404(analisis_completo):
    _, analysis_id = analisis_completo
    otro = SessionLocal()
    try:
        intruso = User(id=uuid.uuid4(), email="intruso-pdf@example.com", github_id=950000099)
        otro.add(intruso)
        otro.commit()
        intruso_id = intruso.id
    finally:
        otro.close()
    try:
        r = client.get(
            f"/api/analyses/{analysis_id}/report.pdf",
            headers={"Authorization": f"Bearer {create_access_token(intruso_id)}"},
        )
        assert r.status_code == 404
    finally:
        db = SessionLocal()
        db.execute(delete(User).where(User.id == intruso_id))
        db.commit()
        db.close()


def test_report_without_a_token_is_rejected(analisis_completo):
    _, analysis_id = analisis_completo
    assert client.get(f"/api/analyses/{analysis_id}/report.pdf").status_code == 401
