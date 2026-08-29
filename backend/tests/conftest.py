import os

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://qalitiradar:qalitiradar_dev@localhost:5433/qalitiradar_test")

# Guard against running this destructive test suite (it does `delete(User)`
# cleanups) against a real, non-test database. This must run before any
# fixture executes, so it lives here at import time, right after resolving
# DATABASE_URL. setdefault() above yields to any ambient env value (e.g. the
# compose `backend` service's DATABASE_URL, which points at the real
# `qalitiradar` database) so we can't just trust the default is in effect.
if not os.environ["DATABASE_URL"].endswith("_test"):
    raise RuntimeError(
        "DATABASE_URL does not point at a *_test database "
        f"(got {os.environ['DATABASE_URL']!r}). Refusing to run the test "
        "suite, which deletes rows, against what looks like a real "
        "database. Set DATABASE_URL to a database whose name ends in "
        "'_test' (e.g. qalitiradar_test)."
    )

os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("JWT_SECRET", "test-secret")
os.environ.setdefault("ENCRYPTION_KEY", "vxhb4mYBgiJ9hV5GKwlB7XZOeQQZLAuGayrkNp4UWNQ=")
os.environ.setdefault("GITHUB_CLIENT_ID", "test-client-id")
os.environ.setdefault("GITHUB_CLIENT_SECRET", "test-client-secret")
os.environ.setdefault("GITHUB_OAUTH_REDIRECT_URI", "http://localhost:8000/api/auth/github/callback")

import uuid

import pytest
from sqlalchemy import delete

from app.core.database import SessionLocal
from app.models.user import User
from app.utils.crypto import encrypt_token

# Fixed (not random) github_id/email so cleanup targets a deterministic row
# across runs against the real qalitiradar_test database, following the same
# pattern used in test_auth_register_login.py / test_github_oauth.py.
_FIXTURE_GITHUB_ID = 900000001
_FIXTURE_EMAIL = "fixture-github-user@example.com"


@pytest.fixture
def db_session_with_github_user():
    """Creates a User row that already went through GitHub OAuth: it has a
    github_id and a github_access_token_encrypted set via encrypt_token(...).
    Cleans up before and after so the fixture is repeatable across runs and
    safe to use from any test module in the suite."""

    def _delete():
        db = SessionLocal()
        try:
            db.execute(delete(User).where(User.github_id == _FIXTURE_GITHUB_ID))
            db.commit()
        finally:
            db.close()

    _delete()

    db = SessionLocal()
    try:
        user = User(
            id=uuid.uuid4(),
            email=_FIXTURE_EMAIL,
            github_id=_FIXTURE_GITHUB_ID,
            github_username="fixture-github-user",
            github_access_token_encrypted=encrypt_token("gho_fixture_fake_token"),
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        yield user
    finally:
        db.close()
        _delete()


@pytest.fixture(autouse=True)
def _sin_limite_de_registros_por_ip():
    """Todas las pruebas llegan desde la misma IP (`testclient`), asi que a
    partir del sexto registro saltaria el limite y fallarian por un motivo que
    no tiene nada que ver con lo que prueban.

    Se limpia el contador antes de cada una. El limite sigue activo en
    produccion, que es donde hace falta; ahi las IP son distintas de verdad.
    """
    from app.services import rate_limit_service as limites

    def _vaciar():
        try:
            cliente = limites._client()
            for clave in cliente.scan_iter("ratelimit:registrations:*"):
                cliente.delete(clave)
        except Exception:  # noqa: BLE001
            # Sin Redis hay pruebas que igualmente no pueden correr; no es
            # cosa de esta fixture decidirlo.
            pass

    _vaciar()
    yield
    _vaciar()
