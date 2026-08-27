import uuid

from fastapi.testclient import TestClient
from sqlalchemy import delete

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


def test_list_repositories_returns_only_public_repos(monkeypatch, db_session_with_github_user):
    user = db_session_with_github_user
    monkeypatch.setattr(
        github_service, "list_public_repos",
        lambda token: [
            {"id": 1, "name": "qaliti-radar", "full_name": "juan/qaliti-radar", "private": False},
            {"id": 2, "name": "side-project", "full_name": "juan/side-project", "private": False},
        ],
    )

    token = create_access_token(user.id)
    response = client.get("/api/repositories", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 2
    assert all(repo["is_private"] is False for repo in body)


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
