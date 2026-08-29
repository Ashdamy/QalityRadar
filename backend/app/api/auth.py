import uuid
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.config import get_settings
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_refresh_token,
    hash_password,
    verify_password,
)
from app.models.user import User
from app.schemas.auth import (
    LoginRequest,
    LogoutRequest,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
)
from app.services import github_service
from app.services import session_service
from app.services.rate_limit_service import RateLimitExceeded, check_registration_ip
from app.services.oauth_state_service import consume_state, issue_state
from app.utils.crypto import encrypt_token

router = APIRouter(prefix="/api/auth", tags=["auth"])

GITHUB_AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
GITHUB_OAUTH_SCOPES = "public_repo read:user user:email"

# Computado una sola vez, en import, para que el costo de bcrypt se pague
# igual en el path de "usuario no existe" que en el de "password incorrecta"
# y no se pueda distinguir por tiempo de respuesta cual email esta registrado.
_DUMMY_PASSWORD_HASH = hash_password("dummy-password-for-timing-equalization")


@router.post("/register", status_code=status.HTTP_201_CREATED)
def register(
    payload: RegisterRequest, request: Request, db: Session = Depends(get_db)
) -> dict:
    # Los limites de uso son por cuenta, asi que sin esto basta con crear
    # varias desde el mismo sitio para saltarselos.
    try:
        check_registration_ip(request.client.host if request.client else None)
    except RateLimitExceeded as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=exc.message,
            headers={"Retry-After": str(exc.retry_after_seconds)},
        ) from exc

    existing = db.scalar(select(User).where(User.email == payload.email))
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="email already registered")

    user = User(id=uuid.uuid4(), email=payload.email, password_hash=hash_password(payload.password))
    db.add(user)
    try:
        db.commit()
    except IntegrityError as exc:
        # La comprobacion de arriba no basta: entre el SELECT y el COMMIT otra
        # peticion puede haber insertado el mismo email. La restriccion unica
        # de la tabla es la que decide, y aqui se traduce a la respuesta que
        # corresponde en vez de dejar escapar un 500.
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="email already registered"
        ) from exc
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

    return _emitir_sesion(db, user.id)


@router.get("/github/login")
def github_login() -> dict:
    settings = get_settings()
    query = urlencode(
        {
            "client_id": settings.github_client_id,
            "redirect_uri": settings.github_oauth_redirect_uri,
            "scope": GITHUB_OAUTH_SCOPES,
            # Ata la vuelta de GitHub a esta ida concreta. Sin el, un tercero
            # podria forzar el callback con un `code` suyo y dejar su cuenta
            # de GitHub vinculada a la sesion de la victima.
            "state": issue_state(),
        }
    )
    return {"authorization_url": f"{GITHUB_AUTHORIZE_URL}?{query}"}


@router.get("/github/callback", response_model=TokenResponse)
def github_callback(
    code: str, state: str | None = None, db: Session = Depends(get_db)
) -> TokenResponse:
    # Se valida y se gasta antes de tocar GitHub: si el `state` no salio de
    # aqui, no hay nada que canjear.
    if not consume_state(state):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="la solicitud de autenticacion no es valida o ha caducado; vuelve a intentarlo",
        )

    github_token = github_service.exchange_code_for_token(code)
    github_user = github_service.fetch_github_user(github_token)
    email = github_service.fetch_github_primary_email(github_token)

    user = db.scalar(select(User).where(User.github_id == github_user["id"]))
    if user is None:
        # No row is linked to this GitHub account yet. The GitHub primary
        # email may already belong to a password-registered account, in
        # which case we must LINK that existing row instead of inserting a
        # new one — otherwise db.commit() below violates the users.email
        # UNIQUE constraint (unhandled IntegrityError -> 500), and that
        # person could never authenticate via GitHub.
        user = db.scalar(select(User).where(User.email == email))
        if user is None:
            user = User(id=uuid.uuid4(), email=email, github_id=github_user["id"])
        else:
            user.github_id = github_user["id"]

    user.github_username = github_user["login"]
    user.avatar_url = github_user.get("avatar_url")
    user.github_access_token_encrypted = encrypt_token(github_token)
    db.add(user)
    db.commit()
    db.refresh(user)

    # Con GitHub tambien hace falta el token de refresco. Sin el, quien entraba
    # por aqui se quedaba sin sesion a los 15 minutos y no habia forma de
    # renovarla sin volver a pasar por GitHub.
    return _emitir_sesion(db, user.id)


def _emitir_sesion(db: Session, user_id: uuid.UUID) -> TokenResponse:
    """Crea la pareja de tokens y anota el de refresco como activo."""
    refresco = create_refresh_token(user_id)
    session_service.register_refresh_token(db, user_id, refresco)
    db.commit()
    return TokenResponse(
        access_token=create_access_token(user_id),
        refresh_token=refresco,
    )


@router.post("/refresh", response_model=TokenResponse)
def refresh(payload: RefreshRequest, db: Session = Depends(get_db)) -> TokenResponse:
    """Emite un token de acceso nuevo a partir del de refresco.

    No se rota el de refresco: rotarlo obliga a que dos pestanas renovando a la
    vez no se pisen, y una rotacion a medias deja al usuario fuera.
    """
    try:
        user_id = decode_refresh_token(payload.refresh_token)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="refresh token invalido"
        ) from exc

    # Que la firma sea valida no basta. Hay que comprobar que la sesion siga
    # abierta: si se cerro sesion, el token no debe servir aunque no haya
    # caducado.
    if not session_service.is_active(db, payload.refresh_token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="la sesion ya no esta activa"
        )

    # Y que la cuenta siga existiendo: son 30 dias de margen.
    if db.get(User, user_id) is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="refresh token invalido"
        )

    return TokenResponse(access_token=create_access_token(user_id))


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(payload: LogoutRequest, db: Session = Depends(get_db)) -> None:
    """Cierra la sesion de verdad, invalidando el token en el servidor.

    No exige sesion valida a proposito: si el token de acceso ya caduco, cerrar
    sesion tiene que seguir funcionando. Y no revela si el token existia, para
    que no sirva de oraculo.
    """
    session_service.revoke(db, payload.refresh_token)
    db.commit()
