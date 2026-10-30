"""Veredicto de conformidad: apto, apto condicionado o no apto.

Se calcula al leer el analisis, sin guardarlo: sale de la nota, los
hallazgos y la confianza, que ya estan guardados.
"""

from types import SimpleNamespace

import pytest

from app.services.veredicto import (
    APTO,
    APTO_CONDICIONADO,
    NO_APTO,
    TEXTO_FIJO,
    calcular_veredicto,
)


def h(severity, type="security", title="algo"):
    return SimpleNamespace(severity=severity, type=type, title=title)


COBERTURA = h("info", "structure", "Cobertura parcial de lenguajes")


# --- Bordes de la nota -----------------------------------------------------------


@pytest.mark.parametrize(
    "nota, nivel",
    [(60, APTO), (59.99, APTO_CONDICIONADO), (59, APTO_CONDICIONADO),
     (40, APTO_CONDICIONADO), (39.99, NO_APTO), (39, NO_APTO), (100, APTO), (0, NO_APTO)],
)
def test_bordes_de_la_nota_sin_hallazgos_graves(nota, nivel):
    assert calcular_veredicto(nota, [h("medium"), h("low")], 90)["nivel"] == nivel


# --- Hallazgos altos y criticos ----------------------------------------------------


def test_un_alto_condiciona_aunque_la_nota_sea_buena():
    v = calcular_veredicto(70, [h("high")], 90)
    assert v["nivel"] == APTO_CONDICIONADO
    assert "Hay 1 hallazgo alto en Seguridad" in v["motivos"]


def test_sin_altos_ni_criticos_con_buena_nota_es_apto():
    v = calcular_veredicto(70, [h("medium")], 90)
    assert v["nivel"] == APTO
    assert v["provisional"] is False


def test_un_critico_es_no_apto_aunque_la_nota_sea_buena():
    v = calcular_veredicto(80, [h("critical")], 90)
    assert v["nivel"] == NO_APTO
    assert "Hay 1 hallazgo crítico en Seguridad" in v["motivos"]


def test_gana_el_caso_mas_severo():
    """Nota de condicionado con un critico: no apto."""
    assert calcular_veredicto(55, [h("high"), h("critical")], 90)["nivel"] == NO_APTO


def test_los_hallazgos_se_agrupan_por_area_y_en_plural():
    v = calcular_veredicto(
        70,
        [h("high", "security"), h("high", "dependency"), h("high", "test_coverage")],
        90,
    )
    # Dependencias vulnerables son seguridad; la cobertura de pruebas, fiabilidad.
    assert "Hay 2 hallazgos altos en Seguridad" in v["motivos"]
    assert "Hay 1 hallazgo alto en Fiabilidad" in v["motivos"]


# --- Provisional -------------------------------------------------------------------


@pytest.mark.parametrize("confianza, provisional", [(49, True), (49.99, True), (50, False), (100, False)])
def test_bordes_de_la_confianza(confianza, provisional):
    v = calcular_veredicto(70, [], confianza)
    assert v["provisional"] is provisional
    assert v["nivel"] == APTO  # la confianza no cambia el nivel, lo matiza


def test_la_cobertura_parcial_lo_hace_provisional():
    v = calcular_veredicto(70, [COBERTURA], 90)
    assert v["provisional"] is True
    assert v["nivel"] == APTO
    assert any("cobertura parcial" in m.lower() for m in v["motivos"])


def test_sin_confianza_conocida_es_provisional():
    assert calcular_veredicto(70, [], None)["provisional"] is True


# --- Motivos y casos limite ----------------------------------------------------------


@pytest.mark.parametrize(
    "nota, esperado",
    [(72, "La nota global es 72, igual o superior a 60"),
     (52, "La nota global es 52, entre 40 y 59"),
     (35, "La nota global es 35, por debajo de 40")],
)
def test_el_primer_motivo_explica_la_nota(nota, esperado):
    assert calcular_veredicto(nota, [], 90)["motivos"][0].startswith(esperado)


def test_sin_nota_no_hay_veredicto():
    """Un analisis fallido o en marcha no se juzga."""
    assert calcular_veredicto(None, [], 90) is None


def test_el_texto_fijo():
    assert TEXTO_FIJO == "Indicador interno basado en ISO/IEC 25010. No constituye una certificación oficial."


# --- API y PDF ------------------------------------------------------------------------


@pytest.fixture
def analisis_guardado():
    """Un analisis de URL completado con un hallazgo alto, de un usuario con sesion."""
    import uuid

    from fastapi.testclient import TestClient
    from sqlalchemy import delete

    from app.core.database import SessionLocal
    from app.main import app
    from app.models.analysis import Analysis, Finding
    from app.models.deployed_app import DeployedApp
    from app.models.user import User

    email = "veredicto@example.com"

    def _borrar():
        db = SessionLocal()
        try:
            db.execute(delete(User).where(User.email == email))
            db.commit()
        finally:
            db.close()

    _borrar()
    navegador = TestClient(app)
    navegador.post("/api/auth/register", json={"accept_privacy": True, "email": email, "password": "s3cur3-passw0rd"})
    navegador.post("/api/auth/login", json={"email": email, "password": "s3cur3-passw0rd"})
    db = SessionLocal()
    try:
        usuario = db.query(User).filter_by(email=email).one()
        aplicacion = DeployedApp(id=uuid.uuid4(), user_id=usuario.id, url="https://example.com")
        db.add(aplicacion)
        db.flush()
        hecho = Analysis(id=uuid.uuid4(), user_id=usuario.id, app_id=aplicacion.id, analysis_type="url",
                         status="completed", overall_score=68, confidence_level=40)
        en_marcha = Analysis(id=uuid.uuid4(), user_id=usuario.id, app_id=aplicacion.id, analysis_type="url",
                             status="running")
        db.add_all([hecho, en_marcha])
        db.flush()
        db.add(Finding(id=uuid.uuid4(), analysis_id=hecho.id, type="security", severity="high",
                       title="Sin HSTS", description="x"))
        db.commit()
        datos = (navegador, hecho.id, en_marcha.id)
    finally:
        db.close()
    yield datos
    _borrar()


def test_la_api_devuelve_el_veredicto(analisis_guardado):
    navegador, hecho, en_marcha = analisis_guardado

    v = navegador.get(f"/api/analyses/{hecho}").json()["verdict"]

    assert v["nivel"] == APTO_CONDICIONADO
    assert v["etiqueta"] == "Apto condicionado"
    assert v["provisional"] is True  # confianza 40
    assert "Hay 1 hallazgo alto en Seguridad" in v["motivos"]
    assert v["aviso"] == TEXTO_FIJO
    assert navegador.get(f"/api/analyses/{en_marcha}").json()["verdict"] is None


def test_el_informe_compartido_tambien_lo_lleva(analisis_guardado):
    from fastapi.testclient import TestClient

    from app.main import app

    navegador, hecho, _ = analisis_guardado
    token = navegador.post(f"/api/analyses/{hecho}/share", json={}).json()["token"]

    v = TestClient(app).get(f"/api/reports/shared/{token}").json()["verdict"]
    assert v["nivel"] == APTO_CONDICIONADO


def test_el_pdf_lleva_el_veredicto_en_la_primera_pagina():
    from datetime import datetime, timezone

    from app.services.report_service import build_analysis_report
    from tests.pdf_texto import paginas_del_pdf

    analisis = SimpleNamespace(
        overall_score=35, confidence_level=90, completed_at=datetime.now(timezone.utc),
        created_at=datetime.now(timezone.utc), summary_text=None, commit_hash=None, analysis_type="url",
    )
    pdf = build_analysis_report(
        repository_full_name="a/b", analysis=analisis, dimensions=[],
        findings=[SimpleNamespace(severity="critical", type="security", title="Secreto expuesto",
                                  description="x", file_path=None, recommendation=None)],
    )
    primera = paginas_del_pdf(pdf)[0]

    assert "No apto" in primera
    assert "Hay 1 hallazgo cr" in primera  # la tilde va escapada en el PDF
    assert "Indicador interno basado en ISO/IEC 25010" in primera
