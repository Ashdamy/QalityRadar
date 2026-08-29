"""Vigilancia de proyectos enganchados.

La propiedad que sostiene toda la funcion: **comprobar no analiza**. Si el
objetivo no ha cambiado, la comprobacion no debe generar ningun analisis. Sin
eso, vigilar tres repositorios cada hora serian setenta y dos analisis diarios
inutiles, y la maquina no lo aguanta.
"""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import delete

from app.core.database import SessionLocal
from app.models.deployed_app import DeployedApp
from app.models.monitor import Monitor
from app.models.repository import Repository
from app.models.user import User
from app.services import monitor_service
from app.services.monitor_service import (
    ALLOWED_INTERVALS,
    MAX_CONSECUTIVE_FAILURES,
    MAX_MONITORS_PER_USER,
    MonitorLimitReached,
    check_monitor,
    create_monitor,
    due_monitors,
)
from app.services.rate_limit_service import (
    MONITOR_MAX_CONCURRENT,
    RateLimitExceeded,
    check_and_reserve,
    check_and_reserve_monitor,
)

_EMAIL = "monitores-fixture@example.com"


@pytest.fixture
def contexto():
    def _limpiar():
        db = SessionLocal()
        try:
            db.execute(delete(User).where(User.email == _EMAIL))
            db.commit()
        finally:
            db.close()

    _limpiar()
    db = SessionLocal()
    try:
        usuario = User(id=uuid.uuid4(), email=_EMAIL, password_hash="x")
        db.add(usuario)
        db.flush()
        repo = Repository(
            id=uuid.uuid4(),
            user_id=usuario.id,
            github_id=987654340,
            name="vigilado",
            full_name="prueba/vigilado",
            is_private=False,
        )
        db.add(repo)
        aplicacion = DeployedApp(
            id=uuid.uuid4(),
            user_id=usuario.id,
            name="app",
            url="https://ejemplo-vigilado.test",
        )
        db.add(aplicacion)
        db.commit()
        yield db, usuario.id, repo.id, aplicacion.id
    finally:
        db.close()
        _limpiar()


# --------------------------------------------------------------------------
# Lo esencial: comprobar no analiza
# --------------------------------------------------------------------------


def test_si_el_commit_no_cambio_no_hay_que_analizar(contexto, monkeypatch):
    db, user_id, repo_id, _ = contexto
    monitor = create_monitor(db, user_id, repository_id=repo_id)
    monitor.last_commit_sha = "a" * 40
    db.commit()

    monkeypatch.setattr(monitor_service, "fetch_latest_commit_sha", lambda *_: "a" * 40)
    assert check_monitor(db, monitor) is None


def test_un_commit_nuevo_si_dispara_analisis(contexto, monkeypatch):
    db, user_id, repo_id, _ = contexto
    monitor = create_monitor(db, user_id, repository_id=repo_id)
    monitor.last_commit_sha = "a" * 40
    db.commit()

    monkeypatch.setattr(monitor_service, "fetch_latest_commit_sha", lambda *_: "b" * 40)
    motivo = check_monitor(db, monitor)
    assert motivo is not None
    assert "commit nuevo" in motivo


def test_el_mismo_commit_no_se_analiza_dos_veces(contexto, monkeypatch):
    """Tras disparar, la marca queda guardada: la siguiente vuelta ve el mismo
    commit y no hace nada."""
    db, user_id, repo_id, _ = contexto
    monitor = create_monitor(db, user_id, repository_id=repo_id)
    monitor.last_commit_sha = "a" * 40
    db.commit()

    monkeypatch.setattr(monitor_service, "fetch_latest_commit_sha", lambda *_: "c" * 40)
    assert check_monitor(db, monitor) is not None
    assert check_monitor(db, monitor) is None


def test_el_primer_vistazo_analiza_para_tener_punto_de_partida(contexto, monkeypatch):
    db, user_id, repo_id, _ = contexto
    monitor = create_monitor(db, user_id, repository_id=repo_id)
    db.commit()

    monkeypatch.setattr(monitor_service, "fetch_latest_commit_sha", lambda *_: "d" * 40)
    assert check_monitor(db, monitor) == "analisis inicial"


# --------------------------------------------------------------------------
# Direcciones
# --------------------------------------------------------------------------


def test_una_pagina_con_el_mismo_etag_no_se_reanaliza(contexto, monkeypatch):
    db, user_id, _, app_id = contexto
    monitor = create_monitor(db, user_id, app_id=app_id)
    monitor.last_fingerprint = 'W/"abc"'
    monitor.last_triggered_at = monitor_service.now()
    db.commit()

    monkeypatch.setattr(monitor_service, "fetch_url_fingerprint", lambda *_: 'W/"abc"')
    assert check_monitor(db, monitor) is None


def test_un_etag_distinto_dispara_analisis(contexto, monkeypatch):
    db, user_id, _, app_id = contexto
    monitor = create_monitor(db, user_id, app_id=app_id)
    monitor.last_fingerprint = 'W/"abc"'
    monitor.last_triggered_at = monitor_service.now()
    db.commit()

    monkeypatch.setattr(monitor_service, "fetch_url_fingerprint", lambda *_: 'W/"xyz"')
    assert check_monitor(db, monitor) == "la pagina ha cambiado"


def test_sin_etag_se_cae_a_revision_periodica(contexto, monkeypatch):
    """Si el servidor no da ninguna senal de cambio, no se puede saber: la
    unica opcion honesta es analizar por intervalo."""
    db, user_id, _, app_id = contexto
    monitor = create_monitor(db, user_id, app_id=app_id)
    monitor.last_triggered_at = monitor_service.now()
    db.commit()

    monkeypatch.setattr(monitor_service, "fetch_url_fingerprint", lambda *_: None)
    assert check_monitor(db, monitor) == "revision periodica"


# --------------------------------------------------------------------------
# Planificacion
# --------------------------------------------------------------------------


def test_un_monitor_recien_creado_toca_ya(contexto):
    db, user_id, repo_id, _ = contexto
    monitor = create_monitor(db, user_id, repository_id=repo_id)
    db.commit()
    assert monitor.id in {m.id for m in due_monitors(db)}


def test_un_monitor_comprobado_hace_un_momento_no_toca(contexto):
    db, user_id, repo_id, _ = contexto
    monitor = create_monitor(db, user_id, repository_id=repo_id, interval_minutes=60)
    monitor.last_checked_at = monitor_service.now()
    db.commit()
    assert monitor.id not in {m.id for m in due_monitors(db)}


def test_pasado_el_intervalo_vuelve_a_tocar(contexto):
    db, user_id, repo_id, _ = contexto
    monitor = create_monitor(db, user_id, repository_id=repo_id, interval_minutes=60)
    monitor.last_checked_at = datetime.now(timezone.utc) - timedelta(minutes=61)
    db.commit()
    assert monitor.id in {m.id for m in due_monitors(db)}


def test_un_monitor_desactivado_no_se_comprueba(contexto):
    db, user_id, repo_id, _ = contexto
    monitor = create_monitor(db, user_id, repository_id=repo_id)
    monitor.is_active = False
    db.commit()
    assert monitor.id not in {m.id for m in due_monitors(db)}


# --------------------------------------------------------------------------
# Limites y resistencia
# --------------------------------------------------------------------------


def test_no_se_pueden_vigilar_mas_proyectos_de_la_cuenta(contexto):
    db, user_id, repo_id, app_id = contexto
    create_monitor(db, user_id, repository_id=repo_id)
    create_monitor(db, user_id, app_id=app_id)
    db.commit()

    # Se rellena hasta el tope con objetivos nuevos.
    for i in range(MAX_MONITORS_PER_USER):
        extra = Repository(
            id=uuid.uuid4(),
            user_id=user_id,
            github_id=987654350 + i,
            name=f"extra{i}",
            full_name=f"prueba/extra{i}",
            is_private=False,
        )
        db.add(extra)
        db.commit()
        try:
            create_monitor(db, user_id, repository_id=extra.id)
            db.commit()
        except MonitorLimitReached:
            return  # comportamiento esperado
    pytest.fail("deberia haber cortado al llegar al tope")


def test_vigilar_dos_veces_el_mismo_repositorio_reactiva_el_existente(contexto):
    """El indice unico no admite duplicados: hay que reutilizar la fila."""
    db, user_id, repo_id, _ = contexto
    primero = create_monitor(db, user_id, repository_id=repo_id)
    db.commit()
    primero.is_active = False
    db.commit()

    segundo = create_monitor(db, user_id, repository_id=repo_id)
    db.commit()
    assert segundo.id == primero.id
    assert segundo.is_active is True


def test_un_intervalo_no_permitido_cae_al_valor_por_defecto(contexto):
    db, user_id, repo_id, _ = contexto
    monitor = create_monitor(db, user_id, repository_id=repo_id, interval_minutes=1)
    db.commit()
    assert monitor.check_interval_minutes in ALLOWED_INTERVALS


def test_tras_muchos_fallos_seguidos_se_desactiva_solo(contexto, monkeypatch):
    """Un repositorio borrado o un token revocado no deben reintentarse
    eternamente."""
    db, user_id, repo_id, _ = contexto
    monitor = create_monitor(db, user_id, repository_id=repo_id)
    db.commit()

    monkeypatch.setattr(monitor_service, "fetch_latest_commit_sha", lambda *_: None)
    for _ in range(MAX_CONSECUTIVE_FAILURES):
        check_monitor(db, monitor)
    assert monitor.is_active is False


def test_un_fallo_suelto_no_desactiva_nada(contexto, monkeypatch):
    db, user_id, repo_id, _ = contexto
    monitor = create_monitor(db, user_id, repository_id=repo_id)
    db.commit()

    monkeypatch.setattr(monitor_service, "fetch_latest_commit_sha", lambda *_: None)
    check_monitor(db, monitor)
    assert monitor.is_active is True


def test_un_exito_borra_el_contador_de_fallos(contexto, monkeypatch):
    db, user_id, repo_id, _ = contexto
    monitor = create_monitor(db, user_id, repository_id=repo_id)
    monitor.consecutive_failures = MAX_CONSECUTIVE_FAILURES - 1
    db.commit()

    monkeypatch.setattr(monitor_service, "fetch_latest_commit_sha", lambda *_: "e" * 40)
    check_monitor(db, monitor)
    assert monitor.consecutive_failures == 0


# --------------------------------------------------------------------------
# Cuota separada
# --------------------------------------------------------------------------


def _limpiar_cuotas(user_id):
    from app.services import rate_limit_service as limites

    cliente = limites._client()
    for plantilla in (
        limites._HISTORY_KEY,
        limites._RUNNING_KEY,
        limites._MONITOR_HISTORY_KEY,
        limites._MONITOR_RUNNING_KEY,
    ):
        cliente.delete(plantilla.format(user_id=user_id))
    cliente.delete(limites._GLOBAL_RUNNING_KEY)


def test_los_analisis_automaticos_no_gastan_la_cuota_manual():
    """El riesgo real: que un proyecto vigilado te deje sin analisis a mano."""
    user_id = uuid.uuid4()
    _limpiar_cuotas(user_id)
    try:
        for _ in range(MONITOR_MAX_CONCURRENT):
            check_and_reserve_monitor(user_id, str(uuid.uuid4()))
        # La cuota manual sigue intacta.
        check_and_reserve(user_id, str(uuid.uuid4()))
    finally:
        _limpiar_cuotas(user_id)


def test_la_cuota_de_monitores_tambien_tiene_tope():
    user_id = uuid.uuid4()
    _limpiar_cuotas(user_id)
    try:
        for _ in range(MONITOR_MAX_CONCURRENT):
            check_and_reserve_monitor(user_id, str(uuid.uuid4()))
        with pytest.raises(RateLimitExceeded):
            check_and_reserve_monitor(user_id, str(uuid.uuid4()))
    finally:
        _limpiar_cuotas(user_id)


def test_los_analisis_manuales_no_gastan_la_cuota_de_monitores():
    user_id = uuid.uuid4()
    _limpiar_cuotas(user_id)
    try:
        check_and_reserve(user_id, str(uuid.uuid4()))
        check_and_reserve_monitor(user_id, str(uuid.uuid4()))  # no debe lanzar
    finally:
        _limpiar_cuotas(user_id)
