"""Parametro `state` del flujo OAuth: proteccion contra CSRF.

Sin el, cualquiera puede provocar que la cuenta de GitHub de otra persona
quede vinculada a su sesion: basta con hacerle visitar un callback preparado
con un `code` propio. El `state` ata la vuelta de GitHub a la ida que salio de
aqui.

Se guarda en Redis, no en memoria del proceso, por dos motivos: sobrevive a un
reinicio del backend (si no, todo el mundo a medio autenticar recibiria un
error) y funciona con varias instancias detras de un balanceador, donde la ida
y la vuelta pueden caer en procesos distintos.

Cada `state` es de un solo uso: se borra al validarlo, asi que reproducir un
callback capturado no sirve de nada.
"""

import secrets

import redis

from app.core.config import get_settings

# Margen suficiente para autenticarse en GitHub sin prisa (incluido aprobar la
# aplicacion la primera vez), pero corto para que la ventana de ataque no
# quede abierta.
STATE_TTL_SECONDS = 600

_KEY_PREFIX = "oauth:state:"


def _client() -> redis.Redis:
    return redis.Redis.from_url(get_settings().redis_url)


def issue_state() -> str:
    """Genera un `state` imposible de adivinar y lo registra como pendiente."""
    state = secrets.token_urlsafe(32)
    _client().setex(f"{_KEY_PREFIX}{state}", STATE_TTL_SECONDS, "1")
    return state


def consume_state(state: str | None) -> bool:
    """Valida y gasta el `state`. Devuelve False si no era uno emitido aqui.

    El borrado y la comprobacion van en la misma operacion (`delete` devuelve
    cuantas claves borro), de modo que dos callbacks simultaneos con el mismo
    `state` no pueden pasar los dos.
    """
    if not state:
        return False
    return _client().delete(f"{_KEY_PREFIX}{state}") == 1
