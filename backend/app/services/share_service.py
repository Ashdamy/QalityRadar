"""Enlaces publicos y temporales para compartir un informe.

Un enlace compartido salta la autenticacion por definicion, asi que el token
**es** la credencial. De ahi tres decisiones:

- Se genera con `secrets.token_urlsafe(32)`: 256 bits, imposible de adivinar
  por fuerza bruta.
- Caduca. Un enlace eterno acaba circulando por sitios que nadie controla.
- No se reutiliza: pedir un enlace dos veces da dos tokens, y revocar uno no
  afecta al otro.
"""

import secrets
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.analysis import Analysis
from app.models.shared_report import SharedReport

# Suficiente para ensenar un informe a un equipo o adjuntarlo a una entrega,
# sin que el enlace siga vivo meses despues.
DEFAULT_EXPIRY_DAYS = 7
MAX_EXPIRY_DAYS = 30


def create_share_link(db: Session, analysis: Analysis, expiry_days: int | None = None) -> SharedReport:
    dias = expiry_days or DEFAULT_EXPIRY_DAYS
    dias = max(1, min(dias, MAX_EXPIRY_DAYS))

    enlace = SharedReport(
        id=uuid.uuid4(),
        analysis_id=analysis.id,
        token=secrets.token_urlsafe(32),
        expires_at=datetime.now(timezone.utc) + timedelta(days=dias),
    )
    db.add(enlace)
    return enlace


def resolve_share_token(db: Session, token: str) -> Analysis | None:
    """Devuelve el analisis del enlace, o None si no vale.

    No distingue entre "no existe" y "ha caducado": para quien no tiene el
    enlace, ambos casos deben ser indistinguibles, o el endpoint publico se
    convierte en un oraculo para saber que tokens existieron.
    """
    enlace = db.scalar(select(SharedReport).where(SharedReport.token == token))
    if enlace is None:
        return None

    expira = enlace.expires_at
    if expira.tzinfo is None:
        expira = expira.replace(tzinfo=timezone.utc)
    if expira <= datetime.now(timezone.utc):
        return None

    return db.get(Analysis, enlace.analysis_id)


def revoke_share_link(db: Session, analysis: Analysis, token: str) -> bool:
    """Invalida un enlace concreto. Devuelve False si no era de ese analisis."""
    enlace = db.scalar(
        select(SharedReport).where(
            SharedReport.token == token, SharedReport.analysis_id == analysis.id
        )
    )
    if enlace is None:
        return False
    db.delete(enlace)
    return True
