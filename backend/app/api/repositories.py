import uuid

from cryptography.fernet import InvalidToken
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from datetime import datetime, timedelta, timezone

from pydantic import BaseModel, Field

from app.api.deps import get_current_user, get_db
from app.models.analysis import Analysis
from app.models.repository import Repository
from app.models.user import User
from app.schemas.repository import RepositoryOut
from app.services import github_service
from app.services.monitor_service import fetch_latest_commit_sha
from app.services.repo_service import validate_branch
from app.services.rate_limit_service import RateLimitExceeded, check_and_reserve
from app.tasks import queue_repository_analysis
from app.utils.crypto import decrypt_token

router = APIRouter(prefix="/api/repositories", tags=["repositories"])

# Pasado este tiempo se vuelve a analizar aunque el commit no haya cambiado.
# El codigo es el mismo, pero el informe no: las vulnerabilidades conocidas de
# las dependencias las publica OSV cuando le toca, no cuando alguien commitea.
REUSE_WINDOW_HOURS = 24


class AnalyzeRequest(BaseModel):
    # Sin rama, la de por defecto del repositorio.
    # Git admite nombres largos, pero no tanto; la forma la valida el clonado.
    branch: str | None = Field(default=None, max_length=255)
    # Para cuando el usuario quiere un informe nuevo del mismo commit.
    force: bool = False


@router.get("", response_model=list[RepositoryOut])
def list_repositories(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[RepositoryOut]:
    if current_user.github_access_token_encrypted is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="GitHub account not connected")

    try:
        token = decrypt_token(current_user.github_access_token_encrypted)
    except InvalidToken as exc:
        # ENCRYPTION_KEY was rotated (or the stored value is otherwise
        # undecryptable): the stored token is unusable. Same message and
        # status as the "no token at all" case above, so the client's
        # remedy (reconnect GitHub) is identical either way.
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="GitHub account not connected"
        ) from exc

    # Los repositorios se persisten al listarlos: el analisis se dispara contra
    # nuestro propio id, no contra el numerico de GitHub, para que un analisis
    # siga apuntando al mismo repositorio aunque cambie de nombre alli.
    stored = _sync_repositories(db, current_user, github_service.list_public_repos(token))

    return [
        RepositoryOut(
            id=str(repo.id),
            name=repo.name,
            full_name=repo.full_name,
            is_private=repo.is_private,
            last_analyzed_at=(
                repo.last_analyzed_at.isoformat() if repo.last_analyzed_at else None
            ),
        )
        for repo in stored
    ]


def _sync_repositories(db: Session, user: User, github_repos: list[dict]) -> list[Repository]:
    existing = {
        repo.github_id: repo
        for repo in db.scalars(select(Repository).where(Repository.user_id == user.id)).all()
    }

    synced: list[Repository] = []
    for payload in github_repos:
        repo = existing.get(payload["id"])
        if repo is None:
            repo = Repository(
                id=uuid.uuid4(),
                user_id=user.id,
                github_id=payload["id"],
                name=payload["name"],
                full_name=payload["full_name"],
                default_branch=payload.get("default_branch") or "main",
                is_private=payload["private"],
            )
            db.add(repo)
        else:
            # El repositorio puede haberse renombrado o cambiado de rama por
            # defecto desde el ultimo listado.
            repo.name = payload["name"]
            repo.full_name = payload["full_name"]
            repo.default_branch = payload.get("default_branch") or repo.default_branch
            repo.is_private = payload["private"]
        synced.append(repo)

    db.commit()
    for repo in synced:
        db.refresh(repo)
    return synced


@router.post("/{repository_id}/analyze", status_code=status.HTTP_202_ACCEPTED)
def analyze_repository(
    repository_id: uuid.UUID,
    payload: AnalyzeRequest | None = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    repository = db.get(Repository, repository_id)
    # Se responde 404 tanto si no existe como si pertenece a otro usuario, para
    # no revelar que repositorios hay en cuentas ajenas.
    if repository is None or repository.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="repositorio no encontrado")
    if repository.is_private:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="solo se analizan repositorios publicos",
        )

    rama = None
    if payload is not None and payload.branch:
        try:
            rama = validate_branch(payload.branch)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="nombre de rama no valido"
            ) from exc

    ya_analizado = _analisis_reutilizable(db, repository, rama, current_user)
    if ya_analizado is not None and not (payload and payload.force):
        # Mismo commit y reciente: repetirlo daria la misma nota gastando otro
        # hueco de cuota. Se devuelve el que ya existe, y 200 en vez de 202
        # porque no hay nada encolado.
        return {"analysis_id": str(ya_analizado.id), "reused": True}

    analysis_id = uuid.uuid4()
    reservar_o_429(current_user.id, analysis_id)

    analysis = Analysis(
        id=analysis_id,
        user_id=current_user.id,
        repository_id=repository.id,
        analysis_type="repository",
        status="pending",
        branch=rama,
    )
    db.add(analysis)
    db.commit()

    queue_repository_analysis(str(analysis.id))
    return {"analysis_id": str(analysis.id), "reused": False}


def _analisis_reutilizable(
    db: Session, repository: Repository, rama: str | None, user: User
) -> Analysis | None:
    """El ultimo analisis terminado, si sigue valiendo para el estado de hoy.

    Vale si es del mismo commit que la punta de la rama y es reciente. Lo de
    reciente importa: el codigo no ha cambiado, pero las vulnerabilidades
    conocidas de sus dependencias si pueden haberlo hecho.

    Ante cualquier duda —no se puede preguntar a GitHub, no hay token, la rama
    pedida no es la de siempre— devuelve None y se analiza. Reutilizar de mas
    daria un informe desactualizado sin avisar; analizar de mas solo cuesta un
    hueco de cuota.
    """
    if rama is not None and rama != repository.default_branch:
        return None
    if user.github_access_token_encrypted is None:
        return None

    try:
        token = decrypt_token(user.github_access_token_encrypted)
        sha = fetch_latest_commit_sha(repository.full_name, token)
    except Exception:  # noqa: BLE001
        return None
    if sha is None:
        return None

    desde = datetime.now(timezone.utc) - timedelta(hours=REUSE_WINDOW_HOURS)
    return db.scalar(
        select(Analysis)
        .where(
            Analysis.repository_id == repository.id,
            Analysis.status == "completed",
            Analysis.commit_hash == sha,
            Analysis.created_at >= desde,
        )
        .order_by(Analysis.created_at.desc())
        .limit(1)
    )


def reservar_o_429(user_id, analysis_id) -> None:
    """Comprueba los limites de uso antes de crear y encolar nada.

    Va aqui y no en el worker porque un 202 para algo que despues se descarta
    en silencio seria mentir al cliente.
    """
    try:
        check_and_reserve(user_id, str(analysis_id))
    except RateLimitExceeded as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=exc.message,
            headers={"Retry-After": str(exc.retry_after_seconds)},
        ) from exc
