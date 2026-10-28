"""Verificacion del correo de las cuentas con contrasena.

Sin ella, los limites de uso por cuenta se saltaban inventandose correos.
"""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from app.core.database import SessionLocal
from app.core.security import create_access_token
from app.main import app
from app.models.user import User
from app.services import github_service
from app.services.oauth_state_service import issue_state
from app.services.rate_limit_service import MAX_VERIFICATION_EMAILS_PER_HOUR
from app.services.verification_service import (
    UNVERIFIED_RETENTION_DAYS,
    purge_unverified_accounts,
)

_EMAIL = "verificacion@example.com"
_PASSWORD = "s3cur3-passw0rd"
_GITHUB_ID = 777000111
_PURGA = ["purga-vieja@example.com", "purga-nueva@example.com", "purga-verificada@example.com"]


def _borrar():
    db = SessionLocal()
    try:
        db.execute(delete(User).where(User.email.in_([_EMAIL, *_PURGA])))
        db.execute(delete(User).where(User.github_id == _GITHUB_ID))
        db.commit()
    finally:
        db.close()


@pytest.fixture(autouse=True)
def _limpio(buzon):
    buzon.abrir_enlaces = False
    _borrar()
    yield
    _borrar()


def _token(enlace: str) -> str:
    return enlace.split("#token=", 1)[1]


def test_sin_verificar_no_se_entra_y_se_reenvia_el_enlace(buzon):
    navegador = TestClient(app)
    assert navegador.post("/api/auth/register", json={"accept_privacy": True, "email": _EMAIL, "password": _PASSWORD}).status_code == 201
    assert [d for d, _ in buzon.correos] == [_EMAIL]

    respuesta = navegador.post("/api/auth/login", json={"email": _EMAIL, "password": _PASSWORD})

    assert respuesta.status_code == 403
    assert "qr_access" not in respuesta.cookies
    assert len(buzon.correos) == 2


def test_la_contrasena_mala_sigue_siendo_401_y_no_manda_correo(buzon):
    # El 403 solo lo ve quien sabe la contrasena: si no, diria que cuentas
    # estan pendientes.
    navegador = TestClient(app)
    navegador.post("/api/auth/register", json={"accept_privacy": True, "email": _EMAIL, "password": _PASSWORD})

    respuesta = navegador.post("/api/auth/login", json={"email": _EMAIL, "password": "otra-cosa-123"})

    assert respuesta.status_code == 401
    assert len(buzon.correos) == 1


def test_con_el_enlace_se_verifica_y_ya_se_entra(buzon):
    navegador = TestClient(app)
    navegador.post("/api/auth/register", json={"accept_privacy": True, "email": _EMAIL, "password": _PASSWORD})
    _, enlace = buzon.correos[0]
    assert "/verificar-email#token=" in enlace

    verificado = navegador.post("/api/auth/verify-email", json={"token": _token(enlace)})
    assert verificado.status_code == 200
    assert verificado.json() == {"email": _EMAIL}
    # Abrirlo dos veces no es un error: pasa al pulsar el enlace en dos sitios.
    assert navegador.post("/api/auth/verify-email", json={"token": _token(enlace)}).status_code == 200

    assert navegador.post("/api/auth/login", json={"email": _EMAIL, "password": _PASSWORD}).status_code == 200


def test_otro_tipo_de_token_no_verifica(buzon):
    navegador = TestClient(app)
    navegador.post("/api/auth/register", json={"accept_privacy": True, "email": _EMAIL, "password": _PASSWORD})
    db = SessionLocal()
    try:
        user_id = db.scalar(select(User.id).where(User.email == _EMAIL))
    finally:
        db.close()

    # Un token de acceso esta firmado con el mismo secreto: sin la marca de
    # tipo, valdria como enlace de verificacion.
    for token in (create_access_token(user_id), "basura", ""):
        assert navegador.post("/api/auth/verify-email", json={"token": token}).status_code == 400


def test_reenviar_tiene_tope(buzon):
    navegador = TestClient(app)
    navegador.post("/api/auth/register", json={"accept_privacy": True, "email": _EMAIL, "password": _PASSWORD})

    for _ in range(MAX_VERIFICATION_EMAILS_PER_HOUR + 3):
        respuesta = navegador.post("/api/auth/login", json={"email": _EMAIL, "password": _PASSWORD})
        assert respuesta.status_code == 403

    assert len(buzon.correos) == 1 + MAX_VERIFICATION_EMAILS_PER_HOUR


def test_github_sobre_una_cuenta_sin_verificar_borra_la_contrasena(monkeypatch, buzon):
    # Alguien registra el correo de otro con su propia contrasena. Cuando el
    # dueno entra por GitHub, esa contrasena no puede seguir abriendo la cuenta.
    TestClient(app).post("/api/auth/register", json={"accept_privacy": True, "email": _EMAIL, "password": _PASSWORD})

    monkeypatch.setattr(github_service, "exchange_code_for_token", lambda code: "gho_fake")
    monkeypatch.setattr(
        github_service, "fetch_github_user", lambda token: {"id": _GITHUB_ID, "login": "dueno"}
    )
    monkeypatch.setattr(github_service, "fetch_github_primary_email", lambda token: _EMAIL)

    respuesta = TestClient(app).get(
        "/api/auth/github/callback", params={"code": "x", "state": issue_state()}
    )
    assert respuesta.status_code == 200

    db = SessionLocal()
    try:
        usuario = db.scalar(select(User).where(User.email == _EMAIL))
        assert usuario.password_hash is None
        assert usuario.email_verified_at is not None
    finally:
        db.close()

    intruso = TestClient(app).post("/api/auth/login", json={"email": _EMAIL, "password": _PASSWORD})
    assert intruso.status_code == 401


def test_la_purga_se_lleva_solo_las_cuentas_viejas_sin_verificar():
    ahora = datetime.now(timezone.utc)
    viejo = ahora - timedelta(days=UNVERIFIED_RETENTION_DAYS + 1)
    db = SessionLocal()
    try:
        db.add_all(
            [
                User(id=uuid.uuid4(), email=_PURGA[0], password_hash="x", created_at=viejo),
                User(id=uuid.uuid4(), email=_PURGA[1], password_hash="x", created_at=ahora),
                User(
                    id=uuid.uuid4(), email=_PURGA[2], password_hash="x",
                    created_at=viejo, email_verified_at=viejo,
                ),
            ]
        )
        db.commit()

        purge_unverified_accounts(db)
        db.commit()

        quedan = set(db.scalars(select(User.email).where(User.email.in_(_PURGA))).all())
    finally:
        db.close()

    assert quedan == {_PURGA[1], _PURGA[2]}
