"""Bandeja de avisos de cambio significativo."""

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.models.notification import Notification
from app.models.user import User

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


@router.get("")
def list_notifications(
    unread_only: bool = False,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Los avisos del usuario, del mas reciente al mas antiguo."""
    consulta = select(Notification).where(Notification.user_id == current_user.id)
    if unread_only:
        consulta = consulta.where(Notification.read_at.is_(None))

    filas = db.scalars(consulta.order_by(Notification.created_at.desc()).limit(50)).all()
    return {
        # El contador va aparte del listado: la interfaz lo necesita para el
        # punto rojo aunque no despliegue la bandeja.
        "unread_count": sum(1 for f in filas if f.read_at is None),
        "notifications": [
            {
                "id": str(f.id),
                "analysis_id": str(f.analysis_id),
                "kind": f.kind,
                "severity": f.severity,
                "title": f.title,
                "body": f.body,
                "read": f.read_at is not None,
                "created_at": f.created_at.isoformat() if f.created_at else None,
            }
            for f in filas
        ],
    }


@router.post("/{notification_id}/read", status_code=status.HTTP_204_NO_CONTENT)
def mark_read(
    notification_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    aviso = db.get(Notification, notification_id)
    if aviso is None or aviso.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="aviso no encontrado")
    if aviso.read_at is None:
        aviso.read_at = datetime.now(timezone.utc)
        db.commit()


@router.post("/read-all", status_code=status.HTTP_204_NO_CONTENT)
def mark_all_read(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    db.execute(
        update(Notification)
        .where(Notification.user_id == current_user.id, Notification.read_at.is_(None))
        .values(read_at=datetime.now(timezone.utc))
    )
    db.commit()
