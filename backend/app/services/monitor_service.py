"""Vigila proyectos enganchados y los reanaliza solo cuando cambian.

Toda la funcion se sostiene sobre una idea: **comprobar es barato, analizar es
caro**. Un analisis clona el repositorio y levanta un contenedor; tarda casi un
minuto. Preguntarle a GitHub cual es el ultimo commit es una llamada que no
descarga codigo.

Asi que el ciclo es: comprobar a menudo, analizar casi nunca. Si nadie ha
subido nada, la comprobacion no cuesta practicamente nada y no se genera
ningun analisis. Solo cuando el commit cambia se lanza el trabajo de verdad.

Para direcciones no hay commit. Se usa el ETag (o el Last-Modified) que
devuelve el servidor, que cumple el mismo papel: dice si el contenido cambio
sin tener que descargarlo entero. Si el servidor no manda ninguno de los dos,
se cae a un analisis por intervalo, porque no hay forma de saberlo.
"""

import uuid
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.analysis import Analysis
from app.models.deployed_app import DeployedApp
from app.models.monitor import Monitor
from app.models.repository import Repository
from app.models.user import User
from app.services.github_service import GITHUB_API_BASE
from app.services.rate_limit_service import check_and_reserve_monitor
from app.utils.crypto import decrypt_token
from app.utils.url_validation import UnsafeUrlError, validate_public_url

# Tope por cuenta. Cada monitor activo multiplica la carga de la maquina, asi
# que se empieza bajo y se sube cuando se vea el consumo real.
MAX_MONITORS_PER_USER = 3

# Intervalos que se ofrecen. Por debajo de 15 minutos no aporta nada: nadie
# necesita saber la nota de su codigo con esa resolucion, y multiplica las
# llamadas a GitHub sin motivo.
ALLOWED_INTERVALS = (15, 60, 360, 1440)
DEFAULT_INTERVAL = 60

# Tras varios fallos seguidos se desactiva solo. Un repositorio borrado o un
# token revocado no deben reintentarse eternamente.
MAX_CONSECUTIVE_FAILURES = 5


class MonitorLimitReached(Exception):
    pass


def now() -> datetime:
    return datetime.now(timezone.utc)


def count_active(db: Session, user_id: uuid.UUID) -> int:
    return len(
        db.scalars(
            select(Monitor.id).where(Monitor.user_id == user_id, Monitor.is_active.is_(True))
        ).all()
    )


def create_monitor(
    db: Session,
    user_id: uuid.UUID,
    *,
    repository_id: uuid.UUID | None = None,
    app_id: uuid.UUID | None = None,
    interval_minutes: int = DEFAULT_INTERVAL,
) -> Monitor:
    if count_active(db, user_id) >= MAX_MONITORS_PER_USER:
        raise MonitorLimitReached(
            f"Solo puedes vigilar {MAX_MONITORS_PER_USER} proyectos a la vez. "
            "Deja de vigilar alguno para anadir otro."
        )

    intervalo = interval_minutes if interval_minutes in ALLOWED_INTERVALS else DEFAULT_INTERVAL

    # Si ya existia uno para este objetivo (desactivado), se reactiva en vez de
    # insertar otro: el indice unico no admite duplicados.
    existente = db.scalar(
        select(Monitor).where(
            Monitor.repository_id == repository_id
            if repository_id
            else Monitor.app_id == app_id
        )
    )
    if existente is not None:
        existente.is_active = True
        existente.check_interval_minutes = intervalo
        existente.consecutive_failures = 0
        return existente

    monitor = Monitor(
        id=uuid.uuid4(),
        user_id=user_id,
        repository_id=repository_id,
        app_id=app_id,
        check_interval_minutes=intervalo,
        # Sin marca previa, la primera comprobacion siempre dispara un
        # analisis: es la foto de partida contra la que comparar despues.
        last_commit_sha=None,
        last_fingerprint=None,
    )
    db.add(monitor)
    return monitor


def due_monitors(db: Session) -> list[Monitor]:
    """Los monitores activos a los que ya les toca comprobacion."""
    candidatos = db.scalars(select(Monitor).where(Monitor.is_active.is_(True))).all()
    momento = now()
    pendientes = []
    for monitor in candidatos:
        ultimo = monitor.last_checked_at
        if ultimo is None:
            pendientes.append(monitor)
            continue
        if ultimo.tzinfo is None:
            ultimo = ultimo.replace(tzinfo=timezone.utc)
        if momento - ultimo >= timedelta(minutes=monitor.check_interval_minutes):
            pendientes.append(monitor)
    return pendientes


def fetch_latest_commit_sha(full_name: str, token: str | None) -> str | None:
    """Ultimo commit de la rama por defecto. Una llamada, sin clonar nada."""
    cabeceras = {"Accept": "application/vnd.github+json"}
    if token:
        cabeceras["Authorization"] = f"Bearer {token}"
    try:
        respuesta = httpx.get(
            f"{GITHUB_API_BASE}/repos/{full_name}/commits",
            headers=cabeceras,
            params={"per_page": 1},
            timeout=10,
        )
    except httpx.RequestError:
        return None
    if respuesta.status_code != 200:
        return None
    commits = respuesta.json()
    return commits[0]["sha"] if commits else None


def fetch_url_fingerprint(url: str) -> str | None:
    """ETag o Last-Modified de la pagina, con una peticion que no baja el cuerpo.

    Se revalida la direccion antes de tocarla: un monitor sobrevive semanas y
    el DNS pudo cambiar desde que se creo, asi que la comprobacion de SSRF que
    se hizo al darla de alta ya no vale.
    """
    try:
        objetivo = validate_public_url(url)
    except UnsafeUrlError:
        return None

    try:
        respuesta = httpx.head(objetivo.url, timeout=10, follow_redirects=False)
    except httpx.RequestError:
        return None

    etag = respuesta.headers.get("etag")
    if etag:
        return etag[:255]
    modificado = respuesta.headers.get("last-modified")
    return modificado[:255] if modificado else None


def check_monitor(db: Session, monitor: Monitor) -> str | None:
    """Comprueba si el objetivo cambio. Devuelve el motivo para analizar, o None.

    Actualiza la marca (`last_commit_sha` o `last_fingerprint`) antes de
    devolver, para no relanzar el mismo cambio en la siguiente vuelta.
    """
    monitor.last_checked_at = now()

    if monitor.repository_id is not None:
        return _comprobar_repositorio(db, monitor)
    return _comprobar_direccion(db, monitor)


def _comprobar_repositorio(db: Session, monitor: Monitor) -> str | None:
    repositorio = db.get(Repository, monitor.repository_id)
    if repositorio is None:
        monitor.is_active = False
        return None

    usuario = db.get(User, monitor.user_id)
    token = None
    if usuario is not None and usuario.github_access_token_encrypted:
        try:
            token = decrypt_token(usuario.github_access_token_encrypted)
        except Exception:  # noqa: BLE001
            token = None

    sha = fetch_latest_commit_sha(repositorio.full_name, token)
    if sha is None:
        monitor.consecutive_failures += 1
        if monitor.consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
            # Repositorio borrado, privado o token revocado: reintentarlo para
            # siempre solo gasta llamadas.
            monitor.is_active = False
        return None

    monitor.consecutive_failures = 0
    if sha == monitor.last_commit_sha:
        return None

    primera_vez = monitor.last_commit_sha is None
    monitor.last_commit_sha = sha
    return "analisis inicial" if primera_vez else f"commit nuevo {sha[:8]}"


def _comprobar_direccion(db: Session, monitor: Monitor) -> str | None:
    aplicacion = db.get(DeployedApp, monitor.app_id)
    if aplicacion is None:
        monitor.is_active = False
        return None

    huella = fetch_url_fingerprint(aplicacion.url)
    primera_vez = monitor.last_fingerprint is None and monitor.last_triggered_at is None

    if huella is None:
        # El servidor no da ETag ni Last-Modified. Sin senal de cambio, la
        # unica opcion honesta es analizar por intervalo.
        monitor.last_fingerprint = None
        return "analisis inicial" if primera_vez else "revision periodica"

    if huella == monitor.last_fingerprint:
        return None

    monitor.last_fingerprint = huella
    return "analisis inicial" if primera_vez else "la pagina ha cambiado"


def latest_analysis_for(db: Session, monitor: Monitor) -> Analysis | None:
    consulta = select(Analysis).where(Analysis.status == "completed")
    if monitor.repository_id is not None:
        consulta = consulta.where(Analysis.repository_id == monitor.repository_id)
    else:
        consulta = consulta.where(Analysis.app_id == monitor.app_id)
    return db.scalars(consulta.order_by(Analysis.created_at.desc()).limit(1)).first()


def reservar_para_monitor(user_id: uuid.UUID, reservation: str) -> None:
    """Pide hueco en la cuota de los analisis automaticos."""
    check_and_reserve_monitor(user_id, reservation)
