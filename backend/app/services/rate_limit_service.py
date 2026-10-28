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

import hashlib
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

# Tope para TODA la maquina, no por usuario. Los limites de arriba impiden que
# una cuenta abuse, pero no que diez cuentas coincidan: cada analisis reserva
# 512 MB, asi que treinta a la vez son quince gigas y el servidor se cae.
#
# Aqui no se protege al usuario del sistema, sino al sistema de sus usuarios.
MAX_GLOBAL_CONCURRENT = 6
_GLOBAL_RUNNING_KEY = "ratelimit:global:running"

# Registros por hora desde una misma IP. Como los limites de uso son por
# cuenta, sin esto basta con crear varias para saltarselos.
MAX_REGISTRATIONS_PER_IP_HOUR = 5
_REGISTRATION_KEY = "ratelimit:registrations:{ip}"

MAX_VERIFICATION_EMAILS_PER_HOUR = 3
_VERIFICATION_KEY = "ratelimit:verification:{user_id}"

MAX_RESET_EMAILS_PER_EMAIL_HOUR = 3
MAX_RESET_REQUESTS_PER_IP_HOUR = 10
_RESET_EMAIL_KEY = "ratelimit:reset:email:{huella}"
_RESET_IP_KEY = "ratelimit:reset:ip:{ip}"
# Fuerza bruta contra el inicio de sesion. bcrypt hace lento cada intento,
# pero lento no es imposible: sin limite se pueden probar contrasenas toda la
# noche contra la misma cuenta.
#
# Se cuentan solo los fallos, y por dos claves a la vez porque frenan ataques
# distintos: la del email frena probar mil contrasenas contra una cuenta, la de
# la IP frena probar una contrasena comun contra mil cuentas.
MAX_LOGIN_FAILURES_PER_EMAIL_HOUR = 10
MAX_LOGIN_FAILURES_PER_IP_HOUR = 30
_LOGIN_EMAIL_KEY = "ratelimit:login:email:{huella}"
_LOGIN_IP_KEY = "ratelimit:login:ip:{ip}"

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


def check_and_reserve(user_id: uuid.UUID, reservation: str, *, contar: bool = True) -> None:
    """Comprueba los tres limites y reserva un hueco.

    Con `contar=False` se toma el hueco de simultaneos pero el analisis no entra
    en el historial horario ni diario. Es para reintentar uno que fallo: cobrar
    dos veces por un corte de red no tiene sentido. Los limites de simultaneos y
    el tope de la maquina se siguen respetando, que son los que protegen los
    recursos; el numero de reintentos gratuitos lo acota quien llama.

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
        contar=contar,
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
    contar: bool = True,
) -> None:
    cliente = _client()
    ahora = time.time()
    sufijo = f" {etiqueta}" if etiqueta else ""

    # Los que ya salieron de la ventana no cuentan para nada.
    cliente.zremrangebyscore(historial, 0, ahora - DAY_SECONDS)
    cliente.zremrangebyscore(en_curso, 0, ahora - _RUNNING_TTL)
    cliente.zremrangebyscore(_GLOBAL_RUNNING_KEY, 0, ahora - _RUNNING_TTL)

    # El tope de la maquina se mira primero: da igual que al usuario le queden
    # analisis si no hay memoria para atenderlos.
    if cliente.zcard(_GLOBAL_RUNNING_KEY) >= MAX_GLOBAL_CONCURRENT:
        raise RateLimitExceeded(
            "El servicio esta atendiendo el maximo de analisis a la vez. "
            "Vuelve a intentarlo en unos minutos.",
            120,
        )

    if cliente.zcard(en_curso) >= max_simultaneos:
        raise RateLimitExceeded(
            f"Ya hay {max_simultaneos} analisis{sufijo} en curso. Espera a que terminen.",
            60,
        )

    # Un reintento no pasa por las ventanas horaria y diaria, pero si por el
    # tope de simultaneos y por el de la maquina, que son los que protegen los
    # recursos de verdad.
    ventanas = (
        ((HOUR_SECONDS, max_hora, "por hora"), (DAY_SECONDS, max_dia, "diarios"))
        if contar
        else ()
    )
    for ventana, maximo, unidad in ventanas:
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

    if contar:
        cliente.zadd(historial, {reservation: ahora})
        cliente.expire(historial, DAY_SECONDS)
    cliente.zadd(en_curso, {reservation: ahora})
    cliente.expire(en_curso, _RUNNING_TTL)
    cliente.zadd(_GLOBAL_RUNNING_KEY, {reservation: ahora})


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
        cliente.zrem(_GLOBAL_RUNNING_KEY, reservation)
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


def check_registration_ip(ip: str | None) -> None:
    """Limita cuantas cuentas se pueden crear desde una misma IP.

    No sustituye a verificar el email, pero sube bastante el coste de crear
    cuentas en cadena para saltarse los limites de uso.
    """
    if not ip:
        return

    cliente = _client()
    clave = _REGISTRATION_KEY.format(ip=ip)
    ahora = time.time()
    cliente.zremrangebyscore(clave, 0, ahora - HOUR_SECONDS)

    if cliente.zcard(clave) >= MAX_REGISTRATIONS_PER_IP_HOUR:
        raise RateLimitExceeded(
            "Se han creado demasiadas cuentas desde esta conexion. "
            "Vuelve a intentarlo mas tarde.",
            HOUR_SECONDS,
        )

    cliente.zadd(clave, {str(uuid.uuid4()): ahora})
    cliente.expire(clave, HOUR_SECONDS)


def check_verification_email(user_id: uuid.UUID) -> None:
    """Limita cuantos correos de verificacion salen para una misma cuenta.

    Se reenvia cada vez que alguien entra con la contrasena correcta sin haber
    verificado. Sin tope, repetir el login seria una forma de usarnos para
    llenarle el buzon a alguien, y de quemar la reputacion del remitente.
    """
    cliente = _client()
    clave = _VERIFICATION_KEY.format(user_id=user_id)
    ahora = time.time()
    cliente.zremrangebyscore(clave, 0, ahora - HOUR_SECONDS)

    if cliente.zcard(clave) >= MAX_VERIFICATION_EMAILS_PER_HOUR:
        raise RateLimitExceeded("Ya se enviaron varios correos; revisa tu bandeja.", HOUR_SECONDS)

    cliente.zadd(clave, {str(uuid.uuid4()): ahora})
    cliente.expire(clave, HOUR_SECONDS)


def check_password_reset(email: str, ip: str | None) -> None:
    """Limita las peticiones de "olvide mi contrasena".

    Por correo, para no poder usarnos para llenarle el buzon a alguien; por IP,
    para no poder recorrer una lista de correos mandando enlaces a todos. Solo
    cuenta si caben las dos: un intento rechazado no gasta cupo.
    """
    cliente = _client()
    ahora = time.time()
    claves = [(_RESET_EMAIL_KEY.format(huella=_huella_de_email(email)), MAX_RESET_EMAILS_PER_EMAIL_HOUR)]
    if ip:
        claves.append((_RESET_IP_KEY.format(ip=ip), MAX_RESET_REQUESTS_PER_IP_HOUR))

    for clave, maximo in claves:
        cliente.zremrangebyscore(clave, 0, ahora - HOUR_SECONDS)
        if cliente.zcard(clave) >= maximo:
            raise RateLimitExceeded("Demasiadas peticiones; vuelve a intentarlo mas tarde.", HOUR_SECONDS)

    for clave, _ in claves:
        cliente.zadd(clave, {str(uuid.uuid4()): ahora})
        cliente.expire(clave, HOUR_SECONDS)


def global_running() -> int:
    """Cuantos analisis hay en marcha en toda la maquina."""
    cliente = _client()
    cliente.zremrangebyscore(_GLOBAL_RUNNING_KEY, 0, time.time() - _RUNNING_TTL)
    return cliente.zcard(_GLOBAL_RUNNING_KEY)


def _huella_de_email(email: str) -> str:
    """El email no se guarda en claro como clave de Redis.

    Quien lea el Redis se llevaria el listado de correos que han intentado
    entrar, que es justo lo que no hace falta darle. El hash sirve igual para
    contar y no dice a quien pertenece.
    """
    return hashlib.sha256(email.strip().lower().encode()).hexdigest()


def _claves_de_login(email: str, ip: str | None) -> list[tuple[str, int]]:
    claves = [
        (
            _LOGIN_EMAIL_KEY.format(huella=_huella_de_email(email)),
            MAX_LOGIN_FAILURES_PER_EMAIL_HOUR,
        )
    ]
    # Detras de segun que proxy la IP no llega. Mejor limitar solo por email
    # que rechazar a usuarios legitimos.
    if ip:
        claves.append((_LOGIN_IP_KEY.format(ip=ip), MAX_LOGIN_FAILURES_PER_IP_HOUR))
    return claves


def check_login_allowed(email: str, ip: str | None) -> None:
    """Comprueba, antes de mirar la contrasena, que quedan intentos.

    Va antes a proposito: si se comprobara despues, cada intento bloqueado
    seguiria pagando el bcrypt y el limite no protegeria de nada la CPU.

    El limite se aplica exista o no la cuenta, asi que un 429 no revela que el
    email este registrado.
    """
    cliente = _client()
    ahora = time.time()

    for clave, maximo in _claves_de_login(email, ip):
        cliente.zremrangebyscore(clave, 0, ahora - HOUR_SECONDS)
        if cliente.zcard(clave) < maximo:
            continue
        mas_antiguo = cliente.zrange(clave, 0, 0, withscores=True)
        espera = (
            int(mas_antiguo[0][1] + HOUR_SECONDS - ahora) + 1 if mas_antiguo else HOUR_SECONDS
        )
        raise RateLimitExceeded(
            "Demasiados intentos fallidos. Vuelve a intentarlo mas tarde.",
            max(1, espera),
        )


def record_login_failure(email: str, ip: str | None) -> None:
    """Anota un fallo en las dos ventanas."""
    cliente = _client()
    ahora = time.time()
    # Cada fallo necesita su propia marca: en un sorted set, dos miembros
    # iguales se pisan y el segundo intento no contaria.
    marca = str(uuid.uuid4())
    for clave, _ in _claves_de_login(email, ip):
        cliente.zadd(clave, {marca: ahora})
        cliente.expire(clave, HOUR_SECONDS)


def clear_login_failures(email: str) -> None:
    """Entrar bien borra el contador de la cuenta, para que un despiste no
    deje al dueno fuera una hora.

    El de la IP no se toca: si se limpiara, cualquiera con una cuenta propia
    podria entrar en la suya entre tandas y seguir probando sin limite contra
    las demas.
    """
    _client().delete(_LOGIN_EMAIL_KEY.format(huella=_huella_de_email(email)))
