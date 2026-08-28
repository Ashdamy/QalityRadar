"""Los cuatro huecos de seguridad que quedaban en autenticacion.

Cada bloque fija un fallo concreto que estaba documentado como deuda: el
`state` del OAuth, el limite de bcrypt, la carrera en el registro y la
separacion entre token de acceso y de refresco.
"""

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete

from app.core.database import SessionLocal
from app.core.security import (
    ACCESS_TOKEN_TYPE,
    REFRESH_TOKEN_TYPE,
    InvalidTokenType,
    create_access_token,
    create_refresh_token,
    decode_access_token,
    decode_refresh_token,
    hash_password,
    verify_password,
)
from app.main import app
from app.models.user import User
from app.services.oauth_state_service import consume_state, issue_state

client = TestClient(app)

_EMAIL = "hardening-fixture@example.com"


def _borrar_usuario():
    db = SessionLocal()
    try:
        db.execute(delete(User).where(User.email == _EMAIL))
        db.commit()
    finally:
        db.close()


@pytest.fixture(autouse=True)
def _limpieza():
    _borrar_usuario()
    yield
    _borrar_usuario()


# --------------------------------------------------------------------------
# `state` del OAuth: proteccion contra CSRF
# --------------------------------------------------------------------------


def test_la_url_de_autorizacion_incluye_un_state():
    from urllib.parse import parse_qs, urlparse

    respuesta = client.get("/api/auth/github/login")
    assert respuesta.status_code == 200
    query = parse_qs(urlparse(respuesta.json()["authorization_url"]).query)
    assert query["state"][0]


def test_dos_solicitudes_reciben_states_distintos():
    """Si se repitiera, capturar uno serviria para siempre."""
    from urllib.parse import parse_qs, urlparse

    def estado():
        url = client.get("/api/auth/github/login").json()["authorization_url"]
        return parse_qs(urlparse(url).query)["state"][0]

    assert estado() != estado()


def test_el_callback_sin_state_se_rechaza():
    """El ataque que esto evita: forzar el callback con un `code` ajeno."""
    respuesta = client.get("/api/auth/github/callback", params={"code": "cualquiera"})
    assert respuesta.status_code == 400


def test_el_callback_con_un_state_inventado_se_rechaza():
    respuesta = client.get(
        "/api/auth/github/callback",
        params={"code": "cualquiera", "state": "no-salio-de-aqui"},
    )
    assert respuesta.status_code == 400


def test_un_state_solo_sirve_una_vez():
    """Reproducir un callback capturado no debe funcionar."""
    state = issue_state()
    assert consume_state(state) is True
    assert consume_state(state) is False


def test_consumir_un_state_vacio_no_revienta():
    assert consume_state(None) is False
    assert consume_state("") is False


# --------------------------------------------------------------------------
# Limite de 72 bytes de bcrypt
# --------------------------------------------------------------------------


def test_el_registro_rechaza_una_contrasena_demasiado_larga():
    respuesta = client.post(
        "/api/auth/register",
        json={"email": _EMAIL, "password": "a" * 73},
    )
    assert respuesta.status_code == 422


def test_una_contrasena_larga_en_el_login_da_401_y_no_500():
    """bcrypt lanza ValueError por encima de 72 bytes, y eso llegaba al
    cliente como un error del servidor."""
    client.post("/api/auth/register", json={"email": _EMAIL, "password": "correcta123"})
    respuesta = client.post(
        "/api/auth/login",
        json={"email": _EMAIL, "password": "a" * 200},
    )
    assert respuesta.status_code == 401


def test_verificar_una_contrasena_larga_devuelve_falso_sin_excepcion():
    assert verify_password("a" * 500, hash_password("corta")) is False


def test_una_contrasena_de_72_bytes_sigue_siendo_valida():
    """El limite es 72 inclusive: no hay que estrecharlo de mas."""
    secreto = "a" * 72
    assert verify_password(secreto, hash_password(secreto)) is True


# --------------------------------------------------------------------------
# Carrera en el registro
# --------------------------------------------------------------------------


def test_registrar_dos_veces_el_mismo_email_da_409():
    primera = client.post("/api/auth/register", json={"email": _EMAIL, "password": "clave12345"})
    assert primera.status_code == 201
    segunda = client.post("/api/auth/register", json={"email": _EMAIL, "password": "otra12345"})
    assert segunda.status_code == 409


def test_la_restriccion_de_la_tabla_se_traduce_a_409_y_no_a_500():
    """Simula la carrera: la fila aparece entre la comprobacion y el commit,
    asi que la unica defensa que queda es el indice unico."""
    from app.api import auth as auth_api

    client.post("/api/auth/register", json={"email": _EMAIL, "password": "clave12345"})

    original = auth_api.select

    def select_que_no_ve_la_fila(*args, **kwargs):
        # Devuelve una consulta que no encuentra nada, como si el email aun
        # no estuviera registrado en el momento de comprobarlo.
        return original(*args, **kwargs).where(User.email == "inexistente@example.com")

    auth_api.select = select_que_no_ve_la_fila
    try:
        respuesta = client.post(
            "/api/auth/register", json={"email": _EMAIL, "password": "otra12345"}
        )
    finally:
        auth_api.select = original

    assert respuesta.status_code == 409


# --------------------------------------------------------------------------
# Token de acceso frente a token de refresco
# --------------------------------------------------------------------------


def test_el_login_devuelve_los_dos_tokens():
    client.post("/api/auth/register", json={"email": _EMAIL, "password": "clave12345"})
    cuerpo = client.post(
        "/api/auth/login", json={"email": _EMAIL, "password": "clave12345"}
    ).json()
    assert cuerpo["access_token"]
    assert cuerpo["refresh_token"]
    assert cuerpo["access_token"] != cuerpo["refresh_token"]


def test_un_token_de_refresco_no_sirve_como_token_de_acceso():
    """Se firman con el mismo secreto: sin la marca de tipo, robar uno de
    refresco daria 30 dias de acceso en vez de un solo canje."""
    identificador = uuid.uuid4()
    with pytest.raises(InvalidTokenType):
        decode_access_token(create_refresh_token(identificador))


def test_un_token_de_acceso_no_sirve_para_refrescar():
    identificador = uuid.uuid4()
    with pytest.raises(InvalidTokenType):
        decode_refresh_token(create_access_token(identificador))


def test_cada_token_se_descodifica_con_su_tipo():
    identificador = uuid.uuid4()
    assert decode_access_token(create_access_token(identificador)) == identificador
    assert decode_refresh_token(create_refresh_token(identificador)) == identificador


def test_los_tipos_de_token_no_se_llaman_igual():
    assert ACCESS_TOKEN_TYPE != REFRESH_TOKEN_TYPE


def test_refrescar_devuelve_un_token_de_acceso_usable():
    client.post("/api/auth/register", json={"email": _EMAIL, "password": "clave12345"})
    tokens = client.post(
        "/api/auth/login", json={"email": _EMAIL, "password": "clave12345"}
    ).json()

    respuesta = client.post(
        "/api/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
    )
    assert respuesta.status_code == 200
    nuevo = respuesta.json()["access_token"]

    # Sirve de verdad contra un endpoint protegido.
    protegido = client.get("/api/repositories", headers={"Authorization": f"Bearer {nuevo}"})
    assert protegido.status_code != 401


def test_refrescar_con_un_token_invalido_da_401():
    respuesta = client.post("/api/auth/refresh", json={"refresh_token": "no-es-un-token"})
    assert respuesta.status_code == 401


def test_refrescar_con_un_token_de_acceso_da_401():
    """El endpoint no debe aceptar el token equivocado aunque sea valido."""
    client.post("/api/auth/register", json={"email": _EMAIL, "password": "clave12345"})
    tokens = client.post(
        "/api/auth/login", json={"email": _EMAIL, "password": "clave12345"}
    ).json()
    respuesta = client.post(
        "/api/auth/refresh", json={"refresh_token": tokens["access_token"]}
    )
    assert respuesta.status_code == 401


def test_refrescar_con_la_cuenta_ya_borrada_da_401():
    """Treinta dias de margen dan tiempo de sobra a que la cuenta desaparezca."""
    borrado = create_refresh_token(uuid.uuid4())
    respuesta = client.post("/api/auth/refresh", json={"refresh_token": borrado})
    assert respuesta.status_code == 401
