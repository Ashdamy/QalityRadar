"""Registro de lo que le pasa a una cuenta.

Sin esto no habia forma de contestar la pregunta que se hace despues de un
susto: si alguien entro donde no debia, cuando, y desde donde.

Se dejo fuera a proposito el registro de **lecturas** —quien consulto que
analisis—, que es lo que el inventario de seguridad pedia. Eso crece con cada
peticion, guarda mucho mas dato personal y no contesta esa pregunta. Lo que la
contesta es esto: entradas, salidas, fallos y vinculaciones de cuenta.

Tampoco se guarda el correo de un intento contra una cuenta que no existe: eso
seria construir la lista de correos que alguien probo, que es justo lo que no
hace falta tener guardado.
"""

import ipaddress
import uuid

from sqlalchemy.orm import Session

from app.models.auth_event import AuthEvent

REGISTRO = "registro"
ENTRADA = "entrada"
ENTRADA_FALLIDA = "entrada_fallida"
ENTRADA_BLOQUEADA = "entrada_bloqueada"
SALIDA = "salida"
GITHUB_VINCULADO = "github_vinculado"
EMAIL_VERIFICADO = "email_verificado"

# Una IP es un dato personal, y guardarla para siempre no ayuda a nadie: para
# investigar un incidente sobra con los ultimos meses.
RETENTION_DAYS = 90


def _ip_o_nada(valor: str | None) -> str | None:
    """La columna es INET y rechaza lo que no sea una direccion.

    Y lo que llega no siempre lo es: detras de segun que proxy no llega nada, y
    un cliente de pruebas manda literalmente "testclient". Si eso llegara a la
    columna, la insercion falla y se pierde el evento **entero**, que es mucho
    peor que perder solo la direccion.
    """
    if not valor:
        return None
    try:
        return str(ipaddress.ip_address(valor))
    except ValueError:
        return None


def registrar(
    db: Session, evento: str, *, user_id: uuid.UUID | None = None, ip: str | None = None
) -> None:
    """Anota un evento. Nunca hace fallar a quien la llama.

    Si el registro fallara y arrastrara consigo la peticion, un problema del
    rastro dejaria a la gente sin poder entrar. Un rastro incompleto es peor
    que uno completo y mejor que un servicio caido.

    No confirma la transaccion: lo hace quien la llama, junto con lo demas.
    """
    try:
        db.add(
            AuthEvent(id=uuid.uuid4(), user_id=user_id, event=evento, ip=_ip_o_nada(ip))
        )
        db.flush()
    except Exception:  # noqa: BLE001
        db.rollback()


def purge_old_events(db: Session) -> int:
    """Borra los eventos que pasaron de la ventana de retencion."""
    from datetime import datetime, timedelta, timezone

    from sqlalchemy import delete

    corte = datetime.now(timezone.utc) - timedelta(days=RETENTION_DAYS)
    resultado = db.execute(delete(AuthEvent).where(AuthEvent.created_at < corte))
    return resultado.rowcount or 0
