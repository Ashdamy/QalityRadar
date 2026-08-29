"""Semana 5: enlaces publicos temporales y limites de uso.

Los dos comparten una idea: son las defensas que hacen falta para que el
servicio pueda estar abierto. El enlace da acceso sin sesion, asi que el token
tiene que ser la credencial completa; los limites impiden que una sola cuenta
agote la maquina.
"""

import time
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete

from app.core.database import SessionLocal
from app.main import app
from app.models.analysis import Analysis
from app.models.deployed_app import DeployedApp
from app.models.shared_report import SharedReport
from app.models.user import User
from app.services import rate_limit_service as limites
from app.services.rate_limit_service import (
    HOUR_SECONDS,
    MAX_CONCURRENT,
    MAX_PER_DAY,
    MAX_PER_HOUR,
    RateLimitExceeded,
    check_and_reserve,
    current_usage,
    release,
)
from app.services.share_service import (
    create_share_link,
    resolve_share_token,
    revoke_share_link,
)

client = TestClient(app)

_EMAIL = "semana5-fixture@example.com"


@pytest.fixture
def usuario():
    """Un usuario con un analisis terminado, listo para compartir."""

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
        fila = User(id=uuid.uuid4(), email=_EMAIL, password_hash="x")
        db.add(fila)
        # Sin relaciones ORM declaradas, SQLAlchemy no deduce el orden de
        # insercion y las claves ajenas fallan: hay que forzarlo.
        db.flush()
        # La tabla exige que el analisis apunte a un repositorio o a una
        # aplicacion; no puede quedar huerfano.
        aplicacion = DeployedApp(
            id=uuid.uuid4(),
            user_id=fila.id,
            name="ejemplo",
            url="https://ejemplo.test",
        )
        db.add(aplicacion)
        db.flush()
        analisis = Analysis(
            id=uuid.uuid4(),
            user_id=fila.id,
            app_id=aplicacion.id,
            analysis_type="url",
            status="completed",
            overall_score=72,
        )
        db.add(analisis)
        db.commit()
        yield fila.id, analisis.id
    finally:
        db.close()
        _limpiar()


def _limpiar_limites(user_id):
    cliente = limites._client()
    cliente.delete(limites._HISTORY_KEY.format(user_id=user_id))
    cliente.delete(limites._RUNNING_KEY.format(user_id=user_id))
    # El tope de la maquina es compartido: si no se vacia, lo que reserve una
    # prueba hace fallar a la siguiente.
    cliente.delete(limites._GLOBAL_RUNNING_KEY)


# --------------------------------------------------------------------------
# Enlaces compartidos
# --------------------------------------------------------------------------


def test_un_enlace_recien_creado_resuelve_al_analisis(usuario):
    _, analysis_id = usuario
    db = SessionLocal()
    try:
        analisis = db.get(Analysis, analysis_id)
        enlace = create_share_link(db, analisis)
        db.commit()
        assert resolve_share_token(db, enlace.token).id == analysis_id
    finally:
        db.close()


def test_el_token_es_largo_e_impredecible(usuario):
    """Es la credencial completa: si fuera corto, se podria probar a ciegas."""
    _, analysis_id = usuario
    db = SessionLocal()
    try:
        analisis = db.get(Analysis, analysis_id)
        primero = create_share_link(db, analisis)
        segundo = create_share_link(db, analisis)
        db.commit()
        assert len(primero.token) >= 40
        assert primero.token != segundo.token
    finally:
        db.close()


def test_un_enlace_caducado_deja_de_resolver(usuario):
    _, analysis_id = usuario
    db = SessionLocal()
    try:
        caducado = SharedReport(
            id=uuid.uuid4(),
            analysis_id=analysis_id,
            token="token-caducado-de-prueba",
            expires_at=datetime.now(timezone.utc) - timedelta(minutes=1),
        )
        db.add(caducado)
        db.commit()
        assert resolve_share_token(db, "token-caducado-de-prueba") is None
    finally:
        db.close()


def test_un_token_inexistente_y_uno_caducado_son_indistinguibles(usuario):
    """Si se distinguieran, el endpoint publico diria que tokens existieron."""
    _, analysis_id = usuario
    db = SessionLocal()
    try:
        db.add(
            SharedReport(
                id=uuid.uuid4(),
                analysis_id=analysis_id,
                token="otro-token-caducado",
                expires_at=datetime.now(timezone.utc) - timedelta(days=1),
            )
        )
        db.commit()
        assert resolve_share_token(db, "otro-token-caducado") is None
        assert resolve_share_token(db, "jamas-existio") is None
    finally:
        db.close()

    caducado = client.get("/api/reports/shared/otro-token-caducado")
    inexistente = client.get("/api/reports/shared/jamas-existio")
    assert caducado.status_code == inexistente.status_code == 404
    assert caducado.json() == inexistente.json()


def test_el_informe_compartido_se_lee_sin_autenticacion(usuario):
    _, analysis_id = usuario
    db = SessionLocal()
    try:
        enlace = create_share_link(db, db.get(Analysis, analysis_id))
        db.commit()
        token = enlace.token
    finally:
        db.close()

    respuesta = client.get(f"/api/reports/shared/{token}")
    assert respuesta.status_code == 200
    assert respuesta.json()["overall_score"] == 72.0


def test_revocar_un_enlace_lo_invalida(usuario):
    _, analysis_id = usuario
    db = SessionLocal()
    try:
        analisis = db.get(Analysis, analysis_id)
        enlace = create_share_link(db, analisis)
        db.commit()
        token = enlace.token

        assert revoke_share_link(db, analisis, token) is True
        db.commit()
        assert resolve_share_token(db, token) is None
    finally:
        db.close()


def test_revocar_un_enlace_no_afecta_a_los_demas(usuario):
    """Cada enlace se revoca por separado: repartir dos y anular uno no debe
    tumbar el otro."""
    _, analysis_id = usuario
    db = SessionLocal()
    try:
        analisis = db.get(Analysis, analysis_id)
        primero = create_share_link(db, analisis)
        segundo = create_share_link(db, analisis)
        db.commit()

        revoke_share_link(db, analisis, primero.token)
        db.commit()
        assert resolve_share_token(db, primero.token) is None
        assert resolve_share_token(db, segundo.token) is not None
    finally:
        db.close()


def test_la_caducidad_no_puede_estirarse_sin_limite(usuario):
    _, analysis_id = usuario
    db = SessionLocal()
    try:
        enlace = create_share_link(db, db.get(Analysis, analysis_id), expiry_days=9999)
        db.commit()
        margen = enlace.expires_at - datetime.now(timezone.utc)
        assert margen <= timedelta(days=31)
    finally:
        db.close()


def test_compartir_exige_sesion():
    respuesta = client.post(f"/api/analyses/{uuid.uuid4()}/share")
    assert respuesta.status_code == 401


# --------------------------------------------------------------------------
# Limites de uso
# --------------------------------------------------------------------------


def test_el_sexto_analisis_de_la_hora_se_rechaza():
    user_id = uuid.uuid4()
    _limpiar_limites(user_id)
    try:
        for _ in range(MAX_PER_HOUR):
            reserva = str(uuid.uuid4())
            check_and_reserve(user_id, reserva)
            # Se libera el hueco de simultaneos para aislar el limite horario.
            release(user_id, reserva)

        with pytest.raises(RateLimitExceeded) as excinfo:
            check_and_reserve(user_id, str(uuid.uuid4()))
        assert "hora" in excinfo.value.message
        assert excinfo.value.retry_after_seconds > 0
    finally:
        _limpiar_limites(user_id)


def test_no_se_permiten_mas_de_dos_analisis_a_la_vez():
    user_id = uuid.uuid4()
    _limpiar_limites(user_id)
    try:
        for _ in range(MAX_CONCURRENT):
            check_and_reserve(user_id, str(uuid.uuid4()))

        with pytest.raises(RateLimitExceeded) as excinfo:
            check_and_reserve(user_id, str(uuid.uuid4()))
        assert "en curso" in excinfo.value.message
    finally:
        _limpiar_limites(user_id)


def test_liberar_un_hueco_permite_encolar_otro():
    user_id = uuid.uuid4()
    _limpiar_limites(user_id)
    try:
        primera = str(uuid.uuid4())
        check_and_reserve(user_id, primera)
        check_and_reserve(user_id, str(uuid.uuid4()))
        release(user_id, primera)
        check_and_reserve(user_id, str(uuid.uuid4()))  # no debe lanzar
    finally:
        _limpiar_limites(user_id)


def test_el_limite_diario_tambien_corta():
    user_id = uuid.uuid4()
    _limpiar_limites(user_id)
    cliente = limites._client()
    historial = limites._HISTORY_KEY.format(user_id=user_id)
    ahora = time.time()
    try:
        # Repartidos a lo largo del dia, de modo que ninguno cae en la ultima
        # hora: asi se comprueba el limite diario y no el horario.
        for i in range(MAX_PER_DAY):
            cliente.zadd(historial, {str(uuid.uuid4()): ahora - 7200 - i * 60})

        with pytest.raises(RateLimitExceeded) as excinfo:
            check_and_reserve(user_id, str(uuid.uuid4()))
        assert "diarios" in excinfo.value.message
    finally:
        _limpiar_limites(user_id)


def test_lo_que_sale_de_la_ventana_deja_de_contar():
    """Con contadores por hora natural se podrian lanzar 5 a las 10:59 y otros
    5 a las 11:00. La ventana deslizante lo impide, pero tambien debe olvidar
    lo viejo."""
    user_id = uuid.uuid4()
    _limpiar_limites(user_id)
    cliente = limites._client()
    historial = limites._HISTORY_KEY.format(user_id=user_id)
    ahora = time.time()
    try:
        for _ in range(MAX_PER_HOUR):
            cliente.zadd(historial, {str(uuid.uuid4()): ahora - HOUR_SECONDS - 60})
        check_and_reserve(user_id, str(uuid.uuid4()))  # no debe lanzar
    finally:
        _limpiar_limites(user_id)


def test_el_consumo_refleja_lo_reservado():
    user_id = uuid.uuid4()
    _limpiar_limites(user_id)
    try:
        check_and_reserve(user_id, str(uuid.uuid4()))
        uso = current_usage(user_id)
        assert uso["last_hour"] == 1
        assert uso["running"] == 1
        assert uso["max_per_hour"] == MAX_PER_HOUR
        assert uso["max_concurrent"] == MAX_CONCURRENT
    finally:
        _limpiar_limites(user_id)


def test_liberar_una_reserva_inexistente_no_revienta():
    """Se llama desde un `finally`: no puede tapar el resultado del analisis."""
    release(uuid.uuid4(), "no-existe")


def test_los_limites_de_distintos_usuarios_no_se_mezclan():
    uno, otro = uuid.uuid4(), uuid.uuid4()
    _limpiar_limites(uno)
    _limpiar_limites(otro)
    try:
        for _ in range(MAX_CONCURRENT):
            check_and_reserve(uno, str(uuid.uuid4()))
        check_and_reserve(otro, str(uuid.uuid4()))  # no debe lanzar
    finally:
        _limpiar_limites(uno)
        _limpiar_limites(otro)
