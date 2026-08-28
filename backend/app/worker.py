from celery import Celery

from app.core.config import get_settings

settings = get_settings()

celery_app = Celery(
    "qalitiradar",
    broker=settings.redis_url,
    backend=settings.redis_url,
    # Sin `include`, Celery nunca importa el modulo de tareas y el worker
    # rechaza cada mensaje con KeyError: 'qalitiradar.analyze_repository'.
    include=["app.tasks.analyze_repository"],
)
