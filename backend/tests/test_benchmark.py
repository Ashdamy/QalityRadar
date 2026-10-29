"""Referencia por lenguaje: GET /api/repositories/{id}/benchmark.

Los valores de `benchmark_data` son SIMULADOS (migracion 0009). La API lo
dice en cada respuesta para que el frontend nunca los presente como reales.
"""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete

from app.core.database import SessionLocal
from app.main import app
from app.models.analysis import Analysis, Dimension
from app.models.repository import Repository
from app.models.user import User

_EMAIL = "benchmark@example.com"
_OTRO = "benchmark-otro@example.com"


def _borrar():
    db = SessionLocal()
    try:
        db.execute(delete(User).where(User.email.in_([_EMAIL, _OTRO])))
        db.commit()
    finally:
        db.close()


def _entrar(email):
    navegador = TestClient(app)
    navegador.post("/api/auth/register", json={"accept_privacy": True, "email": email, "password": "s3cur3-passw0rd"})
    navegador.post("/api/auth/login", json={"email": email, "password": "s3cur3-passw0rd"})
    return navegador


@pytest.fixture
def repo():
    _borrar()
    navegador = _entrar(_EMAIL)
    db = SessionLocal()
    try:
        usuario = db.query(User).filter_by(email=_EMAIL).one()
        repositorio = Repository(id=uuid.uuid4(), user_id=usuario.id, github_id=555000777, name="p", full_name="alguien/p")
        db.add(repositorio)
        db.commit()
        datos = (navegador, usuario.id, repositorio.id)
    finally:
        db.close()
    yield datos
    _borrar()


def _analisis(user_id, repo_id, lenguaje, notas, *, estado="completed", hace_dias=0, tipo="repository"):
    db = SessionLocal()
    try:
        analisis = Analysis(
            id=uuid.uuid4(), user_id=user_id, repository_id=repo_id, analysis_type=tipo,
            status=estado, created_at=datetime.now(timezone.utc) - timedelta(days=hace_dias),
        )
        db.add(analisis)
        db.flush()
        for nombre, nota in notas.items():
            db.add(Dimension(
                id=uuid.uuid4(), analysis_id=analisis.id, name=nombre, score=nota, weight=0.2,
                raw_metrics={"primary_language": lenguaje} if nombre == "maintainability" else {},
            ))
        db.commit()
    finally:
        db.close()


def test_compara_con_la_referencia_de_su_lenguaje_y_avisa_de_que_es_simulada(repo):
    navegador, user_id, repo_id = repo
    _analisis(user_id, repo_id, "Python", {"maintainability": 70, "security": 50, "portability": 40})

    respuesta = navegador.get(f"/api/repositories/{repo_id}/benchmark")

    assert respuesta.status_code == 200
    datos = respuesta.json()
    assert datos["language"] == "Python"
    assert datos["is_simulated"] is True
    por_dimension = {i["dimension"]: i for i in datos["items"]}
    # Solo las que tienen referencia: flexibilidad no la tiene.
    assert set(por_dimension) == {"maintainability", "security"}
    assert por_dimension["maintainability"] == {
        "dimension": "maintainability", "label": "Mantenibilidad",
        "score": 70.0, "reference": 68.0, "delta": 2.0,
    }


def test_usa_el_ultimo_analisis_completado_de_repositorio(repo):
    navegador, user_id, repo_id = repo
    _analisis(user_id, repo_id, "Python", {"maintainability": 10}, hace_dias=5)
    _analisis(user_id, repo_id, "Python", {"maintainability": 80}, hace_dias=1)
    _analisis(user_id, repo_id, "Python", {"maintainability": 99}, estado="failed")

    datos = navegador.get(f"/api/repositories/{repo_id}/benchmark").json()

    assert datos["items"][0]["score"] == 80.0


@pytest.mark.parametrize("lenguaje", ["Rust", None])
def test_sin_referencia_para_el_lenguaje_no_devuelve_nada(repo, lenguaje):
    navegador, user_id, repo_id = repo
    _analisis(user_id, repo_id, lenguaje, {"maintainability": 70})

    assert navegador.get(f"/api/repositories/{repo_id}/benchmark").status_code == 204


def test_sin_analisis_no_devuelve_nada(repo):
    navegador, _, repo_id = repo
    assert navegador.get(f"/api/repositories/{repo_id}/benchmark").status_code == 204


def test_el_repositorio_de_otro_es_404(repo):
    _, _, repo_id = repo
    assert _entrar(_OTRO).get(f"/api/repositories/{repo_id}/benchmark").status_code == 404


def test_exige_sesion(repo):
    _, _, repo_id = repo
    assert TestClient(app).get(f"/api/repositories/{repo_id}/benchmark").status_code == 401
