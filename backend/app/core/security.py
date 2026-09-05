import uuid
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from app.core.config import get_settings

# bcrypt no acepta mas de 72 bytes. El registro ya lo rechaza en la capa de
# validacion, pero el login recibe lo que sea que escriban.
BCRYPT_MAX_BYTES = 72

# Los dos tipos de token se firman con el mismo secreto, asi que sin esta
# marca un token de refresco valdria como token de acceso: quien robara uno
# tendria 30 dias de acceso en vez de un solo canje.
ACCESS_TOKEN_TYPE = "access"
REFRESH_TOKEN_TYPE = "refresh"

# La sesion viaja en cookies httpOnly, no en localStorage: lo que JavaScript no
# puede leer, un XSS no puede robar. Antes bastaba con un `alert` inyectado
# para llevarse 30 dias de sesion.
COOKIE_ACCESS = "qr_access"
COOKIE_REFRESH = "qr_refresh"
# Esta si es legible desde JavaScript, y a proposito: no es una credencial,
# solo dice "hay sesion", que es lo que la interfaz necesita para saber si
# redirige al inicio. Robarla no sirve de nada.
COOKIE_SESION = "qr_sesion"


class InvalidTokenType(Exception):
    """El token es valido pero no es del tipo que el endpoint espera."""


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    """Comprueba la contrasena sin dejar que bcrypt propague excepciones.

    Una contrasena de mas de 72 bytes hace que bcrypt lance ValueError, y eso
    llegaba al cliente como un 500. No puede coincidir con ningun hash
    almacenado (el registro las rechaza), asi que la respuesta correcta es
    simplemente que no coincide.
    """
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except ValueError:
        return False


def _create_token(user_id: uuid.UUID, token_type: str, lifetime: timedelta) -> str:
    settings = get_settings()
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "type": token_type,
        # Identificador unico del token. Sin el, dos tokens del mismo usuario
        # creados en el mismo segundo salen identicos, porque `iat` y `exp`
        # tienen resolucion de segundos: al rotar el de refresco se emitia
        # literalmente el mismo token que se acababa de anular, y quedaban dos
        # filas con el mismo hash, una viva y otra no.
        "jti": uuid.uuid4().hex,
        "iat": now,
        "exp": now + lifetime,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def create_access_token(user_id: uuid.UUID) -> str:
    settings = get_settings()
    return _create_token(
        user_id,
        ACCESS_TOKEN_TYPE,
        timedelta(minutes=settings.jwt_access_expire_minutes),
    )


def create_refresh_token(user_id: uuid.UUID) -> str:
    settings = get_settings()
    return _create_token(
        user_id,
        REFRESH_TOKEN_TYPE,
        timedelta(days=settings.jwt_refresh_expire_days),
    )


def _decode(token: str, expected_type: str) -> uuid.UUID:
    settings = get_settings()
    payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    # Un token sin marca se rechaza. Hubo un periodo en que se trataba como
    # de acceso, para no cortar las sesiones abiertas al desplegar los tipos;
    # ese periodo ya paso, y mientras duro cualquier token sin `type` valia
    # como token de acceso.
    tipo = payload.get("type")
    if tipo != expected_type:
        raise InvalidTokenType(f"se esperaba un token de tipo {expected_type}, llego {tipo}")
    return uuid.UUID(payload["sub"])


def decode_access_token(token: str) -> uuid.UUID:
    return _decode(token, ACCESS_TOKEN_TYPE)


def decode_refresh_token(token: str) -> uuid.UUID:
    return _decode(token, REFRESH_TOKEN_TYPE)
