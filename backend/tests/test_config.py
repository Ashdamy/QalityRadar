from app.core.config import get_settings


def test_settings_loads_from_env():
    settings = get_settings()
    assert settings.jwt_algorithm == "HS256"
    assert settings.jwt_access_expire_minutes == 15
    assert settings.database_url.startswith("postgresql+psycopg://")
    # These aren't class defaults -- they only end up on `settings` if env
    # loading actually happened, using the values conftest.py sets.
    assert settings.redis_url == "redis://localhost:6379/0"
    assert settings.github_client_id == "test-client-id"
    assert settings.github_oauth_redirect_uri == "http://localhost:8000/api/auth/github/callback"
