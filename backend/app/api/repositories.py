import uuid

from cryptography.fernet import InvalidToken
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.models.analysis import Analysis
from app.models.repository import Repository
from app.models.user import User
from app.schemas.repository import RepositoryOut
from app.services import github_service
from app.tasks import queue_repository_analysis
from app.utils.crypto import decrypt_token

router = APIRouter(prefix="/api/repositories", tags=["repositories"])


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

    analysis = Analysis(
        id=uuid.uuid4(),
        user_id=current_user.id,
        repository_id=repository.id,
        analysis_type="repository",
        status="pending",
    )
    db.add(analysis)
    db.commit()

    queue_repository_analysis(str(analysis.id))
    return {"analysis_id": str(analysis.id)}
