from app.services.analysis_service import run_repository_analysis
from app.worker import celery_app


@celery_app.task(
    name="qalitiradar.analyze_repository",
    time_limit=600,        # 10 minutos duros, como exige el spec
    soft_time_limit=570,   # margen para limpiar antes del corte
)
def analyze_repository_task(analysis_id: str) -> None:
    run_repository_analysis(analysis_id)


def queue_repository_analysis(analysis_id: str) -> None:
    analyze_repository_task.delay(analysis_id)
