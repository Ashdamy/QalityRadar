"""Registro de tokens de refresco, para que cerrar sesion signifique algo.

Antes la renovacion era sin estado: el token valia 30 dias y el servidor no
llevaba cuenta de cuales seguian vivos. Cerrar sesion solo lo borraba del
navegador, asi que un token robado seguia funcionando un mes entero y no habia
forma de cortarlo.

Ahora cada token emitido queda registrado y `/refresh` comprueba que siga
activo. Cerrar sesion lo marca revocado y deja de servir al instante.

Y cada renovacion **rota**: emite uno nuevo y anula el que se uso. Asi un token
robado deja de valer en cuanto el dueno renueva, en vez de los 30 dias enteros.
El anterior se sigue aceptando unos segundos (`GRACE_SECONDS`) porque dos
pestanas renovando a la vez no son un ataque, y sin ese margen la segunda se
encontraria con la sesion cerrada.

Se guarda el **hash**, nunca el token en claro: si alguien lee la tabla no
puede usar lo que encuentre. Basta SHA-256 y no bcrypt porque el token no es
una contrasena elegida por una persona — es un JWT firmado, de entropia alta y
no adivinable, asi que no hay nada que proteger contra fuerza bruta. Y hace
falta que la busqueda sea por indice, que con bcrypt seria imposible.
"""

import hashlib
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.refresh_token import RefreshToken


# Margen para que dos pestanas que renuevan a la vez no se pisen. Corto a
# proposito: durante ese rato un token robado tambien sirve, y son segundos
# frente a los 30 dias que duraba antes.
GRACE_SECONDS = 30


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def register_refresh_token(db: Session, user_id: uuid.UUID, token: str) -> None:
    """Anota un token recien emitido como activo."""
    settings = get_settings()
    expira = datetime.now(timezone.utc) + _dias(settings.jwt_refresh_expire_days)
    db.add(
        RefreshToken(
            id=uuid.uuid4(),
            user_id=user_id,
            token_hash=_hash(token),
            expires_at=expira,
        )
    )


def is_active(db: Session, token: str) -> bool:
    """True si el token esta registrado, sin revocar y sin caducar.

    Un token que no aparece en la tabla se rechaza. Eso invalida de golpe los
    emitidos antes de existir este registro, que es lo correcto: no se puede
    garantizar nada sobre ellos.

    Un token recien rotado tambien cuenta como activo mientras dure la ventana
    de gracia: lo uso su dueno hace un segundo, no es un token resucitado.
    """
    fila = db.scalar(select(RefreshToken).where(RefreshToken.token_hash == _hash(token)))
    if fila is None:
        return False
    if fila.revoked and not _en_periodo_de_gracia(fila):
        return False

    return _con_zona(fila.expires_at) > datetime.now(timezone.utc)


def _con_zona(momento: datetime) -> datetime:
    """Postgres devuelve la fecha con zona, SQLite y algunos fixtures no."""
    return momento if momento.tzinfo else momento.replace(tzinfo=timezone.utc)


def _en_periodo_de_gracia(fila: RefreshToken) -> bool:
    """Distingue "se roto hace un momento" de "se cerro sesion".

    Sin esta distincion habria que elegir entre dos males: aceptar cualquier
    token anulado, o echar de la sesion a quien tenga dos pestanas abiertas
    renovando a la vez.
    """
    if fila.rotated_at is None:
        return False
    limite = _con_zona(fila.rotated_at) + timedelta(seconds=GRACE_SECONDS)
    return datetime.now(timezone.utc) < limite


def rotate(db: Session, user_id: uuid.UUID, token: str, nuevo_token: str) -> None:
    """Anula el token usado y registra el que lo sustituye.

    Se marca `rotated_at` ademas de `revoked` para no confundirlo despues con
    un cierre de sesion, que no admite ninguna gracia.

    Si el token ya estaba rotado (la segunda pestana de la carrera) no se toca
    su marca: mover la fecha alargaria la ventana indefinidamente cada vez que
    alguien reintenta.
    """
    fila = db.scalar(select(RefreshToken).where(RefreshToken.token_hash == _hash(token)))
    if fila is not None and not fila.revoked:
        fila.revoked = True
        fila.rotated_at = datetime.now(timezone.utc)
    register_refresh_token(db, user_id, nuevo_token)


def revoke(db: Session, token: str) -> bool:
    """Invalida un token concreto. Devuelve si habia algo que invalidar.

    Cerrar sesion corta tambien la ventana de gracia: se limpia `rotated_at`,
    porque si no un token recien rotado seguiria sirviendo medio minuto
    despues de haber cerrado, que es justo lo que cerrar sesion promete que no
    pasa.
    """
    fila = db.scalar(select(RefreshToken).where(RefreshToken.token_hash == _hash(token)))
    if fila is None:
        return False
    if fila.revoked and fila.rotated_at is None:
        return False
    fila.revoked = True
    fila.rotated_at = None
    return True


def revoke_all_for_user(db: Session, user_id: uuid.UUID) -> int:
    """Cierra todas las sesiones de una cuenta. Para un "cerrar en todas partes"
    o para cortar por lo sano si se sospecha que la cuenta esta comprometida."""
    from sqlalchemy import or_

    resultado = db.execute(
        update(RefreshToken)
        .where(
            RefreshToken.user_id == user_id,
            # Los que estan en periodo de gracia tambien: siguen sirviendo.
            or_(RefreshToken.revoked.is_(False), RefreshToken.rotated_at.is_not(None)),
        )
        .values(revoked=True, rotated_at=None)
    )
    return resultado.rowcount or 0


def purge_expired(db: Session) -> int:
    """Borra los que ya caducaron. La tabla crece con cada inicio de sesion y
    un token caducado no aporta nada: ya no vale ni aunque no este revocado."""
    from sqlalchemy import delete

    resultado = db.execute(
        delete(RefreshToken).where(RefreshToken.expires_at <= datetime.now(timezone.utc))
    )
    return resultado.rowcount or 0


def _dias(cantidad: int):
    from datetime import timedelta

    return timedelta(days=cantidad)
