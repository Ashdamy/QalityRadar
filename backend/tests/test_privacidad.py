"""Autorizacion de tratamiento de datos (Ley 1581 de 2012).

Sin aceptar la politica no hay cuenta, y la aceptacion queda guardada como
prueba: cuando y que version.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from app.api.auth import PRIVACY_POLICY_VERSION
from app.core.database import SessionLocal
from app.main import app
from app.models.user import User
from app.services import github_service
from app.services.oauth_state_service import issue_state

_EMAIL = "privacidad@example.com"
_GITHUB_ID = 777000222


@pytest.fixture(autouse=True)
def _limpio():
    def _borrar():
        db = SessionLocal()
        try:
            db.execute(delete(User).where(User.email == _EMAIL))
            db.execute(delete(User).where(User.github_id == _GITHUB_ID))
            db.commit()
        finally:
            db.close()

    _borrar()
    yield
    _borrar()


def _usuario() -> User:
    db = SessionLocal()
    try:
        return db.scalar(select(User).where(User.email == _EMAIL))
    finally:
        db.close()


@pytest.mark.parametrize("cuerpo", [{}, {"accept_privacy": False}])
def test_sin_aceptar_la_politica_no_hay_cuenta(cuerpo):
    respuesta = TestClient(app).post(
        "/api/auth/register", json={"email": _EMAIL, "password": "s3cur3-passw0rd", **cuerpo}
    )

    assert respuesta.status_code == 422
    assert _usuario() is None


def test_el_registro_guarda_la_prueba_de_la_aceptacion():
    TestClient(app).post(
        "/api/auth/register",
        json={"email": _EMAIL, "password": "s3cur3-passw0rd", "accept_privacy": True},
    )

    usuario = _usuario()
    assert usuario.privacy_accepted_at is not None
    assert usuario.privacy_version == PRIVACY_POLICY_VERSION


def test_entrar_por_github_tambien_la_guarda(monkeypatch):
    monkeypatch.setattr(github_service, "exchange_code_for_token", lambda code: "gho_fake")
    monkeypatch.setattr(github_service, "fetch_github_user", lambda token: {"id": _GITHUB_ID, "login": "alguien"})
    monkeypatch.setattr(github_service, "fetch_github_primary_email", lambda token: _EMAIL)

    TestClient(app).get("/api/auth/github/callback", params={"code": "x", "state": issue_state()})

    usuario = _usuario()
    assert usuario.privacy_accepted_at is not None
    assert usuario.privacy_version == PRIVACY_POLICY_VERSION
