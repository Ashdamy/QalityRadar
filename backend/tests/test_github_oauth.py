import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, func, select

from app.core.database import SessionLocal
from app.main import app
from app.models.user import User
from app.services import github_service

client = TestClient(app)

# Github ids used by this test module. Fixed (not random) so assertions stay
# deterministic, but cleaned up before/after each test (same pattern as
# tests/test_auth_register_login.py) so repeated runs against the real
# qalitiradar_test database always start from a clean slate and exercise the
# "new user" path rather than silently degrading into the "existing user"
# path.
TEST_GITHUB_IDS = [123456, 654321]


@pytest.fixture(autouse=True)
def _clean_test_users():
    def _delete():
        db = SessionLocal()
        try:
            db.execute(delete(User).where(User.github_id.in_(TEST_GITHUB_IDS)))
            db.commit()
        finally:
            db.close()

    _delete()
    yield
    _delete()


def test_github_callback_creates_user_and_returns_token(monkeypatch):
    monkeypatch.setattr(github_service, "exchange_code_for_token", lambda code: "gho_fake_token")
    monkeypatch.setattr(
        github_service,
        "fetch_github_user",
        lambda token: {"id": 123456, "login": "juan-dev", "avatar_url": "https://avatars.example/juan"},
    )
    monkeypatch.setattr(github_service, "fetch_github_primary_email", lambda token: "juan-dev@example.com")

    response = client.get("/api/auth/github/callback", params={"code": "any-code"})

    assert response.status_code == 200
    assert "access_token" in response.json()


def test_github_callback_called_twice_updates_existing_user_without_duplicate(monkeypatch):
    """Calling the callback twice with the same GitHub identity must hit the
    "returning user" branch (user is not None) on the second call: it should
    update the existing row instead of creating a duplicate, and still
    return a valid app JWT."""

    monkeypatch.setattr(github_service, "exchange_code_for_token", lambda code: "gho_fake_token_first")
    monkeypatch.setattr(
        github_service,
        "fetch_github_user",
        lambda token: {"id": 654321, "login": "maria-dev", "avatar_url": "https://avatars.example/maria"},
    )
    monkeypatch.setattr(github_service, "fetch_github_primary_email", lambda token: "maria-dev@example.com")

    first_response = client.get("/api/auth/github/callback", params={"code": "code-one"})
    assert first_response.status_code == 200
    assert "access_token" in first_response.json()

    # Second call: same github_id, but a different token/avatar to simulate
    # a fresh OAuth round trip for a returning user.
    monkeypatch.setattr(github_service, "exchange_code_for_token", lambda code: "gho_fake_token_second")
    monkeypatch.setattr(
        github_service,
        "fetch_github_user",
        lambda token: {"id": 654321, "login": "maria-dev-renamed", "avatar_url": "https://avatars.example/maria2"},
    )

    second_response = client.get("/api/auth/github/callback", params={"code": "code-two"})
    assert second_response.status_code == 200
    assert "access_token" in second_response.json()

    db = SessionLocal()
    try:
        count = db.scalar(select(func.count()).select_from(User).where(User.github_id == 654321))
        updated_user = db.scalar(select(User).where(User.github_id == 654321))
    finally:
        db.close()

    assert count == 1
    assert updated_user.github_username == "maria-dev-renamed"
