"""El worker debe registrar sus tareas al arrancar.

Sin `include=[...]` en la app de Celery, el worker arranca sin errores pero
rechaza cada mensaje con `KeyError: 'qalitiradar.analyze_repository'` — un
fallo que solo se ve en tiempo de ejecucion y con el worker ya corriendo.
"""

from app.worker import celery_app

TASK_NAME = "qalitiradar.analyze_repository"


def test_analysis_task_is_registered_on_the_worker():
    # `tasks` solo se puebla tras importar los modulos declarados en `include`;
    # forzar la carga es justo lo que hace el worker real al arrancar.
    celery_app.loader.import_default_modules()
    assert TASK_NAME in celery_app.tasks


def test_analysis_task_has_the_mandated_time_limits():
    celery_app.loader.import_default_modules()
    task = celery_app.tasks[TASK_NAME]
    # El spec exige un tope duro de 10 minutos por analisis.
    assert task.time_limit == 600
    assert task.soft_time_limit == 570
    assert task.soft_time_limit < task.time_limit
