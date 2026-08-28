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


@celery_app.task(
    name="qalitiradar.analyze_url",
    time_limit=600,
    soft_time_limit=570,
)
def analyze_url_task(analysis_id: str) -> None:
    # Se importa aqui, no arriba, para no cargar el cliente HTTP y los
    # analizadores de URL en cada arranque del worker de repositorios.
    from app.services.url_analysis_service import run_url_analysis

    run_url_analysis(analysis_id)


def queue_url_analysis(analysis_id: str) -> None:
    analyze_url_task.delay(analysis_id)


@celery_app.task(
    name="qalitiradar.analyze_combined",
    # El doble de tiempo: ejecuta los dos analisis, uno detras de otro.
    time_limit=1200,
    soft_time_limit=1140,
)
def analyze_combined_task(analysis_id: str) -> None:
    from app.services.combined_analysis_service import run_combined_analysis

    run_combined_analysis(analysis_id)


def queue_combined_analysis(analysis_id: str) -> None:
    analyze_combined_task.delay(analysis_id)
