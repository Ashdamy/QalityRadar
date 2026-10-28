"""Control sobre el trabajo: cancelar, reintentar, elegir rama y listar.

Todo esto son huecos de funcionamiento, no de seguridad: cosas que el sistema
sabia hacer por dentro y no dejaba pedir por fuera.
"""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from app.api.analyses import MAX_FREE_RETRIES
from app.core.database import SessionLocal
from app.main import app
from app.models.analysis import Analysis
from app.models.deployed_app import DeployedApp
from app.models.repository import Repository
from app.models.user import User
from app.services import analysis_service
from app.services import rate_limit_service as limites

_EMAIL = "control-fixture@example.com"
_PASSWORD = "una-contrasena-larga-123"


@pytest.fixture
def cuenta():
    def _borrar():
        db = SessionLocal()
        try:
            db.execute(delete(User).where(User.email == _EMAIL))
            db.commit()
        finally:
            db.close()
        cliente = limites._client()
        for clave in cliente.scan_iter("ratelimit:*"):
            cliente.delete(clave)

    _borrar()
    navegador = TestClient(app)
    navegador.post("/api/auth/register", json={"accept_privacy": True, "email": _EMAIL, "password": _PASSWORD})
    navegador.post("/api/auth/login", json={"email": _EMAIL, "password": _PASSWORD})

    db = SessionLocal()
    try:
        usuario = db.scalar(select(User).where(User.email == _EMAIL))
        repo = Repository(
            id=uuid.uuid4(), user_id=usuario.id, github_id=555000111,
            name="proyecto", full_name="alguien/proyecto",
        )
        db.add(repo)
        db.commit()
        datos = (navegador, usuario.id, repo.id)
    finally:
        db.close()

    yield datos
    _borrar()


def _crear_analisis(user_id, repo_id, estado, **extra):
    db = SessionLocal()
    try:
        analisis = Analysis(
            id=uuid.uuid4(), user_id=user_id, repository_id=repo_id,
            analysis_type="repository", status=estado, **extra,
        )
        db.add(analisis)
        db.commit()
        return analisis.id
    finally:
        db.close()


def _estado(analysis_id):
    db = SessionLocal()
    try:
        return db.get(Analysis, analysis_id).status
    finally:
        db.close()


def _otra_cuenta(correo):
    otro = TestClient(app)
    otro.post("/api/auth/register", json={"accept_privacy": True, "email": correo, "password": _PASSWORD})
    otro.post("/api/auth/login", json={"email": correo, "password": _PASSWORD})
    return otro


def _borrar_cuenta(correo):
    db = SessionLocal()
    try:
        db.execute(delete(User).where(User.email == correo))
        db.commit()
    finally:
        db.close()


@pytest.mark.parametrize("estado", ["pending", "cloning", "running", "scoring"])
def test_se_puede_cancelar_mientras_esta_en_marcha(cuenta, estado):
    navegador, user_id, repo_id = cuenta
    aid = _crear_analisis(user_id, repo_id, estado)

    assert navegador.post(f"/api/analyses/{aid}/cancel").status_code == 204
    assert _estado(aid) == "cancelled"


def test_no_se_cancela_uno_que_ya_termino(cuenta):
    navegador, user_id, repo_id = cuenta
    aid = _crear_analisis(user_id, repo_id, "completed")

    assert navegador.post(f"/api/analyses/{aid}/cancel").status_code == 409


def test_cancelar_devuelve_el_hueco(cuenta):
    """Si no, la cuenta se queda con un hueco ocupado por algo que ya nadie
    esta haciendo, hasta que caduque el TTL."""
    navegador, user_id, repo_id = cuenta
    aid = _crear_analisis(user_id, repo_id, "running")
    limites.check_and_reserve(user_id, str(aid))
    antes = limites.current_usage(user_id)["running"]

    navegador.post(f"/api/analyses/{aid}/cancel")

    assert limites.current_usage(user_id)["running"] == antes - 1


def test_el_worker_se_entera_y_sale(cuenta):
    """No se mata la tarea: el propio trabajo comprueba y sale por su pie, que
    es lo que deja el directorio temporal borrado y el hueco libre."""
    navegador, user_id, repo_id = cuenta
    aid = _crear_analisis(user_id, repo_id, "pending")
    navegador.post(f"/api/analyses/{aid}/cancel")

    analysis_service.run_repository_analysis(str(aid))

    assert _estado(aid) == "cancelled"


def test_el_analisis_de_otro_no_se_cancela(cuenta):
    navegador, user_id, repo_id = cuenta
    aid = _crear_analisis(user_id, repo_id, "running")
    correo = "otro-control@example.com"
    ajeno = _otra_cuenta(correo)
    try:
        assert ajeno.post(f"/api/analyses/{aid}/cancel").status_code == 404
    finally:
        _borrar_cuenta(correo)


@pytest.mark.parametrize("estado", ["failed", "timeout", "cancelled"])
def test_se_reintenta_lo_que_no_termino_bien(cuenta, estado, monkeypatch):
    navegador, user_id, repo_id = cuenta
    encolados = []
    monkeypatch.setattr("app.api.analyses._COLAS", {"repository": encolados.append})
    aid = _crear_analisis(user_id, repo_id, estado, error_message="algo se rompio")

    respuesta = navegador.post(f"/api/analyses/{aid}/retry")

    assert respuesta.status_code == 202
    assert encolados == [str(aid)]
    assert _estado(aid) == "pending"


def test_reintentar_reutiliza_la_misma_fila(cuenta, monkeypatch):
    """Para que el enlace y el identificador que el usuario ya tenia sigan
    valiendo."""
    navegador, user_id, repo_id = cuenta
    monkeypatch.setattr("app.api.analyses._COLAS", {"repository": lambda _: None})
    aid = _crear_analisis(user_id, repo_id, "failed")

    devuelto = navegador.post(f"/api/analyses/{aid}/retry").json()

    assert devuelto["analysis_id"] == str(aid)


def test_reintentar_limpia_el_error_anterior(cuenta, monkeypatch):
    navegador, user_id, repo_id = cuenta
    monkeypatch.setattr("app.api.analyses._COLAS", {"repository": lambda _: None})
    aid = _crear_analisis(user_id, repo_id, "failed", error_message="algo se rompio")

    navegador.post(f"/api/analyses/{aid}/retry")

    db = SessionLocal()
    try:
        assert db.get(Analysis, aid).error_message is None
    finally:
        db.close()


def test_los_primeros_reintentos_no_gastan_cuota(cuenta, monkeypatch):
    """Si fallo por un corte de red, cobrarselo al usuario no tiene sentido."""
    navegador, user_id, repo_id = cuenta
    monkeypatch.setattr("app.api.analyses._COLAS", {"repository": lambda _: None})
    aid = _crear_analisis(user_id, repo_id, "failed")
    antes = limites.current_usage(user_id)["last_hour"]

    navegador.post(f"/api/analyses/{aid}/retry")

    assert limites.current_usage(user_id)["last_hour"] == antes


def test_pasados_los_gratuitos_el_reintento_cuenta(cuenta, monkeypatch):
    """Sin tope, reintentar gratis seria un bucle con el que saltarse los
    limites de uso."""
    navegador, user_id, repo_id = cuenta
    monkeypatch.setattr("app.api.analyses._COLAS", {"repository": lambda _: None})
    aid = _crear_analisis(user_id, repo_id, "failed", retry_count=MAX_FREE_RETRIES)
    antes = limites.current_usage(user_id)["last_hour"]

    navegador.post(f"/api/analyses/{aid}/retry")

    assert limites.current_usage(user_id)["last_hour"] == antes + 1


def test_no_se_reintenta_uno_que_fue_bien(cuenta):
    navegador, user_id, repo_id = cuenta
    aid = _crear_analisis(user_id, repo_id, "completed")

    assert navegador.post(f"/api/analyses/{aid}/retry").status_code == 409


def test_el_listado_encuentra_un_analisis_de_url(cuenta):
    """Era el hueco: a un analisis de URL no se llegaba por ningun sitio si se
    perdia el identificador."""
    navegador, user_id, _ = cuenta
    db = SessionLocal()
    try:
        aplicacion = DeployedApp(
            id=uuid.uuid4(), user_id=user_id, name="ejemplo", url="https://ejemplo.test"
        )
        db.add(aplicacion)
        db.flush()
        db.add(Analysis(
            id=uuid.uuid4(), user_id=user_id, app_id=aplicacion.id,
            analysis_type="url", status="completed", overall_score=71.5,
        ))
        db.commit()
    finally:
        db.close()

    listado = navegador.get("/api/analyses").json()

    assert len(listado) == 1
    assert listado[0]["target"] == "https://ejemplo.test"
    assert listado[0]["overall_score"] == 71.5


def test_el_listado_solo_trae_lo_tuyo(cuenta):
    navegador, user_id, repo_id = cuenta
    _crear_analisis(user_id, repo_id, "completed")
    correo = "otro-listado@example.com"
    ajeno = _otra_cuenta(correo)
    try:
        assert ajeno.get("/api/analyses").json() == []
    finally:
        _borrar_cuenta(correo)


def test_el_listado_va_del_mas_reciente_al_mas_antiguo(cuenta):
    navegador, user_id, repo_id = cuenta
    viejo = _crear_analisis(user_id, repo_id, "completed")
    nuevo = _crear_analisis(user_id, repo_id, "completed")
    db = SessionLocal()
    try:
        db.get(Analysis, viejo).created_at = datetime.now(timezone.utc) - timedelta(days=2)
        db.commit()
    finally:
        db.close()

    listado = navegador.get("/api/analyses").json()

    assert [f["id"] for f in listado] == [str(nuevo), str(viejo)]


def test_sin_sesion_no_hay_listado():
    assert TestClient(app).get("/api/analyses").status_code == 401


def test_se_puede_pedir_una_rama_concreta(cuenta, monkeypatch):
    navegador, user_id, repo_id = cuenta
    monkeypatch.setattr("app.api.repositories.queue_repository_analysis", lambda _: None)

    respuesta = navegador.post(
        f"/api/repositories/{repo_id}/analyze", json={"branch": "desarrollo"}
    )

    assert respuesta.status_code == 202
    db = SessionLocal()
    try:
        analisis = db.get(Analysis, uuid.UUID(respuesta.json()["analysis_id"]))
        assert analisis.branch == "desarrollo"
    finally:
        db.close()


def test_una_rama_con_mala_pinta_se_rechaza(cuenta):
    """El mismo patron que ya protegia al clonado: git interpreta como opcion
    lo que empiece por guion."""
    navegador, _, repo_id = cuenta

    respuesta = navegador.post(
        f"/api/repositories/{repo_id}/analyze", json={"branch": "--upload-pack=algo"}
    )

    assert respuesta.status_code == 400
