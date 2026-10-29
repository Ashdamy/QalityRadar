"""La actividad del proyecto sale de la nota ISO.

Puntuaba estrellas, forks y frescura, y pesaba un 15% de la nota global.
Nada de eso es calidad segun ISO/IEC 25010. Se sigue calculando y se ensena
aparte como indicador de salud, pero no mueve la nota.
"""

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.analyzers.base import FindingData
from app.services import report_service
from app.services.combined_service import consolidate_score
from app.services.scoring_service import (
    HEALTH_INDICATORS,
    REPOSITORY_WEIGHTS,
    calculate_overall_score,
    dimension_weight,
    score_dimension,
)
from app.services.summary_service import build_analysis_summary

CALIBRACION = json.loads(
    (Path(__file__).parent / "fixtures" / "calibracion_2026_10.json").read_text(encoding="utf-8")
)

# Pesos que habia antes, con la actividad dentro: sirven para comprobar que la
# instantanea reproduce las notas publicadas y que el cambio es solo ese.
PESOS_2011 = {
    "functional_suitability": 0.15, "reliability": 0.20, "security": 0.20,
    "maintainability": 0.20, "portability": 0.10, "project_activity": 0.15,
}


def _hallazgos(repo):
    return [FindingData(type="security", severity=s, title="", description="") for s in CALIBRACION[repo]["severities"]]


def test_la_actividad_no_tiene_peso_y_los_demas_suman_uno():
    assert "project_activity" not in REPOSITORY_WEIGHTS
    assert set(REPOSITORY_WEIGHTS) == {
        "functional_suitability", "reliability", "security", "maintainability", "portability",
    }
    assert sum(REPOSITORY_WEIGHTS.values()) == pytest.approx(1.0)
    # Renormalizados, no cambiados: guardan la misma proporcion entre si.
    assert REPOSITORY_WEIGHTS["security"] / REPOSITORY_WEIGHTS["portability"] == pytest.approx(2.0)


def test_la_actividad_se_sigue_calculando_y_se_guarda_sin_peso():
    assert "project_activity" in HEALTH_INDICATORS
    assert dimension_weight("project_activity") == 0.0
    assert dimension_weight("security") == REPOSITORY_WEIGHTS["security"]
    metricas = CALIBRACION["pallets/flask"]["metrics"]["project_activity"]
    assert score_dimension("project_activity", metricas, []) == 100.0


def test_el_combinado_pondera_por_caracteristicas_iso_medidas():
    """Sin la actividad, codigo y produccion aportan cinco caracteristicas
    cada uno, y pesan lo mismo."""
    assert consolidate_score(100, 0) == 50.0
    assert consolidate_score(70, 40) == 55.0


def test_el_resumen_no_presenta_la_actividad_como_lo_mas_solido():
    texto, _ = build_analysis_summary(
        target_name="x", is_url=False, overall_score=40,
        dimensions=[("project_activity", 100.0), ("security", 60.0), ("reliability", 20.0)],
        findings=[], api_key=None,
    )
    assert "actividad" not in texto
    assert "seguridad (60/100)" in texto


def test_el_pdf_saca_la_actividad_de_la_tabla_iso_y_la_ensena_aparte():
    dims = [
        SimpleNamespace(name="security", score=60, weight=0.235, subcharacteristics=None),
        SimpleNamespace(name="project_activity", score=37, weight=0.0, subcharacteristics=None),
    ]

    tabla_iso = report_service.filas_de_dimensiones(dims)
    salud = report_service.filas_de_salud(dims)

    assert not any("Actividad" in fila[0] for fila in tabla_iso)
    assert salud == [["Actividad del proyecto", "37/100"]]


# --- Migracion de datos -------------------------------------------------------

_MIGRACION = Path(__file__).parents[1] / "alembic" / "versions" / "0023_actividad_fuera_de_la_nota.py"


def _migracion():
    spec = importlib.util.spec_from_file_location("migracion_0023", _MIGRACION)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


@pytest.mark.parametrize("repo", ["pallets/flask", "axios/axios", "octocat/Hello-World"])
def test_la_migracion_calcula_lo_mismo_que_la_aplicacion(repo):
    """La migracion no importa codigo de la aplicacion (que cambia con el
    tiempo): lleva su propia copia de la formula, y tiene que coincidir."""
    migracion = _migracion()
    dims = CALIBRACION[repo]["dimensions"]
    severidades = set(CALIBRACION[repo]["severities"])

    assert migracion.nota(dims, severidades, migracion.PESOS_NUEVOS) == calculate_overall_score(dims, _hallazgos(repo))
    # Y hacia atras devuelve la nota de antes.
    assert migracion.nota(dims, severidades, migracion.PESOS_VIEJOS) == round(
        sum(PESOS_2011[d] * s for d, s in dims.items()) / sum(PESOS_2011.values()), 2
    )
