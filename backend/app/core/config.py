from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Un secreto corto se puede sacar por fuerza bruta a partir de un solo token
# firmado, sin tocar el servidor. Y con el secreto se firma un token para
# cualquier cuenta: es la llave de todas las sesiones.
MIN_SECRET_LENGTH = 32

# Los valores que trae `.env.example` para que arranque en local. Publicados,
# cualquiera que haya visto el repositorio conoce la llave.
SECRETOS_DE_EJEMPLO = {
    "change-me-in-production",
    "generate-with-fernet-generate-key",
    "changeme",
    "secret",
    "supersecret",
    "test",
}


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

    # Opcional: sin clave, los resumenes se generan con la plantilla de
    # respaldo, que produce un texto correcto con los mismos datos.
    huggingface_api_key: str = ""

    # En produccion se pone a false. La documentacion interactiva es comodisima
    # mientras se desarrolla, pero publicada regala el mapa completo de la API
    # a cualquiera: cada ruta, cada parametro y cada forma de respuesta. No es
    # una vulnerabilidad por si sola, pero le ahorra a un atacante todo el
    # trabajo de reconocimiento.
    enable_api_docs: bool = True

    @field_validator("jwt_secret", "encryption_key")
    @classmethod
    def _un_secreto_de_verdad(cls, valor: str, info) -> str:
        """Se comprueba al arrancar, no al usarse.

        Un despliegue con `JWT_SECRET=change-me-in-production` funciona
        perfectamente y no da ninguna senal: los tokens se firman, las sesiones
        abren y nadie se entera hasta que alguien firma el suyo. Mejor que la
        aplicacion no arranque a que arranque abierta.
        """
        limpio = (valor or "").strip()
        if limpio.lower() in SECRETOS_DE_EJEMPLO:
            raise ValueError(
                f"{info.field_name} sigue con el valor de ejemplo; genera uno propio "
                "antes de arrancar"
            )
        if len(limpio) < MIN_SECRET_LENGTH:
            raise ValueError(
                f"{info.field_name} debe tener al menos {MIN_SECRET_LENGTH} caracteres"
            )
        return limpio

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
