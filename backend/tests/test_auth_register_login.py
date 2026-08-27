import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete

from app.core.database import SessionLocal
from app.main import app
from app.models.user import User

client = TestClient(app)

TEST_EMAILS = ["juan@example.com", "maria@example.com", "dup@example.com"]


@pytest.fixture(autouse=True)
def _clean_test_users():
    """Delete the fixed test emails before and after each test so the suite
    is repeatable across runs against the real qalitiradar_test database."""

    def _delete():
        db = SessionLocal()
        try:
            db.execute(delete(User).where(User.email.in_(TEST_EMAILS)))
            db.commit()
        finally:
            db.close()

    _delete()
    yield
    _delete()


def test_register_then_login_succeeds():
    register_response = client.post(
        "/api/auth/register", json={"email": "juan@example.com", "password": "s3cur3-passw0rd"}
    )
    assert register_response.status_code == 201
    assert register_response.json()["email"] == "juan@example.com"

    login_response = client.post(
        "/api/auth/login", json={"email": "juan@example.com", "password": "s3cur3-passw0rd"}
    )
    assert login_response.status_code == 200
    assert "access_token" in login_response.json()


def test_login_with_wrong_password_returns_401():
    client.post("/api/auth/register", json={"email": "maria@example.com", "password": "correct-password"})
    response = client.post("/api/auth/login", json={"email": "maria@example.com", "password": "wrong-password"})
    assert response.status_code == 401


def test_register_with_duplicate_email_returns_409():
    client.post("/api/auth/register", json={"email": "dup@example.com", "password": "password-one"})
    response = client.post("/api/auth/register", json={"email": "dup@example.com", "password": "password-two"})
    assert response.status_code == 409
