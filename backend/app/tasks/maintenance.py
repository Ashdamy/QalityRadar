"""Tareas periodicas de mantenimiento."""

from app.core.database import SessionLocal
from app.services.retention_service import purge_old_analyses
from app.worker import celery_app


@celery_app.task(name="qalitiradar.purge_old_analyses")
def purge_old_analyses_task() -> int:
    """Borra los analisis que sobran por cantidad o por antiguedad.

    Devuelve cuantos elimino para que quede en el log de Celery: si un dia
    borra mucho mas de lo normal, conviene poder verlo.
    """
    db = SessionLocal()
    try:
        return purge_old_analyses(db)
    finally:
        db.close()
