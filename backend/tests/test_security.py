import uuid
from datetime import datetime, timedelta, timezone

import jwt
import pytest
from jwt import InvalidTokenError

from app.core.config import get_settings
from app.core.security import create_access_token, decode_access_token, hash_password, verify_password


def test_hash_and_verify_password_roundtrip():
    hashed = hash_password("correct horse battery staple")
    assert verify_password("correct horse battery staple", hashed)
    assert not verify_password("wrong password", hashed)


def test_access_token_roundtrip():
    user_id = uuid.uuid4()
    token = create_access_token(user_id)
    assert decode_access_token(token) == user_id


def test_decode_rejects_tampered_payload():
    # Se altera el PAYLOAD, no el ultimo caracter de la firma. El ultimo
    # caracter base64url de la firma solo codifica bits parciales, asi que
    # cambiarlo puede decodificar a los mismos bytes y dejar el token valido
    # (test intermitente). Alterar el payload siempre invalida la firma.
    header, payload, signature = create_access_token(uuid.uuid4()).split(".")
    tampered_payload = payload[:-1] + ("a" if payload[-1] != "a" else "b")
    with pytest.raises(InvalidTokenError):
        decode_access_token(f"{header}.{tampered_payload}.{signature}")


def test_decode_rejects_token_signed_with_another_key():
    foreign_token = jwt.encode(
        {"sub": str(uuid.uuid4()), "exp": datetime.now(timezone.utc) + timedelta(minutes=15)},
        "una-clave-distinta-a-la-del-servicio",
        algorithm="HS256",
    )
    with pytest.raises(InvalidTokenError):
        decode_access_token(foreign_token)


def test_decode_rejects_expired_token():
    expired = jwt.encode(
        {"sub": str(uuid.uuid4()), "exp": datetime.now(timezone.utc) - timedelta(seconds=1)},
        get_settings().jwt_secret,
        algorithm=get_settings().jwt_algorithm,
    )
    with pytest.raises(InvalidTokenError):
        decode_access_token(expired)
