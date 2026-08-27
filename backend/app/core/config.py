from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str
    redis_url: str
    jwt_secret: str
    jwt_algorithm: str = "HS256"
    jwt_access_expire_minutes: int = 15
    jwt_refresh_expire_days: int = 30
    encryption_key: str
    github_client_id: str
    github_client_secret: str
    github_oauth_redirect_uri: str


@lru_cache
def get_settings() -> Settings:
    return Settings()
