import uuid

from cryptography.fernet import InvalidToken
from fastapi.testclient import TestClient
from sqlalchemy import delete

from app.api import repositories as repositories_module
from app.core.database import SessionLocal
from app.core.security import create_access_token
from app.main import app
from app.models.user import User
from app.services import github_service

client = TestClient(app)

# Fixed email so this file's own extra fixture (a user without a GitHub
# token) is cleaned up deterministically, same pattern as every other test
# module in this suite.
NO_GITHUB_TOKEN_EMAIL = "repo-list-no-github@example.com"


def _delete_no_github_token_user():
    db = SessionLocal()
    try:
        db.execute(delete(User).where(User.email == NO_GITHUB_TOKEN_EMAIL))
        db.commit()
    finally:
        db.close()


def test_list_repositories_maps_is_private_field_through_faithfully(monkeypatch, db_session_with_github_user):
    user = db_session_with_github_user
    # Includes one private repo so the assertion below actually exercises
    # the is_private mapping instead of passing vacuously (this endpoint
    # delegates "public only" filtering to GitHub's visibility=public param
    # rather than filtering locally -- see list_public_repos -- so the
    # response should faithfully pass through whatever GitHub returns).
    monkeypatch.setattr(
        github_service, "list_public_repos",
        lambda token: [
            {"id": 1, "name": "qaliti-radar", "full_name": "juan/qaliti-radar", "private": False},
            {"id": 2, "name": "side-project", "full_name": "juan/side-project", "private": False},
            {"id": 3, "name": "secret-project", "full_name": "juan/secret-project", "private": True},
        ],
    )

    token = create_access_token(user.id)
    response = client.get("/api/repositories", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 3
    by_id = {repo["id"]: repo for repo in body}
    assert by_id["1"]["is_private"] is False
    assert by_id["2"]["is_private"] is False
    assert by_id["3"]["is_private"] is True


def test_list_repositories_without_token_returns_401():
    response = client.get("/api/repositories")
    assert response.status_code == 401


def test_list_repositories_with_malformed_header_returns_401():
    response = client.get("/api/repositories", headers={"Authorization": "not-a-bearer-header"})
    assert response.status_code == 401


def test_list_repositories_with_invalid_token_returns_401():
    response = client.get("/api/repositories", headers={"Authorization": "Bearer this.is.not-a-valid-jwt"})
    assert response.status_code == 401


def test_list_repositories_with_token_for_nonexistent_user_returns_401():
    # Valid JWT, correctly signed, but for a user id that has no row in the
    # database (e.g. deleted after the token was issued).
    token = create_access_token(uuid.uuid4())
    response = client.get("/api/repositories", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401


def test_list_repositories_with_undecryptable_token_returns_400(monkeypatch, db_session_with_github_user):
    """If ENCRYPTION_KEY was rotated (or the stored value is otherwise
    corrupt), decrypt_token raises cryptography.fernet.InvalidToken. This
    must not surface as an unhandled 500 -- it should be the same 400 the
    "no token at all" case returns, so the client's remedy (reconnect
    GitHub) is identical either way."""

    user = db_session_with_github_user

    def _raise_invalid_token(_encrypted):
        raise InvalidToken()

    monkeypatch.setattr(repositories_module, "decrypt_token", _raise_invalid_token)

    token = create_access_token(user.id)
    response = client.get("/api/repositories", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 400
    assert response.json()["detail"] == "GitHub account not connected"


def test_list_repositories_for_user_without_github_token_returns_400():
    _delete_no_github_token_user()
    db = SessionLocal()
    try:
        user = User(
            id=uuid.uuid4(),
            email=NO_GITHUB_TOKEN_EMAIL,
            password_hash="not-a-real-hash",
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        user_id = user.id
    finally:
        db.close()

    try:
        token = create_access_token(user_id)
        response = client.get("/api/repositories", headers={"Authorization": f"Bearer {token}"})

        assert response.status_code == 400
        assert response.json()["detail"] == "GitHub account not connected"
    finally:
        _delete_no_github_token_user()
