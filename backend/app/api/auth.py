import uuid
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.config import get_settings
from app.core.security import create_access_token, hash_password, verify_password
from app.models.user import User
from app.schemas.auth import LoginRequest, RegisterRequest, TokenResponse
from app.services import github_service
from app.utils.crypto import encrypt_token

router = APIRouter(prefix="/api/auth", tags=["auth"])

GITHUB_AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
GITHUB_OAUTH_SCOPES = "public_repo read:user user:email"

# Computado una sola vez, en import, para que el costo de bcrypt se pague
# igual en el path de "usuario no existe" que en el de "password incorrecta"
# y no se pueda distinguir por tiempo de respuesta cual email esta registrado.
_DUMMY_PASSWORD_HASH = hash_password("dummy-password-for-timing-equalization")


@router.post("/register", status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest, db: Session = Depends(get_db)) -> dict:
    existing = db.scalar(select(User).where(User.email == payload.email))
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="email already registered")

    user = User(id=uuid.uuid4(), email=payload.email, password_hash=hash_password(payload.password))
    db.add(user)
    db.commit()
    db.refresh(user)
    return {"id": str(user.id), "email": user.email}


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    user = db.scalar(select(User).where(User.email == payload.email))
    if user is None or user.password_hash is None:
        verify_password(payload.password, _DUMMY_PASSWORD_HASH)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid credentials")

    if not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid credentials")

    return TokenResponse(access_token=create_access_token(user.id))


# SEGURIDAD (pendiente, Fase futura): este endpoint no genera ni valida el
# parametro `state` de OAuth 2.0, que es la proteccion estandar contra CSRF
# en este flujo. Debe implementarse antes de exponer el servicio en
# produccion (ver tambien el comentario en github_callback mas abajo).
@router.get("/github/login")
def github_login() -> dict:
    settings = get_settings()
    query = urlencode(
        {
            "client_id": settings.github_client_id,
            "redirect_uri": settings.github_oauth_redirect_uri,
            "scope": GITHUB_OAUTH_SCOPES,
        }
    )
    return {"authorization_url": f"{GITHUB_AUTHORIZE_URL}?{query}"}


# SEGURIDAD (pendiente, Fase futura): este callback no valida el parametro
# `state` de OAuth 2.0, que es la proteccion estandar contra CSRF en este
# flujo. Debe implementarse antes de exponer el servicio en produccion.
@router.get("/github/callback", response_model=TokenResponse)
def github_callback(code: str, db: Session = Depends(get_db)) -> TokenResponse:
    github_token = github_service.exchange_code_for_token(code)
    github_user = github_service.fetch_github_user(github_token)
    email = github_service.fetch_github_primary_email(github_token)

    user = db.scalar(select(User).where(User.github_id == github_user["id"]))
    if user is None:
        user = User(id=uuid.uuid4(), email=email, github_id=github_user["id"])

    user.github_username = github_user["login"]
    user.avatar_url = github_user.get("avatar_url")
    user.github_access_token_encrypted = encrypt_token(github_token)
    db.add(user)
    db.commit()
    db.refresh(user)

    return TokenResponse(access_token=create_access_token(user.id))
