from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, func, select

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.main import app
from app.models.user import User
from app.services import github_service
from app.services.oauth_state_service import issue_state

client = TestClient(app)

# Github ids used by this test module. Fixed (not random) so assertions stay
# deterministic, but cleaned up before/after each test (same pattern as
# tests/test_auth_register_login.py) so repeated runs against the real
# qalitiradar_test database always start from a clean slate and exercise the
# "new user" path rather than silently degrading into the "existing user"
# path.
TEST_GITHUB_IDS = [123456, 654321, 789012]

# Email used by the account-linking tests below: registered via password
# first, then "claimed" by a GitHub identity with the same primary email.
LINK_EMAIL = "link-existing@example.com"


@pytest.fixture(autouse=True)
def _clean_test_users():
    def _delete():
        db = SessionLocal()
        try:
            db.execute(delete(User).where(User.github_id.in_(TEST_GITHUB_IDS)))
            db.execute(delete(User).where(User.email == LINK_EMAIL))
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

    response = client.get(
        "/api/auth/github/callback",
        params={"code": "any-code", "state": issue_state()},
    )

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

    first_response = client.get(
        "/api/auth/github/callback",
        params={"code": "code-one", "state": issue_state()},
    )
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

    second_response = client.get(
        "/api/auth/github/callback",
        params={"code": "code-two", "state": issue_state()},
    )
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


def test_github_callback_links_existing_password_account_by_email(monkeypatch):
    """If the caller already has a password-registered account, and then
    authenticates via GitHub with an identity whose primary email matches
    that account, the callback must LINK the existing row (set its
    github_id/github_username/avatar_url/github_access_token_encrypted)
    instead of inserting a second row -- which would otherwise violate the
    users.email UNIQUE constraint and surface as an unhandled 500,
    permanently locking that person out of GitHub login."""

    register_response = client.post(
        "/api/auth/register", json={"email": LINK_EMAIL, "password": "s3cur3-passw0rd"}
    )
    assert register_response.status_code == 201

    monkeypatch.setattr(github_service, "exchange_code_for_token", lambda code: "gho_fake_token_link")
    monkeypatch.setattr(
        github_service,
        "fetch_github_user",
        lambda token: {"id": 789012, "login": "linked-dev", "avatar_url": "https://avatars.example/linked"},
    )
    monkeypatch.setattr(github_service, "fetch_github_primary_email", lambda token: LINK_EMAIL)

    response = client.get(
        "/api/auth/github/callback",
        params={"code": "any-code", "state": issue_state()},
    )

    assert response.status_code == 200
    assert "access_token" in response.json()

    db = SessionLocal()
    try:
        count = db.scalar(select(func.count()).select_from(User).where(User.email == LINK_EMAIL))
        linked_user = db.scalar(select(User).where(User.email == LINK_EMAIL))
    finally:
        db.close()

    # Exactly one row with this email -- no duplicate was inserted.
    assert count == 1
    assert linked_user.github_id == 789012
    assert linked_user.github_username == "linked-dev"
    assert linked_user.github_access_token_encrypted is not None
    # Linking must not wipe the password login: the account should now
    # support both auth methods.
    assert linked_user.password_hash is not None


def test_github_login_returns_authorization_url_with_exact_scopes():
    response = client.get("/api/auth/github/login")

    assert response.status_code == 200
    body = response.json()
    assert "authorization_url" in body

    parsed = urlparse(body["authorization_url"])
    assert f"{parsed.scheme}://{parsed.netloc}{parsed.path}" == "https://github.com/login/oauth/authorize"

    query = parse_qs(parsed.query)
    # Exactly the three required scopes, no more, no less.
    assert query["scope"] == ["public_repo read:user user:email"]
    assert query["client_id"] == [get_settings().github_client_id]
    # client_id must come from the test env (conftest.py), never the real
    # credentials from backend/.env.
    assert query["client_id"] == ["test-client-id"]
    assert query["redirect_uri"] == [get_settings().github_oauth_redirect_uri]


def test_github_callback_with_bad_verification_code_returns_400(monkeypatch):
    """GitHub's token endpoint answers HTTP 200 with an error body (e.g. a
    reused or expired `code`), so raise_for_status() alone can't catch it —
    the missing access_token must be turned into a 400, not surfaced as
    whatever downstream KeyError/500 would otherwise happen."""

    def fake_request(method, url, **kwargs):
        return httpx.Response(200, json={"error": "bad_verification_code"}, request=httpx.Request(method, url))

    monkeypatch.setattr(github_service.httpx, "request", fake_request)

    response = client.get(
        "/api/auth/github/callback",
        params={"code": "already-used-code", "state": issue_state()},
    )

    assert response.status_code == 400
    detail = response.json()["detail"]
    assert detail == "invalid or expired GitHub authorization code"
    # Never echo GitHub's raw error body or the submitted code back to the caller.
    assert "bad_verification_code" not in response.text
    assert "already-used-code" not in response.text


def test_github_callback_with_no_emails_returns_400(monkeypatch):
    """GitHub's /user/emails can return an empty list. The old code did
    `next((e for e in emails if e.get("primary")), emails[0])`, which
    evaluates emails[0] eagerly and raises IndexError before next() ever
    runs -- surfacing as an unhandled 500. This must be a clean 400
    instead."""

    def fake_request(method, url, **kwargs):
        if url == github_service.GITHUB_OAUTH_TOKEN_URL:
            return httpx.Response(200, json={"access_token": "gho_fake_token"}, request=httpx.Request(method, url))
        if url.endswith("/user/emails"):
            return httpx.Response(200, json=[], request=httpx.Request(method, url))
        if url.endswith("/user"):
            return httpx.Response(200, json={"id": 999999, "login": "no-email-dev"}, request=httpx.Request(method, url))
        raise AssertionError(f"unexpected url in test: {url}")

    monkeypatch.setattr(github_service.httpx, "request", fake_request)

    response = client.get(
        "/api/auth/github/callback",
        params={"code": "any-code", "state": issue_state()},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "GitHub account has no accessible email"


def test_github_callback_with_github_http_error_returns_502(monkeypatch):
    """Any non-2xx from GitHub (rate limit, revoked app, etc.) or a network
    error must surface as a safe 502, not an unhandled 500."""

    def fake_request(method, url, **kwargs):
        return httpx.Response(503, text="upstream rate limited", request=httpx.Request(method, url))

    monkeypatch.setattr(github_service.httpx, "request", fake_request)

    response = client.get(
        "/api/auth/github/callback",
        params={"code": "any-code", "state": issue_state()},
    )

    assert response.status_code == 502
    detail = response.json()["detail"]
    assert detail == "GitHub is unavailable"
    # Never echo GitHub's raw response body into the error detail.
    assert "upstream rate limited" not in response.text
