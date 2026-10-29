"""El modelo de calidad es el de ISO/IEC 25010:2023, no el de 2011.

La version de 2023 tiene nueve caracteristicas: renombra usabilidad
(capacidad de interaccion) y portabilidad (flexibilidad) y anade proteccion
(safety). Cubrimos 8 de las 9: la proteccion queda fuera a proposito, porque
exige una evaluacion humana del riesgo real del sistema, y por decision de
producto no se ensena. Las claves internas no cambian —ver
docs/ISO_25010_MAPPING.md—, solo lo que se ensena.
"""

from types import SimpleNamespace

import pytest

from app.services import comparison_service, iso25010, report_service
from app.services.scoring_service import REPOSITORY_WEIGHTS, URL_WEIGHTS
from app.services.summary_service import build_analysis_summary


def test_estan_las_ocho_caracteristicas_de_2023_que_cubrimos():
    assert list(iso25010.CARACTERISTICAS_2023.values()) == [
        "Adecuación funcional",
        "Eficiencia de desempeño",
        "Compatibilidad",
        "Capacidad de interacción",
        "Fiabilidad",
        "Seguridad",
        "Mantenibilidad",
        "Flexibilidad",
    ]


@pytest.mark.parametrize(
    "clave, etiqueta",
    [
        # Las dos renombradas en 2023: la clave interna se conserva.
        ("usability", "Capacidad de interacción"),
        ("portability", "Flexibilidad"),
        ("performance", "Eficiencia de desempeño"),
        ("functional_suitability", "Adecuación funcional"),
        ("security", "Seguridad"),
    ],
)
def test_las_etiquetas_son_las_de_2023(clave, etiqueta):
    assert iso25010.dimension_label(clave) == etiqueta


def test_proteccion_no_se_ensena_ni_entra_en_la_nota():
    """Antes se ensenaba como "sin medir"; el dueno del producto decidio
    quitarla porque no aporta ni resta a la nota."""
    assert "safety" not in iso25010.DIMENSION_LABELS
    assert "Protección" not in iso25010.DIMENSION_LABELS.values()
    assert "safety" not in REPOSITORY_WEIGHTS
    assert "safety" not in URL_WEIGHTS


def test_el_origen_del_modo_combinado_se_conserva():
    assert iso25010.dimension_label("codigo:portability") == "Flexibilidad (código)"
    assert iso25010.dimension_label("produccion:usability") == "Capacidad de interacción (producción)"


def test_el_pdf_y_la_comparacion_usan_las_mismas_etiquetas():
    """Habia tres copias de la tabla de nombres; cada una se quedaba atras."""
    assert report_service.dimension_label("portability") == "Flexibilidad"
    assert comparison_service.DIMENSION_LABELS["portability"] == "Flexibilidad"


def test_el_pdf_solo_lista_lo_que_se_mide():
    dimensiones = [SimpleNamespace(name="security", score=80, weight=0.2)]

    filas = report_service.filas_de_dimensiones(dimensiones)

    assert filas == [["Dimensión", "Puntuación", "Peso"], ["Seguridad", "80/100", "20%"]]


def test_el_resumen_usa_las_etiquetas_nuevas():
    texto, fuente = build_analysis_summary(
        target_name="alguien/proyecto",
        is_url=False,
        overall_score=50,
        dimensions=[("portability", 90.0), ("security", 10.0)],
        findings=[],
        api_key=None,
    )

    assert fuente == "plantilla"
    assert "flexibilidad" in texto
    assert "portabilidad" not in texto
