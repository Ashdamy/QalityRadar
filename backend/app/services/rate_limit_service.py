"""Limites de uso por usuario, comprobados antes de encolar nada.

Cada analisis clona repositorios, levanta contenedores y hace peticiones
salientes. Sin limites, una sola cuenta puede agotar la maquina o convertir el
servicio en un amplificador de trafico hacia terceros.

La comprobacion va **antes** de encolar a proposito: si se hiciera en el
worker, el trabajo ya estaria aceptado y el usuario recibiria un 202 para algo
que luego se descarta en silencio.

Ventana deslizante, no contador por hora natural: con contadores fijos se
pueden lanzar 5 analisis a las 10:59 y otros 5 a las 11:00, que son 10 en dos
minutos. Se guarda el momento de cada analisis en un sorted set de Redis y se
cuentan los que caen dentro de la ventana.
"""

import time
import uuid

import redis

from app.core.config import get_settings

MAX_PER_HOUR = 5
MAX_PER_DAY = 20
# Dos a la vez por usuario: el sandbox reserva CPU y memoria, y varios en
# paralelo por cuenta dejarian sin turno a los demas.
MAX_CONCURRENT = 2

HOUR_SECONDS = 3600
DAY_SECONDS = 86400

# Los analisis automaticos de los monitores llevan su propia cuenta. Si
# compartieran la del usuario, un proyecto vigilado le consumiria los analisis
# manuales y se encontraria bloqueado sin haber hecho nada.
MONITOR_MAX_PER_HOUR = 10
MONITOR_MAX_PER_DAY = 40
# Uno cada vez: la vigilancia es trabajo de fondo y no debe competir con lo
# que el usuario esta esperando en pantalla.
MONITOR_MAX_CONCURRENT = 1

_HISTORY_KEY = "ratelimit:analyses:{user_id}"
_RUNNING_KEY = "ratelimit:running:{user_id}"
_MONITOR_HISTORY_KEY = "ratelimit:monitor:analyses:{user_id}"
_MONITOR_RUNNING_KEY = "ratelimit:monitor:running:{user_id}"
# Si un analisis muere sin avisar, su marca de "en curso" caducaria sola en
# vez de bloquear la cuenta para siempre.
_RUNNING_TTL = 2400


class RateLimitExceeded(Exception):
    """Incluye el mensaje que se le muestra al usuario y cuando reintentar."""

    def __init__(self, message: str, retry_after_seconds: int) -> None:
        super().__init__(message)
        self.message = message
        self.retry_after_seconds = retry_after_seconds


def _client() -> redis.Redis:
    return redis.Redis.from_url(get_settings().redis_url)


def check_and_reserve(user_id: uuid.UUID, reservation: str) -> None:
    """Comprueba los tres limites y reserva un hueco.

    `reservation` es el identificador del analisis que se va a crear. Usarlo
    como marca evita guardar la reserva en ningun sitio: al terminar, el
    worker libera el hueco con el mismo id que ya tiene a mano.

    Lanza RateLimitExceeded si no hay hueco, antes de encolar nada.
    """
    _reservar(
        user_id,
        reservation,
        historial=_HISTORY_KEY.format(user_id=user_id),
        en_curso=_RUNNING_KEY.format(user_id=user_id),
        max_hora=MAX_PER_HOUR,
        max_dia=MAX_PER_DAY,
        max_simultaneos=MAX_CONCURRENT,
        etiqueta="",
    )


def _reservar(
    user_id: uuid.UUID,
    reservation: str,
    *,
    historial: str,
    en_curso: str,
    max_hora: int,
    max_dia: int,
    max_simultaneos: int,
    etiqueta: str,
) -> None:
    cliente = _client()
    ahora = time.time()
    sufijo = f" {etiqueta}" if etiqueta else ""

    # Los que ya salieron de la ventana no cuentan para nada.
    cliente.zremrangebyscore(historial, 0, ahora - DAY_SECONDS)
    cliente.zremrangebyscore(en_curso, 0, ahora - _RUNNING_TTL)

    if cliente.zcard(en_curso) >= max_simultaneos:
        raise RateLimitExceeded(
            f"Ya hay {max_simultaneos} analisis{sufijo} en curso. Espera a que terminen.",
            60,
        )

    for ventana, maximo, unidad in (
        (HOUR_SECONDS, max_hora, "por hora"),
        (DAY_SECONDS, max_dia, "diarios"),
    ):
        if cliente.zcount(historial, ahora - ventana, ahora) < maximo:
            continue
        mas_antiguo = cliente.zrangebyscore(
            historial, ahora - ventana, ahora, start=0, num=1, withscores=True
        )
        espera = int(mas_antiguo[0][1] + ventana - ahora) + 1 if mas_antiguo else ventana
        raise RateLimitExceeded(
            f"Has alcanzado el limite de {maximo} analisis{sufijo} {unidad}.",
            max(1, espera),
        )

    cliente.zadd(historial, {reservation: ahora})
    cliente.expire(historial, DAY_SECONDS)
    cliente.zadd(en_curso, {reservation: ahora})
    cliente.expire(en_curso, _RUNNING_TTL)


def check_and_reserve_monitor(user_id: uuid.UUID, reservation: str) -> None:
    """Igual que `check_and_reserve`, pero con la cuota de los monitores.

    Cuando no hay hueco no es un problema: el monitor ya guardo que el
    objetivo cambio, asi que lo reintentara en la siguiente vuelta.
    """
    _reservar(
        user_id,
        reservation,
        historial=_MONITOR_HISTORY_KEY.format(user_id=user_id),
        en_curso=_MONITOR_RUNNING_KEY.format(user_id=user_id),
        max_hora=MONITOR_MAX_PER_HOUR,
        max_dia=MONITOR_MAX_PER_DAY,
        max_simultaneos=MONITOR_MAX_CONCURRENT,
        etiqueta="automaticos",
    )


def release(user_id: uuid.UUID, reservation: str) -> None:
    """Libera el hueco de simultaneos. El historial no se toca: cuenta igual.

    Nunca debe hacer fallar al que la llama: si Redis no responde, la marca
    caduca sola por TTL y como mucho se pierde un hueco un rato.
    """
    try:
        cliente = _client()
        # No se sabe de que cuota salio, y quitar una marca que no existe no
        # cuesta nada, asi que se limpian las dos.
        cliente.zrem(_RUNNING_KEY.format(user_id=user_id), reservation)
        cliente.zrem(_MONITOR_RUNNING_KEY.format(user_id=user_id), reservation)
    except Exception:  # noqa: BLE001
        pass


def current_usage(user_id: uuid.UUID) -> dict:
    """Consumo actual, para que el cliente lo muestre antes de tocar nada."""
    cliente = _client()
    ahora = time.time()
    historial = _HISTORY_KEY.format(user_id=user_id)
    return {
        "last_hour": cliente.zcount(historial, ahora - HOUR_SECONDS, ahora),
        "max_per_hour": MAX_PER_HOUR,
        "last_day": cliente.zcount(historial, ahora - DAY_SECONDS, ahora),
        "max_per_day": MAX_PER_DAY,
        "running": cliente.zcard(_RUNNING_KEY.format(user_id=user_id)),
        "max_concurrent": MAX_CONCURRENT,
    }
