"""Histórico, progreso y comparación entre análisis."""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete

from app.core.database import SessionLocal
from app.core.security import create_access_token
from app.main import app
from app.models.analysis import Analysis, Dimension, Finding
from app.models.repository import Repository
from app.models.user import User
from app.services.comparison_service import compare_analyses, find_previous_analysis
from app.services.summary_service import build_summary

client = TestClient(app)

TEST_EMAIL = "historico@example.com"


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
def repo_con_dos_analisis():
    """Dos análisis completados con dimensiones y hallazgos distintos."""
    db = SessionLocal()
    try:
        user = User(id=uuid.uuid4(), email=TEST_EMAIL, github_id=930000001)
        db.add(user)
        db.flush()
        repo = Repository(
            id=uuid.uuid4(), user_id=user.id, github_id=5551234,
            name="demo", full_name="alguien/demo", default_branch="main", is_private=False,
        )
        db.add(repo)
        db.flush()

        base = datetime.now(timezone.utc) - timedelta(days=10)
        viejo = Analysis(
            id=uuid.uuid4(), user_id=user.id, repository_id=repo.id,
            analysis_type="repository", status="completed", overall_score=60.0,
            commit_hash="a" * 40, commit_message="antes", created_at=base,
        )
        nuevo = Analysis(
            id=uuid.uuid4(), user_id=user.id, repository_id=repo.id,
            analysis_type="repository", status="completed", overall_score=68.0,
            commit_hash="b" * 40, commit_message="despues", created_at=base + timedelta(days=10),
        )
        db.add_all([viejo, nuevo])
        db.flush()

        # Fiabilidad sube, seguridad baja, mantenibilidad no cambia.
        for analysis, valores in ((viejo, {"reliability": 34, "security": 66, "maintainability": 49}),
                                  (nuevo, {"reliability": 46, "security": 62, "maintainability": 49})):
            for nombre, score in valores.items():
                db.add(Dimension(id=uuid.uuid4(), analysis_id=analysis.id, name=nombre,
                                 score=score, weight=0.2, raw_metrics={}))

        # Un hallazgo se resuelve y aparece otro nuevo.
        db.add(Finding(id=uuid.uuid4(), analysis_id=viejo.id, type="test_coverage",
                       severity="high", title="El proyecto no tiene tests", description="d"))
        db.add(Finding(id=uuid.uuid4(), analysis_id=nuevo.id, type="dependency",
                       severity="high", title="Dependencia vulnerable: foo 1.0.0", description="d"))

        db.commit()
        return user.id, repo.id, viejo.id, nuevo.id
    finally:
        db.close()


def test_timeline_lists_analyses_newest_first_with_deltas(repo_con_dos_analisis):
    user_id, repo_id, _, _ = repo_con_dos_analisis
    r = client.get(
        f"/api/repositories/{repo_id}/timeline",
        headers={"Authorization": f"Bearer {create_access_token(user_id)}"},
    )
    assert r.status_code == 200
    cuerpo = r.json()
    assert len(cuerpo) == 2
    assert cuerpo[0]["overall_score"] == 68.0  # el mas reciente primero
    assert cuerpo[0]["delta"] == 8.0
    assert cuerpo[1]["delta"] is None  # el primero no tiene con que comparar


def test_progress_reports_best_and_total_change(repo_con_dos_analisis):
    user_id, repo_id, _, _ = repo_con_dos_analisis
    r = client.get(
        f"/api/repositories/{repo_id}/progress",
        headers={"Authorization": f"Bearer {create_access_token(user_id)}"},
    )
    assert r.status_code == 200
    p = r.json()
    assert p["total_analyses"] == 2
    assert p["current_score"] == 68.0
    assert p["best_score"] == 68.0
    assert p["first_score"] == 60.0
    assert p["total_delta"] == 8.0
    assert p["days_tracked"] == 10


def test_timeline_of_another_users_repository_returns_404(repo_con_dos_analisis):
    _, repo_id, _, _ = repo_con_dos_analisis
    otro = SessionLocal()
    try:
        intruso = User(id=uuid.uuid4(), email="intruso-hist@example.com", github_id=930000099)
        otro.add(intruso)
        otro.commit()
        intruso_id = intruso.id
    finally:
        otro.close()
    try:
        r = client.get(
            f"/api/repositories/{repo_id}/timeline",
            headers={"Authorization": f"Bearer {create_access_token(intruso_id)}"},
        )
        assert r.status_code == 404
    finally:
        db = SessionLocal()
        db.execute(delete(User).where(User.id == intruso_id))
        db.commit()
        db.close()


def test_comparison_detects_improvements_and_regressions(repo_con_dos_analisis):
    user_id, _, viejo_id, nuevo_id = repo_con_dos_analisis
    r = client.get(
        f"/api/analyses/{nuevo_id}/comparison/{viejo_id}",
        headers={"Authorization": f"Bearer {create_access_token(user_id)}"},
    )
    assert r.status_code == 200
    c = r.json()

    assert c["score_delta"] == 8.0
    assert c["trend"] == "mejorando"
    # La comparacion es dirigida: el mas antiguo es siempre el punto de partida.
    assert c["analysis_1_id"] == str(viejo_id)
    assert c["analysis_2_id"] == str(nuevo_id)

    descripciones_mejora = " ".join(i["description"] for i in c["improvements"])
    assert "Fiabilidad" in descripciones_mejora
    assert "no tiene tests" in descripciones_mejora  # hallazgo resuelto

    descripciones_regresion = " ".join(x["description"] for x in c["regressions"])
    assert "Seguridad" in descripciones_regresion
    assert "Dependencia vulnerable" in descripciones_regresion


def test_comparison_produces_a_summary_even_without_an_api_key(repo_con_dos_analisis):
    user_id, _, viejo_id, nuevo_id = repo_con_dos_analisis
    r = client.get(
        f"/api/analyses/{nuevo_id}/comparison/{viejo_id}",
        headers={"Authorization": f"Bearer {create_access_token(user_id)}"},
    )
    resumen = r.json()["summary_text"]
    # Sin clave configurada se usa la plantilla, que nunca devuelve vacio.
    assert resumen
    assert "8" in resumen


def test_comparing_an_analysis_with_itself_is_rejected(repo_con_dos_analisis):
    user_id, _, viejo_id, _ = repo_con_dos_analisis
    r = client.get(
        f"/api/analyses/{viejo_id}/comparison/{viejo_id}",
        headers={"Authorization": f"Bearer {create_access_token(user_id)}"},
    )
    assert r.status_code == 400


def test_a_brand_new_dimension_is_not_counted_as_an_improvement():
    """Empezar a medir algo nuevo no es una mejora del proyecto."""
    db = SessionLocal()
    try:
        user = User(id=uuid.uuid4(), email=TEST_EMAIL, github_id=930000002)
        db.add(user)
        db.flush()
        repo = Repository(id=uuid.uuid4(), user_id=user.id, github_id=5559999,
                          name="d", full_name="a/d", default_branch="main", is_private=False)
        db.add(repo)
        db.flush()
        base = datetime.now(timezone.utc) - timedelta(days=2)
        viejo = Analysis(id=uuid.uuid4(), user_id=user.id, repository_id=repo.id,
                         analysis_type="repository", status="completed", overall_score=50.0,
                         created_at=base)
        nuevo = Analysis(id=uuid.uuid4(), user_id=user.id, repository_id=repo.id,
                         analysis_type="repository", status="completed", overall_score=60.0,
                         created_at=base + timedelta(days=2))
        db.add_all([viejo, nuevo])
        db.flush()
        db.add(Dimension(id=uuid.uuid4(), analysis_id=viejo.id, name="reliability",
                         score=50, weight=0.2, raw_metrics={}))
        db.add(Dimension(id=uuid.uuid4(), analysis_id=nuevo.id, name="reliability",
                         score=50, weight=0.2, raw_metrics={}))
        # Dimension que antes no se media.
        db.add(Dimension(id=uuid.uuid4(), analysis_id=nuevo.id, name="portability",
                         score=90, weight=0.1, raw_metrics={}))
        db.commit()

        resultado = compare_analyses(db, viejo, nuevo)
        assert resultado.improvements == 0
        assert resultado.regressions == 0
    finally:
        db.close()


def test_find_previous_analysis_picks_the_closest_earlier_one(repo_con_dos_analisis):
    _, _, viejo_id, nuevo_id = repo_con_dos_analisis
    db = SessionLocal()
    try:
        nuevo = db.get(Analysis, nuevo_id)
        anterior = find_previous_analysis(db, nuevo)
        assert anterior is not None and anterior.id == viejo_id

        viejo = db.get(Analysis, viejo_id)
        assert find_previous_analysis(db, viejo) is None
    finally:
        db.close()


# --- Resumen ----------------------------------------------------------------


def test_template_summary_mentions_the_net_change_and_a_priority():
    texto, origen = build_summary(
        repository_name="a/b", previous_score=60, current_score=68, days_between=16,
        improvements=["Fiabilidad subio de 34 a 46 (+12)."],
        regressions=["Seguridad bajo de 66 a 62 (-4)."],
        api_key=None,
    )
    assert origen == "plantilla"
    assert "8" in texto
    assert "16 dias" in texto
    assert "Prioridad" in texto


def test_template_summary_handles_a_drop():
    texto, _ = build_summary(
        repository_name="a/b", previous_score=70, current_score=55, days_between=3,
        improvements=[], regressions=["Seguridad bajo de 80 a 50 (-30)."], api_key=None,
    )
    assert "retrocedido" in texto


def test_template_summary_handles_no_change_without_crashing():
    texto, _ = build_summary(
        repository_name="a/b", previous_score=70, current_score=70, days_between=None,
        improvements=[], regressions=[], api_key=None,
    )
    assert "mantiene" in texto
    assert texto.strip()


def test_summary_falls_back_to_template_when_the_model_fails(monkeypatch):
    import app.services.summary_service as modulo

    monkeypatch.setattr(modulo, "_try_model", lambda **kwargs: None)
    texto, origen = build_summary(
        repository_name="a/b", previous_score=60, current_score=68, days_between=5,
        improvements=[], regressions=[], api_key="clave-que-falla",
    )
    assert origen == "plantilla"
    assert texto.strip()
