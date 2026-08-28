"""Modo combinado: consolidacion, discrepancia y correspondencia.

Se prueban las funciones puras. Las que escriben en base de datos
(`persist_discrepancy`, `copy_results_into`) se cubren de forma indirecta a
traves de la logica que si es pura: la explicacion de la discrepancia.
"""

import pytest

from app.models.analysis import Finding
from app.services.combined_service import (
    SIGNIFICANT_DISCREPANCY,
    apply_severity_cap,
    build_improvement_plan,
    consolidate_score,
    explain_discrepancy,
)
from app.services.combined_service import ORIGIN_SEPARATOR, prefixed
from app.services.correspondence_service import check_correspondence
from app.services.scoring_service import (
    CRITICAL_FINDING_SCORE_CAP,
    HIGH_FINDING_SCORE_CAP,
    REPOSITORY_WEIGHTS,
    URL_WEIGHTS,
)


def _finding(severity: str, title: str = "algo") -> Finding:
    return Finding(
        type="security",
        severity=severity,
        title=title,
        description="d",
        recommendation="r",
    )


# --------------------------------------------------------------------------
# Consolidacion
# --------------------------------------------------------------------------


def test_consolidacion_queda_entre_las_dos_notas():
    assert 40 <= consolidate_score(40, 80) <= 80


def test_consolidacion_de_notas_iguales_devuelve_esa_nota():
    assert consolidate_score(62.5, 62.5) == 62.5


def test_consolidacion_pondera_por_evidencia_no_es_media_simple():
    """El repositorio aporta seis dimensiones y la URL cinco, asi que el lado
    con mas evidencia debe pesar mas que en una media aritmetica."""
    combinada = consolidate_score(100, 0)
    assert combinada != 50.0
    assert combinada > 50.0


# --------------------------------------------------------------------------
# Discrepancia
# --------------------------------------------------------------------------


def test_diferencia_pequena_no_se_reporta_como_discrepancia():
    assert explain_discrepancy(70, 70 - (SIGNIFICANT_DISCREPANCY - 1)) is None


def test_diferencia_en_el_umbral_exacto_si_se_reporta():
    assert explain_discrepancy(70, 70 - SIGNIFICANT_DISCREPANCY) is not None


def test_produccion_mejor_que_codigo_avisa_de_la_dependencia_de_la_plataforma():
    explicacion, recomendaciones = explain_discrepancy(40, 85)
    assert "40" in explicacion and "85" in explicacion
    assert "migras" in recomendaciones


def test_codigo_mejor_que_produccion_apunta_al_despliegue():
    explicacion, recomendaciones = explain_discrepancy(85, 40)
    assert "despliegue" in explicacion
    assert "cabeceras" in recomendaciones


def test_las_dos_direcciones_dan_explicaciones_distintas():
    hacia_arriba, _ = explain_discrepancy(40, 85)
    hacia_abajo, _ = explain_discrepancy(85, 40)
    assert hacia_arriba != hacia_abajo


# --------------------------------------------------------------------------
# Plan de mejora
# --------------------------------------------------------------------------


def test_el_plan_ordena_por_gravedad_no_por_origen():
    plan = build_improvement_plan(
        [_finding("medium", "medio del codigo")],
        [_finding("critical", "critico de produccion")],
        None,
    )
    assert plan[0]["title"] == "critico de produccion"


def test_el_plan_descarta_lo_informativo_y_lo_leve():
    plan = build_improvement_plan(
        [_finding("low", "leve"), _finding("info", "informativo")], [], None
    )
    assert plan == []


def test_el_plan_no_desplaza_a_los_criticos_al_insertar_la_discrepancia():
    criticos = [_finding("critical", f"critico {i}") for i in range(3)]
    plan = build_improvement_plan(criticos, [], "arregla el despliegue")
    assert plan[0]["severity"] == "critical"
    assert plan[1]["severity"] == "critical"
    assert plan[2]["origin"] == "discrepancia"


def test_el_plan_se_limita_a_diez_acciones():
    muchos = [_finding("high", f"alto {i}") for i in range(30)]
    assert len(build_improvement_plan(muchos, muchos, None)) == 10


def test_el_plan_marca_el_origen_de_cada_accion():
    plan = build_improvement_plan(
        [_finding("high", "del codigo")], [_finding("high", "de produccion")], None
    )
    assert {item["origin"] for item in plan} == {"codigo", "produccion"}


# --------------------------------------------------------------------------
# Techo por gravedad
# --------------------------------------------------------------------------


def test_un_hallazgo_critico_limita_la_nota_consolidada():
    assert apply_severity_cap(95, [_finding("critical")]) == CRITICAL_FINDING_SCORE_CAP


def test_un_hallazgo_alto_limita_la_nota_consolidada():
    assert apply_severity_cap(95, [_finding("high")]) == HIGH_FINDING_SCORE_CAP


def test_el_techo_no_sube_una_nota_que_ya_estaba_por_debajo():
    assert apply_severity_cap(20, [_finding("critical")]) == 20


def test_sin_hallazgos_graves_la_nota_no_se_toca():
    assert apply_severity_cap(88.4, [_finding("low")]) == 88.4


# --------------------------------------------------------------------------
# Nombres de dimension al fusionar los dos analisis
# --------------------------------------------------------------------------


def test_los_dos_modos_comparten_el_nombre_security():
    """Da por sentado el conflicto que obliga a marcar el origen. Si algun dia
    dejan de coincidir, esta prueba avisa de que la premisa cambio."""
    assert set(REPOSITORY_WEIGHTS) & set(URL_WEIGHTS) == {"security"}


def test_marcar_el_origen_evita_la_colision_de_nombres():
    """La tabla tiene un indice unico sobre (analysis_id, name): sin prefijo,
    copiar las dos mitades en el mismo analisis reventaba al insertar."""
    nombres = [prefixed("codigo", n) for n in REPOSITORY_WEIGHTS] + [
        prefixed("produccion", n) for n in URL_WEIGHTS
    ]
    assert len(nombres) == len(set(nombres))
    assert len(nombres) == len(REPOSITORY_WEIGHTS) + len(URL_WEIGHTS)


def test_el_nombre_original_se_puede_recuperar_del_prefijado():
    marcado = prefixed("produccion", "security")
    origen, base = marcado.split(ORIGIN_SEPARATOR, 1)
    assert (origen, base) == ("produccion", "security")


# --------------------------------------------------------------------------
# Correspondencia entre repositorio y URL
# --------------------------------------------------------------------------

WEB = {
    "extensions": {".tsx": 12},
    "languages": {"TypeScript": 12},
    "project_shape": "frontend",
}
NO_WEB = {
    "extensions": {".py": 30},
    "languages": {"Python": 30},
    "project_shape": "backend",
}
PAGINA = "<html><body><main>Mi aplicacion</main></body></html>"


def test_nombre_y_dominio_que_coinciden_no_generan_aviso():
    resultado = check_correspondence(
        repository_full_name="ashdamy/qalitiradar",
        url="https://qalitiradar.vercel.app",
        html=PAGINA,
        structure_metrics=WEB,
    )
    assert resultado.warning is None
    assert resultado.looks_related is True
    assert resultado.kind == "ok"
    assert resultado.confidence == "alta"


def test_un_dominio_propio_por_si_solo_no_dispara_el_aviso():
    """Caso legitimo: el proyecto se sirve bajo una marca distinta. Una sola
    sospecha nunca debe bastar para advertir."""
    resultado = check_correspondence(
        repository_full_name="ashdamy/qalitiradar",
        url="https://midominiopropio.es",
        html=PAGINA,
        structure_metrics=WEB,
    )
    assert resultado.warning is None
    assert resultado.confidence == "media"


def test_pagina_por_defecto_de_la_plataforma_dispara_el_aviso():
    resultado = check_correspondence(
        repository_full_name="ashdamy/qalitiradar",
        url="https://qalitiradar.vercel.app",
        html="<html><body>404: NOT_FOUND - Deployment not found</body></html>",
        structure_metrics=WEB,
    )
    assert resultado.warning is not None
    assert resultado.looks_related is False
    assert resultado.kind == "no_deployment"


def test_repositorio_sin_front_y_dominio_ajeno_dispara_el_aviso():
    """El caso que motiva la comprobacion: se pego la URL de otra aplicacion."""
    resultado = check_correspondence(
        repository_full_name="ashdamy/scripts-de-datos",
        url="https://otra-aplicacion.vercel.app",
        html=PAGINA,
        structure_metrics=NO_WEB,
    )
    assert resultado.warning is not None
    assert resultado.kind == "possible_mismatch"
    assert resultado.confidence == "baja"
    assert any("interfaz web" in motivo for motivo in resultado.reasons)


def test_un_monorepo_de_backend_bien_nombrado_no_se_marca():
    """Solo acumula una sospecha (no genera web), asi que se informa el motivo
    pero no se advierte."""
    resultado = check_correspondence(
        repository_full_name="ashdamy/qalitiradar",
        url="https://qalitiradar.vercel.app",
        html=PAGINA,
        structure_metrics=NO_WEB,
    )
    assert resultado.warning is None


def test_sin_metricas_de_estructura_la_senal_del_repositorio_se_omite():
    """Si el analisis de estructura no dejo metricas no se puede concluir nada
    sobre el repositorio, y su ausencia no debe contar como sospecha."""
    resultado = check_correspondence(
        repository_full_name="ashdamy/qalitiradar",
        url="https://sin-relacion.example.com",
        html=PAGINA,
        structure_metrics=None,
    )
    assert resultado.warning is None


def test_las_palabras_genericas_no_cuentan_como_coincidencia():
    """La palabra "app" aparece en casi cualquier nombre y en casi cualquier
    dominio, asi que no puede dar por buena la correspondencia."""
    resultado = check_correspondence(
        repository_full_name="ashdamy/app",
        url="https://app.vercel.app",
        html=PAGINA,
        structure_metrics=WEB,
    )
    assert resultado.confidence == "media"


def test_los_motivos_se_explican_haya_aviso_o_no():
    for metricas in (WEB, NO_WEB):
        resultado = check_correspondence(
            repository_full_name="ashdamy/qalitiradar",
            url="https://qalitiradar.vercel.app",
            html=PAGINA,
            structure_metrics=metricas,
        )
        assert resultado.reasons


@pytest.mark.parametrize(
    "metricas",
    [
        {"extensions": {".html": 3}},
        {"extensions": {".vue": 3}},
        {"languages": {"JavaScript": 5}},
        {"project_shape": "fullstack"},
    ],
)
def test_distintas_formas_de_reconocer_un_proyecto_web(metricas):
    resultado = check_correspondence(
        repository_full_name="ashdamy/sin-relacion",
        url="https://otro-dominio.example.com",
        html=PAGINA,
        structure_metrics=metricas,
    )
    assert resultado.warning is None
