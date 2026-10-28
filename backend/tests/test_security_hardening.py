"""Los huecos de seguridad que quedaban antes de poder abrir esto al publico.

Ninguno importaba mientras el proyecto corriera en un ordenador propio; todos
importan en cuanto hay una direccion publica. Se prueban aqui juntos porque
comparten la misma pregunta: que pasa cuando quien usa el sistema no es alguien
de confianza.
"""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError
from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from app.core.config import get_settings
from app.core.database import SessionLocal
import jwt

from app.core.config import Settings
from app.core.security import (
    ACCESS_TOKEN_TYPE,
    InvalidTokenType,
    create_refresh_token,
    decode_access_token,
)
from app.main import MAX_REQUEST_BYTES, app
from app.models.refresh_token import RefreshToken
from app.models.user import User
from app.services import rate_limit_service as limites
from app.services import session_service
from app.services.rate_limit_service import (
    MAX_GLOBAL_CONCURRENT,
    MAX_LOGIN_FAILURES_PER_EMAIL_HOUR,
    MAX_REGISTRATIONS_PER_IP_HOUR,
    RateLimitExceeded,
    check_and_reserve,
    check_login_allowed,
    check_registration_ip,
    clear_login_failures,
    global_running,
    record_login_failure,
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
    for patron in ("ratelimit:registrations:*", "ratelimit:login:*"):
        for clave in cliente.scan_iter(patron):
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
    respuesta = client.post("/api/auth/register", json={"accept_privacy": True, "email": _EMAIL, "password": clave})
    assert respuesta.status_code == 422


def test_una_contrasena_de_ocho_caracteres_se_acepta():
    """El limite es ocho inclusive: no hay que estrecharlo de mas."""
    respuesta = client.post("/api/auth/register", json={"accept_privacy": True, "email": _EMAIL, "password": "12345678"})
    assert respuesta.status_code == 201


# --------------------------------------------------------------------------
# Cerrar sesion invalida el token de verdad
# --------------------------------------------------------------------------


def _crear_sesion() -> dict:
    client.post("/api/auth/register", json={"accept_privacy": True, "email": _EMAIL, "password": _PASSWORD})
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


# --------------------------------------------------------------------------
# Cabeceras de seguridad de la propia API
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "cabecera,valor",
    [
        ("X-Content-Type-Options", "nosniff"),
        ("X-Frame-Options", "DENY"),
        ("Referrer-Policy", "no-referrer"),
    ],
)
def test_la_api_envia_sus_cabeceras_de_seguridad(cabecera, valor):
    """QalitiRadar penalizaba a otros sitios por no enviarlas y la propia API
    no enviaba ninguna."""
    respuesta = client.get("/health")
    assert respuesta.headers.get(cabecera) == valor


def test_la_politica_de_contenido_no_permite_incrustar_la_api():
    respuesta = client.get("/health")
    politica = respuesta.headers.get("Content-Security-Policy", "")
    assert "frame-ancestors 'none'" in politica


def test_las_cabeceras_acompanan_tambien_a_los_errores():
    """Una respuesta de error tambien la interpreta el navegador."""
    respuesta = client.get("/api/reports/shared/no-existe")
    assert respuesta.status_code == 404
    assert respuesta.headers.get("X-Content-Type-Options") == "nosniff"


def test_la_documentacion_interactiva_se_puede_apagar():
    """Publicada regala el mapa completo de la API: cada ruta, cada parametro
    y cada forma de respuesta."""
    from app.core.config import Settings

    assert Settings.model_fields["enable_api_docs"].default is True  # comodo en local
    import inspect

    from app import main

    fuente = inspect.getsource(main)
    assert "enable_api_docs" in fuente


# --------------------------------------------------------------------------
# Fuerza bruta contra el inicio de sesion
# --------------------------------------------------------------------------


def test_los_intentos_fallidos_de_login_se_acaban():
    """bcrypt hace lento cada intento, pero lento no es imposible: sin limite
    se pueden probar contrasenas toda la noche contra la misma cuenta."""
    for _ in range(MAX_LOGIN_FAILURES_PER_EMAIL_HOUR):
        check_login_allowed(_EMAIL, "203.0.113.9")
        record_login_failure(_EMAIL, "203.0.113.9")

    with pytest.raises(RateLimitExceeded) as excinfo:
        check_login_allowed(_EMAIL, "203.0.113.9")
    assert excinfo.value.retry_after_seconds > 0


def test_el_limite_de_login_sigue_al_email_aunque_cambie_la_ip():
    """Un ataque distribuido cambia de IP cada intento; si solo se contara por
    IP, la cuenta quedaria igual de expuesta."""
    for numero in range(MAX_LOGIN_FAILURES_PER_EMAIL_HOUR):
        record_login_failure(_EMAIL, f"203.0.113.{numero}")

    with pytest.raises(RateLimitExceeded):
        check_login_allowed(_EMAIL, "198.51.100.1")


def test_bloquear_una_cuenta_no_bloquea_a_las_demas():
    for _ in range(MAX_LOGIN_FAILURES_PER_EMAIL_HOUR):
        record_login_failure(_EMAIL, None)

    check_login_allowed("otra-persona@example.com", None)  # no debe lanzar


def test_entrar_bien_borra_los_fallos_de_esa_cuenta():
    """Un despiste con la contrasena no puede dejar al dueno fuera una hora."""
    for _ in range(MAX_LOGIN_FAILURES_PER_EMAIL_HOUR):
        record_login_failure(_EMAIL, None)

    clear_login_failures(_EMAIL)
    check_login_allowed(_EMAIL, None)  # no debe lanzar


def test_el_endpoint_de_login_responde_429_al_pasarse():
    """De punta a punta: el limite tiene que llegar al cliente como 429 con
    Retry-After, no como un 401 mas."""
    client.post("/api/auth/register", json={"accept_privacy": True, "email": _EMAIL, "password": _PASSWORD})

    for _ in range(MAX_LOGIN_FAILURES_PER_EMAIL_HOUR):
        fallo = client.post("/api/auth/login", json={"email": _EMAIL, "password": "no-es-esta"})
        assert fallo.status_code == 401

    bloqueado = client.post("/api/auth/login", json={"email": _EMAIL, "password": "no-es-esta"})
    assert bloqueado.status_code == 429
    assert "Retry-After" in bloqueado.headers

    # Y la contrasena buena tampoco pasa mientras dure el bloqueo: si pasara,
    # el atacante sabria que acerto por el codigo de respuesta.
    correcta = client.post("/api/auth/login", json={"email": _EMAIL, "password": _PASSWORD})
    assert correcta.status_code == 429


# --------------------------------------------------------------------------
# Un token sin tipo ya no vale
# --------------------------------------------------------------------------


def test_un_token_sin_marca_de_tipo_se_rechaza():
    """Hubo un periodo en que un token sin `type` se trataba como de acceso,
    para no cortar las sesiones al desplegar los tipos. Mientras duro, un token
    de refresco robado valia como token de acceso."""
    ajustes = get_settings()
    sin_tipo = jwt.encode(
        {
            "sub": str(uuid.uuid4()),
            "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
        },
        ajustes.jwt_secret,
        algorithm=ajustes.jwt_algorithm,
    )

    with pytest.raises(InvalidTokenType):
        decode_access_token(sin_tipo)


def test_un_token_de_acceso_normal_sigue_valiendo():
    ajustes = get_settings()
    identificador = uuid.uuid4()
    bueno = jwt.encode(
        {
            "sub": str(identificador),
            "type": ACCESS_TOKEN_TYPE,
            "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
        },
        ajustes.jwt_secret,
        algorithm=ajustes.jwt_algorithm,
    )

    assert decode_access_token(bueno) == identificador


# --------------------------------------------------------------------------
# Secretos de despliegue
# --------------------------------------------------------------------------


def _ajustes_con(**cambios):
    base = get_settings()
    valores = {
        "database_url": base.database_url,
        "redis_url": base.redis_url,
        "jwt_secret": base.jwt_secret,
        "encryption_key": base.encryption_key,
        "github_client_id": base.github_client_id,
        "github_client_secret": base.github_client_secret,
        "github_oauth_redirect_uri": base.github_oauth_redirect_uri,
    }
    valores.update(cambios)
    return Settings(**valores)


@pytest.mark.parametrize("secreto", ["change-me-in-production", "corto", "CHANGEME"])
def test_no_se_arranca_con_un_secreto_de_ejemplo_o_corto(secreto):
    """Un despliegue con el secreto del `.env.example` funciona igual de bien y
    no da ninguna senal, hasta que alguien firma el token que quiera."""
    with pytest.raises(ValidationError):
        _ajustes_con(jwt_secret=secreto)


def test_la_clave_de_cifrado_tambien_se_comprueba():
    with pytest.raises(ValidationError):
        _ajustes_con(encryption_key="generate-with-fernet-generate-key")


def test_un_secreto_propio_y_largo_se_acepta():
    _ajustes_con(jwt_secret="x" * 32)  # no debe lanzar


# --------------------------------------------------------------------------
# Tamano del cuerpo de la peticion
# --------------------------------------------------------------------------


def test_un_cuerpo_desmedido_se_rechaza_sin_leerlo():
    """Sin tope, una sola peticion reserva toda la memoria del proceso antes de
    que nadie mire lo que trae."""
    respuesta = client.post(
        "/api/auth/login",
        content=b"x" * (MAX_REQUEST_BYTES + 1),
        headers={"Content-Type": "application/json"},
    )
    assert respuesta.status_code == 413


def test_un_cuerpo_normal_pasa():
    respuesta = client.post(
        "/api/auth/login", json={"email": _EMAIL, "password": "no-existe-esta-cuenta"}
    )
    assert respuesta.status_code == 401


# --------------------------------------------------------------------------
# Rotacion del token de refresco
# --------------------------------------------------------------------------


def test_cada_renovacion_entrega_un_token_de_refresco_nuevo():
    """Sin rotar, un token robado valia los 30 dias enteros."""
    tokens = _crear_sesion()

    renovado = client.post(
        "/api/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
    ).json()

    assert renovado["refresh_token"]
    assert renovado["refresh_token"] != tokens["refresh_token"]
    assert client.post(
        "/api/auth/refresh", json={"refresh_token": renovado["refresh_token"]}
    ).status_code == 200


def test_el_token_anterior_deja_de_valer_pasada_la_gracia():
    """Es el punto de rotar: el que se uso queda anulado. Se le acepta unos
    segundos por si dos pestanas renuevan a la vez, y despues no."""
    tokens = _crear_sesion()
    client.post("/api/auth/refresh", json={"refresh_token": tokens["refresh_token"]})

    db = SessionLocal()
    try:
        fila = db.scalar(
            select(RefreshToken).where(
                RefreshToken.token_hash == session_service._hash(tokens["refresh_token"])
            )
        )
        assert fila.revoked is True
        assert fila.rotated_at is not None
        # Se envejece la rotacion para no esperar medio minuto en un test.
        fila.rotated_at = datetime.now(timezone.utc) - timedelta(
            seconds=session_service.GRACE_SECONDS + 1
        )
        db.commit()
    finally:
        db.close()

    caducado = client.post("/api/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert caducado.status_code == 401


def test_dos_pestanas_renovando_a_la_vez_no_se_echan():
    """Dentro de la ventana de gracia el anterior sigue sirviendo: dos pestanas
    renovando a la vez no son un ataque, y sin margen la segunda se encontraria
    la sesion cerrada."""
    tokens = _crear_sesion()

    primera = client.post("/api/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    segunda = client.post("/api/auth/refresh", json={"refresh_token": tokens["refresh_token"]})

    assert primera.status_code == 200
    assert segunda.status_code == 200


def test_cerrar_sesion_corta_tambien_la_ventana_de_gracia():
    """Si no, un token recien rotado seguiria sirviendo medio minuto despues de
    cerrar sesion, que es justo lo que cerrar sesion promete que no pasa."""
    tokens = _crear_sesion()
    client.post("/api/auth/refresh", json={"refresh_token": tokens["refresh_token"]})

    client.post("/api/auth/logout", json={"refresh_token": tokens["refresh_token"]})

    despues = client.post("/api/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert despues.status_code == 401


# --------------------------------------------------------------------------
# La sesion viaja en cookies httpOnly
# --------------------------------------------------------------------------


def _cookies_de_login():
    """Hace login con un cliente limpio y devuelve las cookies tal cual salen.

    Cliente propio: el compartido conserva las cookies entre pruebas, y aqui
    hace falta ver exactamente lo que manda el servidor en esta respuesta.
    """
    limpio = TestClient(app)
    limpio.post("/api/auth/register", json={"accept_privacy": True, "email": _EMAIL, "password": _PASSWORD})
    respuesta = limpio.post(
        "/api/auth/login", json={"email": _EMAIL, "password": _PASSWORD}
    )
    assert respuesta.status_code == 200
    return limpio, respuesta


@pytest.mark.parametrize("cookie", ["qr_access", "qr_refresh"])
def test_los_tokens_van_en_cookies_que_javascript_no_puede_leer(cookie):
    """En localStorage bastaba un XSS para llevarse 30 dias de sesion."""
    _, respuesta = _cookies_de_login()
    cabecera = next(
        valor
        for clave, valor in respuesta.headers.multi_items()
        if clave.lower() == "set-cookie" and valor.startswith(f"{cookie}=")
    )
    assert "HttpOnly" in cabecera
    # Sin SameSite, un formulario de otro sitio podria actuar en nombre del
    # usuario: el navegador adjuntaria la cookie igualmente.
    assert "SameSite=lax" in cabecera or "SameSite=Lax" in cabecera


def test_la_marca_de_sesion_si_es_legible_y_no_es_una_credencial():
    """La interfaz necesita saber si hay sesion para redirigir. Esa marca no
    sirve para autenticarse: no lleva ningun token."""
    _, respuesta = _cookies_de_login()
    marca = next(
        valor
        for clave, valor in respuesta.headers.multi_items()
        if clave.lower() == "set-cookie" and valor.startswith("qr_sesion=")
    )
    assert "HttpOnly" not in marca
    assert marca.startswith("qr_sesion=1;")


def test_la_sesion_en_cookie_autentica_sin_cabecera_authorization():
    limpio, _ = _cookies_de_login()
    assert limpio.get("/api/usage").status_code == 200


def test_renovar_por_cookie_no_devuelve_los_tokens_en_el_cuerpo():
    """Un XSS no puede leer la cookie httpOnly, pero el navegador la adjunta
    por el. Si /refresh devolviera los tokens, le bastaria con llamar y leer la
    respuesta, y las cookies no habrian servido de nada."""
    limpio, _ = _cookies_de_login()

    renovado = limpio.post("/api/auth/refresh")

    assert renovado.status_code == 200
    assert renovado.json() == {"access_token": None, "token_type": "bearer", "refresh_token": None}
    # Pero la sesion si se renovo: llegan cookies nuevas y siguen valiendo.
    assert limpio.get("/api/usage").status_code == 200


def test_cerrar_sesion_borra_las_cookies():
    limpio, _ = _cookies_de_login()

    salida = limpio.post("/api/auth/logout")

    assert salida.status_code == 204
    assert limpio.get("/api/usage").status_code == 401
