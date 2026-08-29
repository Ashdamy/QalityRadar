"""Los huecos de seguridad que quedaban antes de poder abrir esto al publico.

Ninguno importaba mientras el proyecto corriera en un ordenador propio; todos
importan en cuanto hay una direccion publica. Se prueban aqui juntos porque
comparten la misma pregunta: que pasa cuando quien usa el sistema no es alguien
de confianza.
"""

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from app.core.database import SessionLocal
from app.core.security import create_refresh_token
from app.main import app
from app.models.refresh_token import RefreshToken
from app.models.user import User
from app.services import rate_limit_service as limites
from app.services import session_service
from app.services.rate_limit_service import (
    MAX_GLOBAL_CONCURRENT,
    MAX_REGISTRATIONS_PER_IP_HOUR,
    RateLimitExceeded,
    check_and_reserve,
    check_registration_ip,
    global_running,
    release,
)

client = TestClient(app)

_EMAIL = "endurecimiento-fixture@example.com"
_PASSWORD = "una-contrasena-larga-123"


def _borrar_usuario():
    db = SessionLocal()
    try:
        db.execute(delete(User).where(User.email == _EMAIL))
        db.commit()
    finally:
        db.close()


def _limpiar_redis():
    cliente = limites._client()
    cliente.delete(limites._GLOBAL_RUNNING_KEY)
    for clave in cliente.scan_iter("ratelimit:registrations:*"):
        cliente.delete(clave)


@pytest.fixture(autouse=True)
def _limpieza():
    _borrar_usuario()
    _limpiar_redis()
    yield
    _borrar_usuario()
    _limpiar_redis()


# --------------------------------------------------------------------------
# Longitud minima de contrasena
# --------------------------------------------------------------------------


@pytest.mark.parametrize("clave", ["a", "1234567"])
def test_una_contrasena_corta_se_rechaza(clave):
    """Se podia registrar una cuenta con una contrasena de un solo caracter."""
    respuesta = client.post("/api/auth/register", json={"email": _EMAIL, "password": clave})
    assert respuesta.status_code == 422


def test_una_contrasena_de_ocho_caracteres_se_acepta():
    """El limite es ocho inclusive: no hay que estrecharlo de mas."""
    respuesta = client.post("/api/auth/register", json={"email": _EMAIL, "password": "12345678"})
    assert respuesta.status_code == 201


# --------------------------------------------------------------------------
# Cerrar sesion invalida el token de verdad
# --------------------------------------------------------------------------


def _crear_sesion() -> dict:
    client.post("/api/auth/register", json={"email": _EMAIL, "password": _PASSWORD})
    return client.post(
        "/api/auth/login", json={"email": _EMAIL, "password": _PASSWORD}
    ).json()


def test_el_token_de_refresco_queda_registrado_al_entrar():
    tokens = _crear_sesion()
    db = SessionLocal()
    try:
        assert session_service.is_active(db, tokens["refresh_token"]) is True
    finally:
        db.close()


def test_el_token_en_claro_nunca_se_guarda():
    """Si alguien lee la tabla, no puede usar lo que encuentre."""
    tokens = _crear_sesion()
    db = SessionLocal()
    try:
        guardados = [f.token_hash for f in db.scalars(select(RefreshToken)).all()]
        assert tokens["refresh_token"] not in guardados
    finally:
        db.close()


def test_cerrar_sesion_invalida_el_token_al_instante():
    """Antes cerrar sesion solo lo borraba del navegador: un token robado
    seguia funcionando treinta dias."""
    tokens = _crear_sesion()
    assert client.post("/api/auth/refresh", json={"refresh_token": tokens["refresh_token"]}).status_code == 200

    assert client.post("/api/auth/logout", json={"refresh_token": tokens["refresh_token"]}).status_code == 204

    despues = client.post("/api/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert despues.status_code == 401


def test_cerrar_sesion_no_necesita_sesion_valida():
    """Si el token de acceso ya caduco, cerrar sesion tiene que seguir
    funcionando."""
    tokens = _crear_sesion()
    respuesta = client.post("/api/auth/logout", json={"refresh_token": tokens["refresh_token"]})
    assert respuesta.status_code == 204


def test_cerrar_sesion_con_un_token_inventado_no_revela_nada():
    respuesta = client.post("/api/auth/logout", json={"refresh_token": "no-existe"})
    assert respuesta.status_code == 204


def test_un_token_firmado_pero_no_registrado_se_rechaza():
    """Firma valida no basta: tiene que constar como sesion abierta."""
    ajeno = create_refresh_token(uuid.uuid4())
    respuesta = client.post("/api/auth/refresh", json={"refresh_token": ajeno})
    assert respuesta.status_code == 401


def test_cerrar_todas_las_sesiones_invalida_las_dos():
    _crear_sesion()
    primera = client.post("/api/auth/login", json={"email": _EMAIL, "password": _PASSWORD}).json()
    segunda = client.post("/api/auth/login", json={"email": _EMAIL, "password": _PASSWORD}).json()

    db = SessionLocal()
    try:
        usuario = db.scalar(select(User).where(User.email == _EMAIL))
        assert session_service.revoke_all_for_user(db, usuario.id) >= 2
        db.commit()
    finally:
        db.close()

    for tokens in (primera, segunda):
        respuesta = client.post(
            "/api/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
        )
        assert respuesta.status_code == 401


def test_entrar_por_github_tambien_devuelve_token_de_refresco():
    """Sin el, quien entraba por GitHub se quedaba sin sesion a los 15 minutos
    y no habia forma de renovarla."""
    import inspect

    from app.api import auth as auth_api

    fuente = inspect.getsource(auth_api.github_callback)
    assert "_emitir_sesion" in fuente


# --------------------------------------------------------------------------
# Tope global de analisis simultaneos
# --------------------------------------------------------------------------


def test_el_tope_global_corta_aunque_cada_usuario_tenga_hueco():
    """El riesgo que esto cubre: los limites por usuario no impiden que diez
    cuentas coincidan y pidan mas contenedores de los que caben en memoria."""
    reservas = []
    try:
        for _ in range(MAX_GLOBAL_CONCURRENT):
            # Un usuario distinto cada vez: individualmente todos tienen hueco.
            usuario = uuid.uuid4()
            reserva = str(uuid.uuid4())
            check_and_reserve(usuario, reserva)
            reservas.append((usuario, reserva))

        with pytest.raises(RateLimitExceeded) as excinfo:
            check_and_reserve(uuid.uuid4(), str(uuid.uuid4()))
        assert "maximo de analisis" in excinfo.value.message
    finally:
        for usuario, reserva in reservas:
            release(usuario, reserva)
        _limpiar_redis()


def test_liberar_un_hueco_devuelve_capacidad_global():
    reservas = []
    try:
        for _ in range(MAX_GLOBAL_CONCURRENT):
            usuario, reserva = uuid.uuid4(), str(uuid.uuid4())
            check_and_reserve(usuario, reserva)
            reservas.append((usuario, reserva))

        usuario, reserva = reservas.pop()
        release(usuario, reserva)
        check_and_reserve(uuid.uuid4(), str(uuid.uuid4()))  # no debe lanzar
    finally:
        _limpiar_redis()


def test_el_contador_global_refleja_lo_reservado():
    try:
        assert global_running() == 0
        check_and_reserve(uuid.uuid4(), str(uuid.uuid4()))
        assert global_running() == 1
    finally:
        _limpiar_redis()


# --------------------------------------------------------------------------
# Registros por IP
# --------------------------------------------------------------------------


def test_no_se_pueden_crear_cuentas_sin_fin_desde_una_ip():
    """Como los limites de uso son por cuenta, sin esto basta con registrar
    varias para saltarselos."""
    try:
        for _ in range(MAX_REGISTRATIONS_PER_IP_HOUR):
            check_registration_ip("203.0.113.7")
        with pytest.raises(RateLimitExceeded):
            check_registration_ip("203.0.113.7")
    finally:
        _limpiar_redis()


def test_el_limite_de_registro_es_por_ip_y_no_global():
    try:
        for _ in range(MAX_REGISTRATIONS_PER_IP_HOUR):
            check_registration_ip("203.0.113.7")
        check_registration_ip("203.0.113.8")  # otra IP, no debe lanzar
    finally:
        _limpiar_redis()


def test_sin_ip_conocida_no_se_bloquea_a_nadie():
    """Detras de segun que proxy no siempre llega. Mejor no limitar que
    rechazar a usuarios legitimos."""
    for _ in range(MAX_REGISTRATIONS_PER_IP_HOUR * 2):
        check_registration_ip(None)
