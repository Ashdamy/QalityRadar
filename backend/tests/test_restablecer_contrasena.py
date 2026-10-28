"""Olvide mi contrasena.

Sin esto, quien olvidaba la contrasena perdia la cuenta.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from app.core.database import SessionLocal
from app.core.security import create_access_token
from app.main import app
from app.models.user import User
from app.services import rate_limit_service
from app.services.rate_limit_service import MAX_RESET_EMAILS_PER_EMAIL_HOUR

_EMAIL = "restablecer@example.com"
_VIEJA = "contrasena-vieja-1"
_NUEVA = "contrasena-nueva-2"


def _vaciar_limites():
    cliente = rate_limit_service._client()
    for clave in cliente.scan_iter("ratelimit:reset:*"):
        cliente.delete(clave)


@pytest.fixture(autouse=True)
def _limpio():
    def _borrar():
        db = SessionLocal()
        try:
            db.execute(delete(User).where(User.email == _EMAIL))
            db.commit()
        finally:
            db.close()

    _borrar()
    _vaciar_limites()
    yield
    _borrar()
    _vaciar_limites()


def _token(enlace: str) -> str:
    return enlace.split("#token=", 1)[1]


def _registrado() -> TestClient:
    navegador = TestClient(app)
    navegador.post("/api/auth/register", json={"email": _EMAIL, "password": _VIEJA})
    return navegador


def test_restablecer_cambia_la_contrasena_y_el_enlace_sirve_una_vez(buzon):
    navegador = _registrado()

    assert navegador.post("/api/auth/password/forgot", json={"email": _EMAIL}).status_code == 202
    destinatario, enlace = buzon.restablecer[0]
    assert destinatario == _EMAIL
    assert "/restablecer-contrasena#token=" in enlace

    cuerpo = {"token": _token(enlace), "password": _NUEVA}
    assert navegador.post("/api/auth/password/reset", json=cuerpo).status_code == 204
    # La huella de la contrasena ya no coincide: el mismo enlace no vuelve a valer.
    assert navegador.post("/api/auth/password/reset", json=cuerpo).status_code == 400

    entrar = lambda clave: TestClient(app).post(  # noqa: E731
        "/api/auth/login", json={"email": _EMAIL, "password": clave}
    )
    assert entrar(_VIEJA).status_code == 401
    assert entrar(_NUEVA).status_code == 200


def test_restablecer_cierra_las_sesiones_abiertas(buzon):
    navegador = _registrado()
    assert navegador.post("/api/auth/login", json={"email": _EMAIL, "password": _VIEJA}).status_code == 200

    navegador.post("/api/auth/password/forgot", json={"email": _EMAIL})
    TestClient(app).post(
        "/api/auth/password/reset", json={"token": _token(buzon.restablecer[0][1]), "password": _NUEVA}
    )

    assert navegador.post("/api/auth/refresh").status_code == 401


def test_un_correo_que_no_existe_responde_igual_y_no_manda_nada(buzon):
    respuesta = TestClient(app).post("/api/auth/password/forgot", json={"email": "nadie@example.com"})

    assert respuesta.status_code == 202
    assert respuesta.json() == TestClient(app).post(
        "/api/auth/password/forgot", json={"email": _EMAIL}
    ).json()
    assert buzon.restablecer == []


def test_pedir_enlaces_tiene_tope_y_no_se_nota(buzon):
    _registrado()
    for _ in range(MAX_RESET_EMAILS_PER_EMAIL_HOUR + 2):
        assert TestClient(app).post("/api/auth/password/forgot", json={"email": _EMAIL}).status_code == 202

    assert len(buzon.restablecer) == MAX_RESET_EMAILS_PER_EMAIL_HOUR


def test_otro_tipo_de_token_no_restablece(buzon):
    _registrado()
    db = SessionLocal()
    try:
        user_id = db.scalar(select(User.id).where(User.email == _EMAIL))
    finally:
        db.close()

    for token in (create_access_token(user_id), "basura"):
        respuesta = TestClient(app).post(
            "/api/auth/password/reset", json={"token": token, "password": _NUEVA}
        )
        assert respuesta.status_code == 400


def test_restablecer_verifica_una_cuenta_pendiente(buzon):
    # Abrir el enlace prueba lo mismo que el de verificacion: que el buzon es suyo.
    buzon.abrir_enlaces = False
    _registrado()
    TestClient(app).post("/api/auth/password/forgot", json={"email": _EMAIL})
    TestClient(app).post(
        "/api/auth/password/reset", json={"token": _token(buzon.restablecer[0][1]), "password": _NUEVA}
    )

    respuesta = TestClient(app).post("/api/auth/login", json={"email": _EMAIL, "password": _NUEVA})
    assert respuesta.status_code == 200
