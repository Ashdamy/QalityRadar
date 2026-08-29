"""Registro de tokens de refresco, para que cerrar sesion signifique algo.

Antes la renovacion era sin estado: el token valia 30 dias y el servidor no
llevaba cuenta de cuales seguian vivos. Cerrar sesion solo lo borraba del
navegador, asi que un token robado seguia funcionando un mes entero y no habia
forma de cortarlo.

Ahora cada token emitido queda registrado y `/refresh` comprueba que siga
activo. Cerrar sesion lo marca revocado y deja de servir al instante.

Se guarda el **hash**, nunca el token en claro: si alguien lee la tabla no
puede usar lo que encuentre. Basta SHA-256 y no bcrypt porque el token no es
una contrasena elegida por una persona — es un JWT firmado, de entropia alta y
no adivinable, asi que no hay nada que proteger contra fuerza bruta. Y hace
falta que la busqueda sea por indice, que con bcrypt seria imposible.
"""

import hashlib
import uuid
from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.refresh_token import RefreshToken


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
    """
    fila = db.scalar(select(RefreshToken).where(RefreshToken.token_hash == _hash(token)))
    if fila is None or fila.revoked:
        return False

    expira = fila.expires_at
    if expira.tzinfo is None:
        expira = expira.replace(tzinfo=timezone.utc)
    return expira > datetime.now(timezone.utc)


def revoke(db: Session, token: str) -> bool:
    """Invalida un token concreto. Devuelve si habia algo que invalidar."""
    fila = db.scalar(select(RefreshToken).where(RefreshToken.token_hash == _hash(token)))
    if fila is None or fila.revoked:
        return False
    fila.revoked = True
    return True


def revoke_all_for_user(db: Session, user_id: uuid.UUID) -> int:
    """Cierra todas las sesiones de una cuenta. Para un "cerrar en todas partes"
    o para cortar por lo sano si se sospecha que la cuenta esta comprometida."""
    resultado = db.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user_id, RefreshToken.revoked.is_(False))
        .values(revoked=True)
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
