"""Irse: borrar la cuenta y retirar el token de GitHub.

Hasta ahora no habia forma de hacer ninguna de las dos cosas. Guardamos un
token de GitHub cifrado y no habia manera de pedir que lo soltaramos.
"""

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from app.core.database import SessionLocal
from app.main import app
from app.models.analysis import Analysis
from app.models.repository import Repository
from app.models.user import User
from app.services import rate_limit_service as limites
from app.utils.crypto import encrypt_token

_EMAIL = "cuenta-fixture@example.com"
_PASSWORD = "una-contrasena-larga-123"


@pytest.fixture
def cuenta():
    def _borrar():
        db = SessionLocal()
        try:
            db.execute(delete(User).where(User.email == _EMAIL))
            db.commit()
        finally:
            db.close()
        cliente = limites._client()
        for clave in cliente.scan_iter("ratelimit:*"):
            cliente.delete(clave)

    _borrar()
    navegador = TestClient(app)
    navegador.post("/api/auth/register", json={"email": _EMAIL, "password": _PASSWORD})
    navegador.post("/api/auth/login", json={"email": _EMAIL, "password": _PASSWORD})

    db = SessionLocal()
    try:
        usuario = db.scalar(select(User).where(User.email == _EMAIL))
        user_id = usuario.id
    finally:
        db.close()

    yield navegador, user_id
    _borrar()


def _existe(user_id):
    db = SessionLocal()
    try:
        return db.get(User, user_id) is not None
    finally:
        db.close()


def test_borrar_la_cuenta_exige_la_contrasena(cuenta):
    """Es irreversible: una sesion abierta en un ordenador prestado no deberia
    bastar."""
    navegador, user_id = cuenta

    sin_clave = navegador.request("DELETE", "/api/auth/account")
    mal = navegador.request("DELETE", "/api/auth/account", json={"password": "no-es"})

    assert sin_clave.status_code == 401
    assert mal.status_code == 401
    assert _existe(user_id)


def test_con_la_contrasena_la_cuenta_se_va(cuenta):
    navegador, user_id = cuenta

    respuesta = navegador.request(
        "DELETE", "/api/auth/account", json={"password": _PASSWORD}
    )

    assert respuesta.status_code == 204
    assert not _existe(user_id)


def test_al_borrar_la_cuenta_se_va_todo_lo_suyo(cuenta):
    """Las claves ajenas van con ON DELETE CASCADE, asi que la fila del usuario
    se lleva el resto por delante."""
    navegador, user_id = cuenta
    db = SessionLocal()
    try:
        repo = Repository(
            id=uuid.uuid4(), user_id=user_id, github_id=777000222,
            name="proyecto", full_name="alguien/proyecto",
        )
        db.add(repo)
        db.flush()
        db.add(Analysis(
            id=uuid.uuid4(), user_id=user_id, repository_id=repo.id,
            analysis_type="repository", status="completed",
        ))
        db.commit()
        repo_id = repo.id
    finally:
        db.close()

    navegador.request("DELETE", "/api/auth/account", json={"password": _PASSWORD})

    db = SessionLocal()
    try:
        assert db.get(Repository, repo_id) is None
        assert db.scalars(
            select(Analysis).where(Analysis.repository_id == repo_id)
        ).all() == []
    finally:
        db.close()


def test_la_sesion_muere_con_la_cuenta(cuenta):
    navegador, _ = cuenta

    navegador.request("DELETE", "/api/auth/account", json={"password": _PASSWORD})

    assert navegador.get("/api/usage").status_code == 401


def test_sin_sesion_no_se_borra_nada():
    assert TestClient(app).request("DELETE", "/api/auth/account").status_code == 401


def test_desconectar_github_retira_el_token(cuenta):
    navegador, user_id = cuenta
    db = SessionLocal()
    try:
        usuario = db.get(User, user_id)
        usuario.github_id = 424242
        usuario.github_access_token_encrypted = encrypt_token("gho_token_de_prueba")
        db.commit()
    finally:
        db.close()

    assert navegador.request("DELETE", "/api/auth/github").status_code == 204

    db = SessionLocal()
    try:
        usuario = db.get(User, user_id)
        assert usuario.github_access_token_encrypted is None
        # La identidad se conserva: borrarla dejaria fuera para siempre a quien
        # entro por GitHub y no tiene contrasena.
        assert usuario.github_id == 424242
    finally:
        db.close()


def test_desconectar_sin_nada_conectado_no_miente(cuenta):
    navegador, _ = cuenta

    assert navegador.request("DELETE", "/api/auth/github").status_code == 404
