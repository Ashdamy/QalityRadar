"""Cobertura de lenguajes en mantenibilidad.

El analizador de calidad de codigo solo entiende Python y JavaScript /
TypeScript. Un repositorio en Java se quedaba con una mantenibilidad muy
floja sin que nada dijera que la mayor parte del codigo no se habia mirado.
No se amplia el soporte: se hace visible.
"""

import tempfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.analyzers.base import AnalyzerResult
from app.analyzers.repository.code_quality import CodeQualityAnalyzer
from app.services import report_service
from app.services.scoring_service import REPOSITORY_WEIGHTS, calculate_confidence
from tests.pdf_texto import texto_del_pdf

TITULO = "Cobertura parcial de lenguajes"


def _repo(archivos: dict[str, int]) -> Path:
    """Crea un repositorio con N archivos por extension (o ruta/extension)."""
    carpeta = Path(tempfile.mkdtemp())
    for extension, cuantos in archivos.items():
        directorio, _, ext = extension.rpartition("/")
        destino = carpeta / directorio if directorio else carpeta
        destino.mkdir(parents=True, exist_ok=True)
        for i in range(cuantos):
            (destino / f"archivo{i}{ext}").write_text("x = 1\n" if ext == ".py" else "class A {}\n", encoding="utf-8")
    return carpeta


def _hallazgo(resultado):
    return next((f for f in resultado.findings if f.title == TITULO), None)


def test_un_repositorio_casi_todo_java_avisa_de_lo_que_quedo_fuera():
    resultado = CodeQualityAnalyzer().analyze(_repo({".java": 8, ".py": 2}))

    cobertura = resultado.metrics["language_coverage"]
    assert cobertura["ratio"] == 0.2
    assert cobertura["unanalyzed"] == {"Java": 8}

    hallazgo = _hallazgo(resultado)
    assert hallazgo is not None
    assert hallazgo.severity == "info"
    assert "Java" in hallazgo.description
    assert "20%" in hallazgo.description


def test_por_encima_del_setenta_por_ciento_no_hay_aviso():
    resultado = CodeQualityAnalyzer().analyze(_repo({".py": 9, ".go": 1}))

    assert resultado.metrics["language_coverage"]["ratio"] == 0.9
    assert _hallazgo(resultado) is None


def test_sin_codigo_fuente_no_hay_cobertura_que_medir():
    resultado = CodeQualityAnalyzer().analyze(_repo({}))

    assert "language_coverage" not in resultado.metrics
    assert _hallazgo(resultado) is None


def test_las_dependencias_instaladas_no_cuentan():
    """Una carpeta node_modules llena de JS no es codigo del proyecto."""
    resultado = CodeQualityAnalyzer().analyze(_repo({".java": 5, "node_modules/x/.js": 50}))

    assert resultado.metrics["language_coverage"]["ratio"] == 0.0


def _resultados(cobertura: float | None) -> list[AnalyzerResult]:
    metricas = {f"m{i}": 1 for i in range(40)}
    if cobertura is not None:
        metricas["language_coverage"] = {"ratio": cobertura, "unanalyzed": {}}
    return [AnalyzerResult(dimension="maintainability", metrics=metricas)]


def test_la_cobertura_baja_la_confianza_segun_el_peso_de_lo_no_analizado():
    completa = calculate_confidence(_resultados(1.0))
    parcial = calculate_confidence(_resultados(0.2))

    assert completa == 100.0
    # La parte de la nota que descansa en codigo no analizado: el peso de
    # mantenibilidad por lo que quedo fuera.
    assert parcial == pytest.approx(100.0 * (1 - REPOSITORY_WEIGHTS["maintainability"] * 0.8), abs=0.01)


def test_por_encima_del_umbral_no_se_toca_la_confianza():
    assert calculate_confidence(_resultados(0.9)) == calculate_confidence(_resultados(None))


def test_la_cobertura_no_cuenta_como_evidencia():
    """Es un dato sobre cuanto se miro, no sobre la calidad del codigo."""
    pocas = [AnalyzerResult(dimension="maintainability", metrics={"a": 1})]
    con_cobertura = [AnalyzerResult(dimension="maintainability", metrics={"a": 1, "language_coverage": {"ratio": 1.0}})]
    assert calculate_confidence(pocas) == calculate_confidence(con_cobertura)


def _dimension(cobertura):
    return SimpleNamespace(
        name="maintainability", score=30, weight=0.2, subcharacteristics=None,
        raw_metrics={"language_coverage": cobertura},
    )


def test_el_aviso_dice_cuanto_se_analizo_y_que_quedo_fuera():
    """Lo usan el PDF y la API (`AnalysisOut.coverage_notice`)."""
    aviso = report_service.aviso_de_cobertura(
        [_dimension({"ratio": 0.25, "unanalyzed": {"Java": 30, "Go": 5}})]
    )

    assert aviso is not None
    assert "25%" in aviso and "Java (30 archivos)" in aviso and "Go (5 archivos)" in aviso


def test_el_pdf_incluye_el_aviso():
    from datetime import datetime, timezone

    analisis = SimpleNamespace(
        overall_score=40, confidence_level=80, completed_at=datetime.now(timezone.utc),
        created_at=datetime.now(timezone.utc), summary_text=None, commit_hash=None,
        analysis_type="repository",
    )
    dims = [_dimension({"ratio": 0.1, "unanalyzed": {"Java": 9}})]
    pdf = report_service.build_analysis_report(
        repository_full_name="a/b", analysis=analisis, dimensions=dims, findings=[]
    )
    assert "Cobertura parcial de lenguajes" in texto_del_pdf(pdf)


def test_sin_cobertura_parcial_no_hay_aviso():
    assert report_service.aviso_de_cobertura([_dimension({"ratio": 0.95, "unanalyzed": {"Go": 1}})]) is None
    assert report_service.aviso_de_cobertura([_dimension(None)]) is None
