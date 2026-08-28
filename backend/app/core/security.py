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
    # Los tokens emitidos antes de que existieran los tipos no llevan la
    # marca. Se tratan como de acceso, que es lo unico que se emitia entonces,
    # para no invalidar las sesiones abiertas al desplegar este cambio.
    tipo = payload.get("type", ACCESS_TOKEN_TYPE)
    if tipo != expected_type:
        raise InvalidTokenType(f"se esperaba un token de tipo {expected_type}, llego {tipo}")
    return uuid.UUID(payload["sub"])


def decode_access_token(token: str) -> uuid.UUID:
    return _decode(token, ACCESS_TOKEN_TYPE)


def decode_refresh_token(token: str) -> uuid.UUID:
    return _decode(token, REFRESH_TOKEN_TYPE)
