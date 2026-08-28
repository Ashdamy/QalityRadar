"""Proyectos enganchados: alta, baja y estado."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.models.deployed_app import DeployedApp
from app.models.monitor import Monitor
from app.models.repository import Repository
from app.models.user import User
from app.services import monitor_service

router = APIRouter(prefix="/api/monitors", tags=["monitors"])


class CreateMonitorRequest(BaseModel):
    repository_id: uuid.UUID | None = None
    app_id: uuid.UUID | None = None
    interval_minutes: int = monitor_service.DEFAULT_INTERVAL


@router.get("")
def list_monitors(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Lo que estas vigilando, con su ultimo resultado.

    Se devuelve el analisis mas reciente de cada objetivo para que la pantalla
    no tenga que pedirlos uno a uno.
    """
    monitores = db.scalars(
        select(Monitor)
        .where(Monitor.user_id == current_user.id)
        .order_by(Monitor.created_at.desc())
    ).all()

    salida = []
    for monitor in monitores:
        repositorio = (
            db.get(Repository, monitor.repository_id) if monitor.repository_id else None
        )
        aplicacion = db.get(DeployedApp, monitor.app_id) if monitor.app_id else None
        ultimo = monitor_service.latest_analysis_for(db, monitor)

        salida.append(
            {
                "id": str(monitor.id),
                "target_type": "repository" if repositorio else "url",
                "target_name": (
                    repositorio.full_name if repositorio else (aplicacion.url if aplicacion else "")
                ),
                "repository_id": str(monitor.repository_id) if monitor.repository_id else None,
                "app_id": str(monitor.app_id) if monitor.app_id else None,
                "is_active": monitor.is_active,
                "interval_minutes": monitor.check_interval_minutes,
                "last_checked_at": (
                    monitor.last_checked_at.isoformat() if monitor.last_checked_at else None
                ),
                "last_commit_sha": monitor.last_commit_sha,
                "latest_analysis_id": str(ultimo.id) if ultimo else None,
                "latest_score": float(ultimo.overall_score) if ultimo and ultimo.overall_score is not None else None,
                "latest_at": ultimo.created_at.isoformat() if ultimo and ultimo.created_at else None,
            }
        )

    return {
        "monitors": salida,
        "active": sum(1 for m in monitores if m.is_active),
        "max_monitors": monitor_service.MAX_MONITORS_PER_USER,
        "allowed_intervals": list(monitor_service.ALLOWED_INTERVALS),
    }


@router.post("", status_code=status.HTTP_201_CREATED)
def create_monitor(
    payload: CreateMonitorRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Engancha un repositorio o una direccion para que se revise sola."""
    if (payload.repository_id is None) == (payload.app_id is None):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="indica un repositorio o una aplicacion, no ambos",
        )

    if payload.repository_id is not None:
        objetivo = db.get(Repository, payload.repository_id)
        if objetivo is None or objetivo.user_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="repositorio no encontrado"
            )
        if objetivo.is_private:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="solo se vigilan repositorios publicos",
            )
    else:
        objetivo = db.get(DeployedApp, payload.app_id)
        if objetivo is None or objetivo.user_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="aplicacion no encontrada"
            )

    try:
        monitor = monitor_service.create_monitor(
            db,
            current_user.id,
            repository_id=payload.repository_id,
            app_id=payload.app_id,
            interval_minutes=payload.interval_minutes,
        )
    except monitor_service.MonitorLimitReached as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        ) from exc

    db.commit()
    db.refresh(monitor)
    return {"id": str(monitor.id), "is_active": monitor.is_active}


@router.delete("/{monitor_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_monitor(
    monitor_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    """Deja de vigilar. Se borra la fila, no se desactiva: el historico de
    analisis se conserva igualmente, que es lo que al usuario le importa."""
    monitor = db.get(Monitor, monitor_id)
    if monitor is None or monitor.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="no encontrado")
    db.delete(monitor)
    db.commit()
