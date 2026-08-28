"""Ciclo de vigilancia: comprobar mucho, analizar poco."""

import uuid

from app.core.database import SessionLocal
from app.models.analysis import Analysis
from app.services import monitor_service
from app.tasks.analyze_repository import queue_repository_analysis, queue_url_analysis
from app.worker import celery_app


@celery_app.task(name="qalitiradar.check_monitors")
def check_monitors_task() -> dict:
    """Recorre los monitores que tocan y encola analisis solo si algo cambio.

    Devuelve un resumen para que quede en el log: si un dia dispara muchos mas
    analisis de lo normal, conviene poder verlo sin entrar a la base.
    """
    db = SessionLocal()
    comprobados = 0
    disparados = 0
    try:
        for monitor in monitor_service.due_monitors(db):
            comprobados += 1
            try:
                motivo = monitor_service.check_monitor(db, monitor)
            except Exception:  # noqa: BLE001
                # Un objetivo que falla no puede impedir que se revisen los
                # demas.
                db.rollback()
                continue

            if motivo is None:
                db.commit()
                continue

            if _encolar(db, monitor):
                monitor.last_triggered_at = monitor_service.now()
                disparados += 1
            db.commit()
        return {"comprobados": comprobados, "disparados": disparados}
    finally:
        db.close()


def _encolar(db, monitor) -> bool:
    """Crea el analisis y lo manda a la cola. False si no se pudo."""
    analysis_id = uuid.uuid4()
    try:
        # Los analisis automaticos pasan por el mismo control de uso que los
        # manuales: un monitor no puede saltarselo.
        monitor_service.reservar_para_monitor(monitor.user_id, str(analysis_id))
    except Exception:  # noqa: BLE001
        # Sin hueco ahora mismo. No es un error: se reintentara en la
        # siguiente vuelta, y la marca de cambio ya quedo guardada.
        return False

    analysis = Analysis(
        id=analysis_id,
        user_id=monitor.user_id,
        repository_id=monitor.repository_id,
        app_id=monitor.app_id,
        analysis_type="repository" if monitor.repository_id else "url",
        status="pending",
        triggered_by="monitor",
    )
    db.add(analysis)
    db.flush()

    if monitor.repository_id is not None:
        queue_repository_analysis(str(analysis_id))
    else:
        queue_url_analysis(str(analysis_id))
    return True
