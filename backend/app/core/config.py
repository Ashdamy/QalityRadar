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

    # Origenes autorizados para llamar a la API desde un navegador, separados
    # por comas. El navegador bloquea las peticiones del frontend si su origen
    # no esta aqui. En produccion debe apuntar al dominio real, nunca a "*",
    # porque la API responde con credenciales.
    cors_origins: str = "http://localhost:3000"

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
