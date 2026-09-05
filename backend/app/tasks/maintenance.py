"""Tareas periodicas de mantenimiento."""

from app.core.database import SessionLocal
from app.services.audit_service import purge_old_events
from app.services.retention_service import purge_old_analyses
from app.services.session_service import purge_expired as purge_expired_tokens
from app.services.share_service import purge_expired_links
from app.worker import celery_app


@celery_app.task(name="qalitiradar.purge_old_analyses")
def purge_old_analyses_task() -> dict:
    """Barre lo que ya no sirve: analisis viejos, tokens muertos y enlaces
    caducados.

    Los tres se limpiaban a mano o no se limpiaban. `purge_expired` de las
    sesiones existia y no la llamaba nadie, cosa que con la rotacion del token
    de refresco pasa de ser un detalle a acumular unas cien filas al dia por
    cada sesion activa.

    Devuelve el recuento para que quede en el log de Celery: si un dia borra
    mucho mas de lo normal, conviene poder verlo.
    """
    db = SessionLocal()
    try:
        borrados = {
            "analisis": purge_old_analyses(db),
            "tokens": purge_expired_tokens(db),
            "enlaces": purge_expired_links(db),
            "eventos": purge_old_events(db),
        }
        # `purge_old_analyses` confirma por su cuenta; los otros dos no, para
        # que las dos limpiezas entren o no entren juntas.
        db.commit()
        return borrados
    finally:
        db.close()
