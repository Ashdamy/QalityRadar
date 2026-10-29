"""El modelo de calidad es el de ISO/IEC 25010:2023, no el de 2011.

La version de 2023 tiene nueve caracteristicas: renombra usabilidad
(capacidad de interaccion) y portabilidad (flexibilidad) y anade proteccion
(safety). Las claves internas no cambian —ver docs/ISO_25010_MAPPING.md—,
solo lo que se ensena.
"""

from types import SimpleNamespace

import pytest

from app.services import comparison_service, iso25010, report_service
from app.services.scoring_service import REPOSITORY_WEIGHTS, URL_WEIGHTS
from app.services.summary_service import build_analysis_summary


def test_estan_las_nueve_caracteristicas_de_2023():
    assert list(iso25010.CARACTERISTICAS_2023.values()) == [
        "Adecuación funcional",
        "Eficiencia de desempeño",
        "Compatibilidad",
        "Capacidad de interacción",
        "Fiabilidad",
        "Seguridad",
        "Mantenibilidad",
        "Flexibilidad",
        "Protección",
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


def test_proteccion_existe_pero_no_se_mide():
    assert iso25010.dimension_label("safety") == "Protección"
    assert "safety" in iso25010.SIN_MEDIR
    # Fuera del denominador: no puede bajar ni subir la nota.
    assert "safety" not in REPOSITORY_WEIGHTS
    assert "safety" not in URL_WEIGHTS


def test_el_origen_del_modo_combinado_se_conserva():
    assert iso25010.dimension_label("codigo:portability") == "Flexibilidad (código)"
    assert iso25010.dimension_label("produccion:usability") == "Capacidad de interacción (producción)"


def test_el_pdf_y_la_comparacion_usan_las_mismas_etiquetas():
    """Habia tres copias de la tabla de nombres; cada una se quedaba atras."""
    assert report_service.dimension_label("portability") == "Flexibilidad"
    assert comparison_service.DIMENSION_LABELS["portability"] == "Flexibilidad"


def test_el_pdf_lista_proteccion_como_sin_medir():
    dimensiones = [SimpleNamespace(name="security", score=80, weight=0.2)]

    filas = report_service.filas_de_dimensiones(dimensiones)

    assert ["Seguridad", "80/100", "20%"] in filas
    assert ["Protección", "sin medir", "—"] in filas


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
