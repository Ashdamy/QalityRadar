import os

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://qalitiradar:qalitiradar_dev@localhost:5433/qalitiradar_test")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("JWT_SECRET", "test-secret")
os.environ.setdefault("ENCRYPTION_KEY", "Zm9vYmFyYmF6cXV1eGZvb2JhcmJhenF1dXg=")
os.environ.setdefault("GITHUB_CLIENT_ID", "test-client-id")
os.environ.setdefault("GITHUB_CLIENT_SECRET", "test-client-secret")
os.environ.setdefault("GITHUB_OAUTH_REDIRECT_URI", "http://localhost:8000/api/auth/github/callback")
