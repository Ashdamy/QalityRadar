"""Correcciones de la auditoria de las 20 medidas de seguridad.

Cada prueba fija un fallo que se reprodujo antes de corregirlo.
"""

import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import delete, select

from app.core.config import Settings
from app.core.database import SessionLocal
from app.main import app
from app.models.analysis import Analysis
from app.models.deployed_app import DeployedApp
from app.models.repository import Repository
from app.models.user import User
from app.services import combined_analysis_service
from app.services.report_service import build_analysis_report

_EMAIL = "auditoria-seguridad@example.com"
_PASSWORD = "s3cur3-passw0rd"


@pytest.fixture
def dentro():
    def _borrar():
        db = SessionLocal()
        try:
            db.execute(delete(User).where(User.email == _EMAIL))
            db.commit()
        finally:
            db.close()

    _borrar()
    navegador = TestClient(app)
    navegador.post("/api/auth/register", json={"accept_privacy": True, "email": _EMAIL, "password": _PASSWORD})
    navegador.post("/api/auth/login", json={"email": _EMAIL, "password": _PASSWORD})
    yield navegador
    _borrar()


# --- 17. No exponer informacion sensible --------------------------------------


def test_un_fallo_inesperado_del_combinado_no_cuenta_credenciales(dentro, monkeypatch):
    db = SessionLocal()
    try:
        usuario = db.scalar(select(User).where(User.email == _EMAIL))
        repo = Repository(
            id=uuid.uuid4(), user_id=usuario.id, github_id=555000999, name="p", full_name="alguien/p"
        )
        aplicacion = DeployedApp(id=uuid.uuid4(), user_id=usuario.id, url="https://example.com")
        db.add_all([repo, aplicacion])
        db.flush()
        analisis = Analysis(
            id=uuid.uuid4(), user_id=usuario.id, repository_id=repo.id, app_id=aplicacion.id,
            analysis_type="combined", status="pending",
        )
        db.add(analisis)
        db.commit()
        analysis_id = analisis.id
    finally:
        db.close()

    # Lo que cuenta un error real de conexion a la base: host, usuario y clave.
    def _revienta(_id):
        raise RuntimeError("connection to postgresql://qalitiradar:CLAVE-SECRETA@db-interna:5432 failed")

    monkeypatch.setattr(combined_analysis_service, "run_repository_analysis", _revienta)
    with pytest.raises(RuntimeError):
        combined_analysis_service.run_combined_analysis(str(analysis_id))

    db = SessionLocal()
    try:
        mensaje = db.get(Analysis, analysis_id).error_message
    finally:
        db.close()
    assert mensaje
    assert "CLAVE-SECRETA" not in mensaje
    assert "db-interna" not in mensaje


# --- 9 y 19. Cookies seguras cuando hay HTTPS ----------------------------------


def test_no_arranca_con_https_y_cookies_inseguras():
    with pytest.raises(ValidationError, match="COOKIE_SECURE"):
        Settings(frontend_base_url="https://qalitiradar.com", cookie_secure=False)


def test_arranca_con_https_y_cookies_seguras():
    ajustes = Settings(frontend_base_url="https://qalitiradar.com", cookie_secure=True)
    assert ajustes.cookie_secure is True


def test_en_local_por_http_las_cookies_pueden_no_ser_seguras():
    assert Settings(frontend_base_url="http://localhost:3000", cookie_secure=False).cookie_secure is False


# --- 14. Validar las entradas --------------------------------------------------


@pytest.mark.parametrize(
    "cuerpo",
    [
        {"url": "https://example.com/" + "a" * 3000},
        {"url": "https://example.com", "name": "x" * 300},
    ],
)
def test_url_y_nombre_tienen_tope(dentro, cuerpo):
    assert dentro.post("/api/apps/analyze", json=cuerpo).status_code == 422


def test_la_rama_tiene_tope(dentro):
    respuesta = dentro.post(f"/api/repositories/{uuid.uuid4()}/analyze", json={"branch": "b" * 300})
    assert respuesta.status_code == 422


# --- 15. Escapar el contenido del usuario --------------------------------------


@pytest.mark.parametrize("nombre", ["https://ejemplo.com/<b>x", 'https://e.com/<link href="javascript:x">y'])
def test_el_pdf_escapa_el_titulo(nombre):
    analisis = SimpleNamespace(
        overall_score=50, confidence_level=0.8, completed_at=datetime.now(timezone.utc),
        created_at=datetime.now(timezone.utc), summary_text=None, commit_hash=None, analysis_type="url",
    )
    pdf = build_analysis_report(repository_full_name=nombre, analysis=analisis, dimensions=[], findings=[])
    assert pdf.startswith(b"%PDF")
