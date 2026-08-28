from celery import Celery

from app.core.config import get_settings

settings = get_settings()

celery_app = Celery(
    "qalitiradar",
    broker=settings.redis_url,
    backend=settings.redis_url,
    # Sin `include`, Celery nunca importa el modulo de tareas y el worker
    # rechaza cada mensaje con KeyError: 'qalitiradar.analyze_repository'.
    include=["app.tasks.analyze_repository", "app.tasks.maintenance", "app.tasks.monitoring"],
)

# La purga corre una vez al dia. No hay prisa: es mantenimiento, y hacerla mas
# a menudo solo anadiria carga sin cambiar el resultado.
celery_app.conf.beat_schedule = {
    "purgar-analisis-antiguos": {
        "task": "qalitiradar.purge_old_analyses",
        "schedule": 24 * 60 * 60,
    },
    # Cada 5 minutos. Puede ser tan frecuente porque comprobar no analiza
    # nada: es una llamada a GitHub que no clona el repositorio. El intervalo
    # real de cada monitor se respeta dentro de la tarea.
    "comprobar-monitores": {
        "task": "qalitiradar.check_monitors",
        "schedule": 5 * 60,
    },
}
