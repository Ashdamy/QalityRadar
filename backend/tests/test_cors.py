"""El frontend corre en otro origen (localhost:3000) que la API
(localhost:8000). Sin cabeceras CORS correctas el navegador bloquea cada
llamada y el login no funciona, aunque los endpoints respondan bien fuera
del navegador. Estos tests cubren justo ese caso.
"""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

FRONTEND_ORIGIN = "http://localhost:3000"


def test_preflight_from_frontend_origin_is_allowed():
    response = client.options(
        "/api/auth/register",
        headers={
            "Origin": FRONTEND_ORIGIN,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == FRONTEND_ORIGIN


def test_actual_request_carries_allow_origin_header():
    response = client.post(
        "/api/auth/login",
        json={"email": "quien-sea@example.com", "password": "no-importa"},
        headers={"Origin": FRONTEND_ORIGIN},
    )

    # Las credenciales son invalidas a proposito: lo que se comprueba es que
    # incluso la respuesta de error llegue con la cabecera CORS, porque sin
    # ella el navegador ni siquiera deja leer el mensaje de error.
    assert response.status_code == 401
    assert response.headers["access-control-allow-origin"] == FRONTEND_ORIGIN


def test_authorization_header_is_allowed():
    response = client.options(
        "/api/repositories",
        headers={
            "Origin": FRONTEND_ORIGIN,
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "authorization",
        },
    )

    assert response.status_code == 200
    assert "authorization" in response.headers["access-control-allow-headers"].lower()


def test_unknown_origin_is_not_allowed():
    response = client.options(
        "/api/auth/register",
        headers={
            "Origin": "https://sitio-que-no-autorizamos.example",
            "Access-Control-Request-Method": "POST",
        },
    )

    assert "access-control-allow-origin" not in response.headers
