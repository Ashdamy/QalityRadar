"""La pagina "Mi cuenta": ver los datos, cambiar la contrasena, cerrar en todas partes."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete

from app.core.database import SessionLocal
from app.main import app
from app.models.user import User

_EMAIL = "mi-cuenta@example.com"
_VIEJA = "contrasena-vieja-1"
_NUEVA = "contrasena-nueva-2"


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
    yield
    _borrar()


def _dentro() -> TestClient:
    navegador = TestClient(app)
    navegador.post("/api/auth/register", json={"accept_privacy": True, "email": _EMAIL, "password": _VIEJA})
    navegador.post("/api/auth/login", json={"email": _EMAIL, "password": _VIEJA})
    return navegador


def test_me_devuelve_lo_justo():
    datos = _dentro().get("/api/auth/me").json()

    assert datos["email"] == _EMAIL
    assert datos["email_verified"] is True
    assert datos["has_password"] is True
    assert datos["github_connected"] is False
    assert not any("token" in clave for clave in datos)


def test_me_exige_sesion():
    assert TestClient(app).get("/api/auth/me").status_code == 401


def test_cambiar_contrasena_pide_la_actual():
    respuesta = _dentro().post(
        "/api/auth/password/change", json={"current_password": "otra-cosa-123", "new_password": _NUEVA}
    )
    assert respuesta.status_code == 401


def test_cambiar_contrasena_cierra_las_otras_sesiones_y_mantiene_esta():
    este = _dentro()
    otro = TestClient(app)
    otro.post("/api/auth/login", json={"email": _EMAIL, "password": _VIEJA})

    respuesta = este.post(
        "/api/auth/password/change", json={"current_password": _VIEJA, "new_password": _NUEVA}
    )
    assert respuesta.status_code == 200

    assert otro.post("/api/auth/refresh").status_code == 401
    assert este.post("/api/auth/refresh").status_code == 200
    login = TestClient(app).post("/api/auth/login", json={"email": _EMAIL, "password": _NUEVA})
    assert login.status_code == 200


def test_cerrar_en_todas_partes():
    este = _dentro()
    otro = TestClient(app)
    otro.post("/api/auth/login", json={"email": _EMAIL, "password": _VIEJA})

    assert este.post("/api/auth/logout-all").status_code == 204

    assert otro.post("/api/auth/refresh").status_code == 401
    assert este.post("/api/auth/refresh").status_code == 401
