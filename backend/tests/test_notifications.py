"""Avisos de cambio significativo.

Lo que se prueba sobre todo es cuando **no** debe avisar: un aviso que salta
por cualquier variacion deja de leerse, y entonces tampoco sirve el dia que
importa.
"""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import delete, select

from app.core.database import SessionLocal
from app.models.analysis import Analysis, Dimension, Finding
from app.models.notification import Notification
from app.models.repository import Repository
from app.models.user import User
from app.services.notification_service import (
    COVERAGE_DROP_THRESHOLD,
    SCORE_DROP_THRESHOLD,
    build_notifications,
    persist_notifications,
)

_EMAIL = "avisos-fixture@example.com"


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
            github_id=987654330,
            name="avisos",
            full_name="prueba/avisos",
            is_private=False,
        )
        db.add(repo)
        db.commit()
        yield db, usuario.id, repo.id
    finally:
        db.close()
        _limpiar()


def _analisis(db, user_id, repo_id, score, *, minutos_atras=0, origen="manual"):
    fila = Analysis(
        id=uuid.uuid4(),
        user_id=user_id,
        repository_id=repo_id,
        analysis_type="repository",
        status="completed",
        overall_score=score,
        triggered_by=origen,
        created_at=datetime.now(timezone.utc) - timedelta(minutes=minutos_atras),
    )
    db.add(fila)
    db.commit()
    return fila


def _hallazgo(db, analysis_id, severidad, titulo, tipo="security"):
    db.add(
        Finding(
            id=uuid.uuid4(),
            analysis_id=analysis_id,
            type=tipo,
            severity=severidad,
            title=titulo,
            description="d",
        )
    )
    db.commit()


def _cobertura(db, analysis_id, proporcion):
    db.add(
        Dimension(
            id=uuid.uuid4(),
            analysis_id=analysis_id,
            name="reliability",
            score=50,
            weight=0.2,
            raw_metrics={"test_ratio": proporcion},
        )
    )
    db.commit()


def _tipos(avisos):
    return {a["kind"] for a in avisos}


# --------------------------------------------------------------------------
# Cuando NO debe avisar
# --------------------------------------------------------------------------


def test_el_primer_analisis_nunca_genera_avisos(contexto):
    """Una nota mala de partida no es un empeoramiento."""
    db, user_id, repo_id = contexto
    primero = _analisis(db, user_id, repo_id, 12)
    assert build_notifications(db, primero) == []


def test_una_caida_pequena_no_avisa(contexto):
    db, user_id, repo_id = contexto
    _analisis(db, user_id, repo_id, 70, minutos_atras=10)
    actual = _analisis(db, user_id, repo_id, 70 - (SCORE_DROP_THRESHOLD - 1))
    assert "score_drop" not in _tipos(build_notifications(db, actual))


def test_una_mejora_no_avisa(contexto):
    """Solo se avisa de lo que empeora."""
    db, user_id, repo_id = contexto
    _analisis(db, user_id, repo_id, 30, minutos_atras=10)
    actual = _analisis(db, user_id, repo_id, 90)
    assert build_notifications(db, actual) == []


def test_un_critico_que_ya_estaba_no_vuelve_a_avisar(contexto):
    db, user_id, repo_id = contexto
    anterior = _analisis(db, user_id, repo_id, 40, minutos_atras=10)
    actual = _analisis(db, user_id, repo_id, 40)
    _hallazgo(db, anterior.id, "critical", "Secreto en el repositorio")
    _hallazgo(db, actual.id, "critical", "Secreto en el repositorio")
    assert "new_critical" not in _tipos(build_notifications(db, actual))


def test_se_compara_con_el_mismo_repositorio_y_no_con_otro(contexto):
    db, user_id, repo_id = contexto
    otro = Repository(
        id=uuid.uuid4(),
        user_id=user_id,
        github_id=987654331,
        name="ajeno",
        full_name="prueba/ajeno",
        is_private=False,
    )
    db.add(otro)
    db.commit()

    _analisis(db, user_id, otro.id, 95, minutos_atras=10)
    primero_del_nuestro = _analisis(db, user_id, repo_id, 20)
    # Es el primero de ESTE repositorio, aunque otro tenga historico.
    assert build_notifications(db, primero_del_nuestro) == []


# --------------------------------------------------------------------------
# Cuando SI debe avisar
# --------------------------------------------------------------------------


def test_una_caida_grande_avisa(contexto):
    db, user_id, repo_id = contexto
    _analisis(db, user_id, repo_id, 80, minutos_atras=10)
    actual = _analisis(db, user_id, repo_id, 55)
    avisos = build_notifications(db, actual)
    assert "score_drop" in _tipos(avisos)
    assert "25" in avisos[0]["title"]


def test_un_critico_nuevo_avisa(contexto):
    db, user_id, repo_id = contexto
    anterior = _analisis(db, user_id, repo_id, 60, minutos_atras=10)
    actual = _analisis(db, user_id, repo_id, 60)
    _hallazgo(db, anterior.id, "critical", "Problema viejo")
    _hallazgo(db, actual.id, "critical", "Problema viejo")
    _hallazgo(db, actual.id, "critical", "Clave de API filtrada")

    avisos = build_notifications(db, actual)
    assert "new_critical" in _tipos(avisos)
    assert "Clave de API filtrada" in avisos[0]["body"]


def test_un_critico_nuevo_avisa_aunque_el_total_no_suba(contexto):
    """Si se arregla uno y aparece otro, el conteo no cambia pero el problema
    nuevo si existe. Por eso se comparan titulos y no cantidades."""
    db, user_id, repo_id = contexto
    anterior = _analisis(db, user_id, repo_id, 60, minutos_atras=10)
    actual = _analisis(db, user_id, repo_id, 60)
    _hallazgo(db, anterior.id, "critical", "El de antes")
    _hallazgo(db, actual.id, "critical", "El de ahora")

    assert "new_critical" in _tipos(build_notifications(db, actual))


def test_una_vulnerabilidad_nueva_avisa(contexto):
    db, user_id, repo_id = contexto
    anterior = _analisis(db, user_id, repo_id, 60, minutos_atras=10)
    actual = _analisis(db, user_id, repo_id, 60)
    _hallazgo(db, anterior.id, "low", "Nada grave", tipo="security")
    _hallazgo(db, actual.id, "high", "Dependencia vulnerable", tipo="dependency")

    assert "new_vulnerability" in _tipos(build_notifications(db, actual))


def test_una_caida_de_cobertura_avisa(contexto):
    db, user_id, repo_id = contexto
    anterior = _analisis(db, user_id, repo_id, 60, minutos_atras=10)
    actual = _analisis(db, user_id, repo_id, 60)
    _cobertura(db, anterior.id, 0.80)
    _cobertura(db, actual.id, 0.80 - (COVERAGE_DROP_THRESHOLD + 10) / 100)

    assert "coverage_drop" in _tipos(build_notifications(db, actual))


def test_una_caida_de_cobertura_pequena_no_avisa(contexto):
    db, user_id, repo_id = contexto
    anterior = _analisis(db, user_id, repo_id, 60, minutos_atras=10)
    actual = _analisis(db, user_id, repo_id, 60)
    _cobertura(db, anterior.id, 0.80)
    _cobertura(db, actual.id, 0.75)

    assert "coverage_drop" not in _tipos(build_notifications(db, actual))


def test_sin_metricas_de_cobertura_no_se_inventa_un_aviso(contexto):
    db, user_id, repo_id = contexto
    _analisis(db, user_id, repo_id, 60, minutos_atras=10)
    actual = _analisis(db, user_id, repo_id, 60)
    assert "coverage_drop" not in _tipos(build_notifications(db, actual))


# --------------------------------------------------------------------------
# Persistencia
# --------------------------------------------------------------------------


def test_los_avisos_se_guardan(contexto):
    db, user_id, repo_id = contexto
    _analisis(db, user_id, repo_id, 90, minutos_atras=10)
    actual = _analisis(db, user_id, repo_id, 50)

    assert persist_notifications(db, actual) == 1
    guardados = db.scalars(
        select(Notification).where(Notification.analysis_id == actual.id)
    ).all()
    assert len(guardados) == 1
    assert guardados[0].read_at is None


def test_reintentar_no_duplica_los_avisos(contexto):
    """Celery puede reintentar una tarea: el indice unico lo impide y eso no
    debe tratarse como un error."""
    db, user_id, repo_id = contexto
    _analisis(db, user_id, repo_id, 90, minutos_atras=10)
    actual = _analisis(db, user_id, repo_id, 50)

    persist_notifications(db, actual)
    assert persist_notifications(db, actual) == 0

    guardados = db.scalars(
        select(Notification).where(Notification.analysis_id == actual.id)
    ).all()
    assert len(guardados) == 1


# --------------------------------------------------------------------------
# Analisis lanzados por la vigilancia
# --------------------------------------------------------------------------


def test_un_analisis_automatico_cuenta_como_fue_aunque_mejore(contexto):
    """El usuario no lo pidio ni estaba delante: si no se le cuenta, la
    vigilancia es un proceso invisible."""
    db, user_id, repo_id = contexto
    _analisis(db, user_id, repo_id, 50, minutos_atras=10)
    actual = _analisis(db, user_id, repo_id, 59, origen="monitor")

    avisos = build_notifications(db, actual)
    assert "monitor_result" in _tipos(avisos)
    resultado = next(a for a in avisos if a["kind"] == "monitor_result")
    assert resultado["severity"] == "good"
    assert "subido" in resultado["title"].lower()


def test_un_analisis_manual_que_mejora_no_genera_aviso(contexto):
    """Ese resultado ya lo tiene en pantalla."""
    db, user_id, repo_id = contexto
    _analisis(db, user_id, repo_id, 50, minutos_atras=10)
    actual = _analisis(db, user_id, repo_id, 59, origen="manual")
    assert build_notifications(db, actual) == []


def test_un_analisis_automatico_sin_cambio_de_nota_no_avisa(contexto):
    """Un aviso de "sigue igual" ensena a ignorar la campana."""
    db, user_id, repo_id = contexto
    _analisis(db, user_id, repo_id, 60, minutos_atras=10)
    actual = _analisis(db, user_id, repo_id, 60, origen="monitor")
    assert "monitor_result" not in _tipos(build_notifications(db, actual))


def test_una_caida_grande_no_se_cuenta_dos_veces(contexto):
    """Ya existe un aviso propio y mas explicito para eso."""
    db, user_id, repo_id = contexto
    _analisis(db, user_id, repo_id, 90, minutos_atras=10)
    actual = _analisis(db, user_id, repo_id, 40, origen="monitor")

    tipos = _tipos(build_notifications(db, actual))
    assert "score_drop" in tipos
    assert "monitor_result" not in tipos


def test_una_caida_pequena_automatica_si_se_cuenta(contexto):
    """Por debajo del umbral no hay aviso de caida, asi que sin esto el usuario
    no se enteraria de nada."""
    db, user_id, repo_id = contexto
    _analisis(db, user_id, repo_id, 60, minutos_atras=10)
    actual = _analisis(db, user_id, repo_id, 55, origen="monitor")

    avisos = build_notifications(db, actual)
    resultado = next(a for a in avisos if a["kind"] == "monitor_result")
    assert resultado["severity"] == "medium"
    assert "bajado" in resultado["title"].lower()


def test_el_primer_analisis_vigilado_confirma_el_punto_de_partida(contexto):
    db, user_id, repo_id = contexto
    primero = _analisis(db, user_id, repo_id, 43, origen="monitor")

    avisos = build_notifications(db, primero)
    assert _tipos(avisos) == {"monitor_baseline"}
    assert "43" in avisos[0]["title"]


def test_el_primer_analisis_manual_sigue_sin_avisar(contexto):
    db, user_id, repo_id = contexto
    primero = _analisis(db, user_id, repo_id, 43, origen="manual")
    assert build_notifications(db, primero) == []
