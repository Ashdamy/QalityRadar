"""Desglose de cada dimension en subcaracteristicas de ISO/IEC 25010:2023.

La nota de una dimension sigue siendo la misma: el desglose solo ensena de
donde sale. Y lo que la norma define pero aun no se mide se lista como
"sin medir", nunca como 0.
"""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.services import report_service
from app.services.scoring_service import (
    DIMENSION_RUBRICS,
    URL_RUBRICS,
    score_dimension,
    score_url_dimension,
    subcharacteristics,
)

CALIBRACION = json.loads(
    (Path(__file__).parent / "fixtures" / "calibracion_2026_10.json").read_text(encoding="utf-8")
)
REPOS = [nombre for nombre in CALIBRACION if not nombre.startswith("_")]

# Metricas de ejemplo para el modo URL: una pagina razonable y una vacia.
URL_METRICAS = [
    {},
    {
        "uses_https": True, "has_hsts": True, "hsts_max_age": 31536000, "cookie_count": 2,
        "cookies_without_httponly": 0, "cookies_without_secure": 1, "has_csp": True,
        "csp_allows_unsafe_inline": True, "csp_directives_present": ["a", "b", "c"],
        "mixed_content_count": 0, "has_x_frame_options": True, "response_seconds": 0.5,
        "uses_compression": True, "image_count": 4, "images_without_alt": 1, "has_title": True,
        "title_length": 30, "has_viewport": True, "has_doctype": True, "declares_language": True,
        "has_h1": True, "h1_count": 1, "form_inputs": 2, "inputs_without_label": 1,
    },
    {"uses_https": False, "response_seconds": 3.0, "image_count": 0, "has_title": False, "has_viewport": False},
]


def _medidas(subs):
    return [s for s in subs if s["measured"]]


@pytest.mark.parametrize("repo", REPOS)
@pytest.mark.parametrize("dimension", sorted(DIMENSION_RUBRICS))
def test_con_datos_reales_la_nota_no_cambia_y_el_desglose_suma_la_nota(repo, dimension):
    """Las notas de la instantanea las dio el codigo ANTES de desglosar."""
    metricas = CALIBRACION[repo]["metrics"].get(dimension)
    if metricas is None:
        pytest.skip("este repositorio no tuvo esta dimension")

    nota = score_dimension(dimension, metricas, [])
    subs = subcharacteristics(dimension, metricas)

    assert nota == CALIBRACION[repo]["dimensions"][dimension]
    assert round(sum(s["earned"] for s in _medidas(subs)), 2) == nota


@pytest.mark.parametrize("metricas", URL_METRICAS)
@pytest.mark.parametrize("dimension", sorted(URL_RUBRICS))
def test_en_modo_url_el_desglose_suma_la_nota(dimension, metricas):
    subs = subcharacteristics(dimension, metricas, url=True)
    assert round(sum(s["earned"] for s in _medidas(subs)), 2) == score_url_dimension(dimension, metricas)


@pytest.mark.parametrize(
    "dimension, url", [(d, False) for d in DIMENSION_RUBRICS] + [(d, True) for d in URL_RUBRICS]
)
def test_los_maximos_suman_cien_y_nadie_pasa_de_su_maximo(dimension, url):
    for metricas in [{}, *URL_METRICAS, *(CALIBRACION[r]["metrics"].get(dimension, {}) for r in REPOS)]:
        subs = _medidas(subcharacteristics(dimension, metricas, url=url))
        assert sum(s["max"] for s in subs) == 100
        assert all(0 <= s["earned"] <= s["max"] for s in subs)


@pytest.mark.parametrize(
    "dimension, url, esperadas",
    [
        ("security", False, {"No repudio", "Responsabilidad", "Autenticidad", "Resistencia"}),
        ("security", True, {"No repudio", "Responsabilidad", "Autenticidad"}),
        ("maintainability", False, {"Reusabilidad", "Capacidad de prueba"}),
        ("portability", False, {"Escalabilidad", "Reemplazabilidad"}),
        ("reliability", False, {"Disponibilidad"}),
        ("functional_suitability", False, {"Corrección funcional"}),
    ],
)
def test_lo_que_no_se_mide_aparece_como_sin_medir_no_como_cero(dimension, url, esperadas):
    subs = subcharacteristics(dimension, {}, url=url)
    sin_medir = {s["name"] for s in subs if not s["measured"]}

    assert esperadas <= sin_medir
    assert all(s["earned"] is None and s["max"] is None for s in subs if not s["measured"])


def test_lo_que_no_es_subcaracteristica_iso_va_marcado():
    """La gobernanza del proyecto y el CI/CD suman puntos, pero no son ISO."""
    flexibilidad = {s["name"]: s for s in subcharacteristics("portability", {})}
    adecuacion = {s["name"]: s for s in subcharacteristics("functional_suitability", {})}

    assert flexibilidad["Instalabilidad"]["iso"] is True
    assert flexibilidad["Automatización (CI/CD)"]["iso"] is False
    assert adecuacion["Gobernanza del proyecto"]["iso"] is False


def test_una_dimension_desconocida_no_tiene_desglose():
    assert subcharacteristics("dimension_nueva", {}) == []


@pytest.fixture
def dentro():
    from fastapi.testclient import TestClient
    from sqlalchemy import delete

    from app.core.database import SessionLocal
    from app.main import app
    from app.models.user import User

    email = "subcaracteristicas@example.com"

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
        user_id = db.query(User).filter_by(email=email).one().id
    finally:
        db.close()
    yield navegador, user_id
    _borrar()


def test_la_api_devuelve_el_desglose_guardado_y_null_en_analisis_antiguos(dentro):
    import uuid

    from app.core.database import SessionLocal
    from app.models.analysis import Analysis, Dimension
    from app.models.deployed_app import DeployedApp

    navegador, user_id = dentro
    desglose = subcharacteristics("security", {"uses_https": False}, url=True)
    db = SessionLocal()
    try:
        aplicacion = DeployedApp(id=uuid.uuid4(), user_id=user_id, url="https://example.com")
        db.add(aplicacion)
        db.flush()
        analisis = Analysis(
            id=uuid.uuid4(), user_id=user_id, app_id=aplicacion.id,
            analysis_type="url", status="completed", overall_score=5,
        )
        db.add(analisis)
        db.flush()
        db.add_all([
            Dimension(id=uuid.uuid4(), analysis_id=analisis.id, name="security", score=5,
                      weight=0.25, subcharacteristics=desglose),
            # Un analisis anterior al desglose no lo tiene.
            Dimension(id=uuid.uuid4(), analysis_id=analisis.id, name="performance", score=10, weight=0.25),
        ])
        db.commit()
        analysis_id = analisis.id
    finally:
        db.close()

    dims = {d["name"]: d for d in navegador.get(f"/api/analyses/{analysis_id}").json()["dimensions"]}

    # `origin` solo lo trae mantenibilidad; en el resto la API lo da nulo.
    assert dims["security"]["subcharacteristics"] == [{**s, "origin": None} for s in desglose]
    assert dims["performance"]["subcharacteristics"] is None


def test_el_pdf_lista_el_desglose():
    dimension = SimpleNamespace(
        name="security",
        score=50,
        weight=0.2,
        subcharacteristics=[
            {"name": "Confidencialidad", "earned": 30, "max": 50, "measured": True, "iso": True},
            {"name": "No repudio", "earned": None, "max": None, "measured": False, "iso": True},
        ],
    )

    filas = report_service.filas_de_subcaracteristicas([dimension])

    assert ["Seguridad", "", ""] in filas
    assert ["Confidencialidad", "30/50", ""] in filas
    assert ["No repudio", "sin medir", ""] in filas


def test_el_pdf_de_un_analisis_antiguo_sin_desglose_no_falla():
    dimension = SimpleNamespace(name="security", score=50, weight=0.2, subcharacteristics=None)
    assert report_service.filas_de_subcaracteristicas([dimension]) == []
