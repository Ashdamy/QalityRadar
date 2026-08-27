from cryptography.fernet import InvalidToken
from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import get_current_user
from app.models.user import User
from app.schemas.repository import RepositoryOut
from app.services import github_service
from app.utils.crypto import decrypt_token

router = APIRouter(prefix="/api/repositories", tags=["repositories"])


@router.get("", response_model=list[RepositoryOut])
def list_repositories(current_user: User = Depends(get_current_user)) -> list[RepositoryOut]:
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
    repos = github_service.list_public_repos(token)
    return [
        RepositoryOut(id=str(repo["id"]), name=repo["name"], full_name=repo["full_name"], is_private=repo["private"])
        for repo in repos
    ]
