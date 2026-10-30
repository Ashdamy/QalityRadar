from functools import lru_cache

from pydantic import field_validator, model_validator
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

    # Medicion en navegador real (Lighthouse + axe-core) de los analisis de
    # URL. Apagada por defecto: necesita la imagen `navegador/` construida y
    # la red `qalitiradar-navegador` creada (ver docs/SECURITY.md). Sin ella,
    # el analisis de URL es solo estatico, como siempre.
    navegador_real: bool = False
    navegador_imagen: str = "qaliti/navegador:latest"
    navegador_red: str = "qalitiradar-navegador"

    # En produccion se pone a false. La documentacion interactiva es comodisima
    # mientras se desarrolla, pero publicada regala el mapa completo de la API
    # a cualquiera: cada ruta, cada parametro y cada forma de respuesta. No es
    # una vulnerabilidad por si sola, pero le ahorra a un atacante todo el
    # trabajo de reconocimiento.
    enable_api_docs: bool = True

    # En produccion, true: la cookie de sesion solo viaja por HTTPS. En local
    # tiene que ser false o el navegador no la guarda, porque el desarrollo va
    # por HTTP y una cookie `Secure` sobre HTTP se descarta en silencio.
    cookie_secure: bool = False

    # Direccion publica de la aplicacion. Se usa para construir la URL de la
    # insignia que el usuario pega en su README, asi que en produccion tiene
    # que ser el dominio real: si apunta a localhost, la imagen no carga en
    # ningun sitio salvo en la maquina de quien la genero.
    public_base_url: str = "http://localhost:8000"

    # Direccion del frontend. El enlace de verificacion del correo apunta ahi,
    # asi que en produccion tiene que ser el dominio real.
    frontend_base_url: str = "http://localhost:3000"

    # Servidor de correo para el enlace de verificacion. Sin `smtp_host` no se
    # envia nada y nadie que se registre con contrasena puede entrar: en local
    # lo cubre el Mailpit del docker-compose.
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    # Mailpit no habla TLS; cualquier proveedor real si, y sin el la contrasena
    # del SMTP viajaria en claro.
    smtp_starttls: bool = True
    mail_from: str = "QalitiRadar <no-reply@localhost>"

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

    @model_validator(mode="after")
    def _cookies_seguras_si_hay_https(self) -> "Settings":
        """Si la aplicacion se sirve por HTTPS, la cookie de sesion tiene que ser `Secure`.

        Con `COOKIE_SECURE=false` en produccion todo funciona y nada avisa:
        simplemente el navegador manda la sesion tambien por HTTP, en claro,
        a quien la pida. Como con los secretos de ejemplo, mejor no arrancar.
        """
        publicas = (self.frontend_base_url, self.public_base_url, self.github_oauth_redirect_uri)
        if not self.cookie_secure and any(url.startswith("https://") for url in publicas):
            raise ValueError(
                "la aplicacion usa direcciones https pero COOKIE_SECURE=false: "
                "la sesion viajaria tambien por HTTP. Pon COOKIE_SECURE=true"
            )
        return self

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
