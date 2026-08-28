"""Convierte evidencia en puntuaciones ISO/IEC 25010.

Principio de diseno: **los puntos se ganan, no se regalan**. Cada dimension
parte de cero y suma segun evidencia positiva y comprobada de calidad. El
modelo anterior partia de 100 y restaba penalizaciones, lo que premiaba la
ausencia de evidencia: un repositorio con un solo archivo y sin nada mas
sacaba 87/100 porque no habia nada que penalizar. Ese incentivo estaba
invertido y es lo que corrige este modulo.

Ademas, tal como pide el spec, los riesgos criticos bloquean las
puntuaciones altas: un hallazgo critico impone un techo a la nota global por
mucho que el resto del proyecto luzca bien.

Advertencia deliberada: esto es una aproximacion util al estandar, no una
certificacion. ISO/IEC 25010 define caracteristicas de calidad, no un
algoritmo de puntuacion; el reparto de pesos y los criterios de cada rubrica
son criterio nuestro y estan aqui a la vista para poder discutirlos.
"""

from app.analyzers.base import AnalyzerResult, FindingData

# Pesos de context/claude.md seccion 6, tabla "Para analisis de repositorio".
REPOSITORY_WEIGHTS: dict[str, float] = {
    "functional_suitability": 0.15,
    "reliability": 0.20,
    "security": 0.20,
    "maintainability": 0.20,
    "portability": 0.10,
    "project_activity": 0.15,
}

# Techos que impone la presencia de hallazgos graves. Sin esto, un proyecto
# con un secreto expuesto podria seguir sacando notable por lo demas.
CRITICAL_FINDING_SCORE_CAP = 40.0
HIGH_FINDING_SCORE_CAP = 70.0

# Cantidad de metricas recogidas a partir de la cual se considera que hay
# evidencia suficiente para confiar plenamente en el resultado.
EVIDENCE_FOR_FULL_CONFIDENCE = 30


def _award(condition: bool, points: float) -> float:
    return points if condition else 0.0


def _tiered(value: float, tiers: list[tuple[float, float]]) -> float:
    """Devuelve los puntos del tramo mas alto que el valor alcanza."""
    earned = 0.0
    for threshold, points in tiers:
        if value >= threshold:
            earned = points
    return earned


def _score_documentation(m: dict) -> float:
    """Adecuacion funcional (ISO 25010).

    Sub-caracteristicas cubiertas:
    - Pertinencia funcional: el proyecto explica que hace y como usarlo.
    - Completitud funcional: cuanto queda declaradamente sin terminar.
    """
    # -- Pertinencia funcional: documentacion utilizable (60 pts) ------------
    pertinencia = (
        _award(m.get("has_readme", False), 8)
        + _tiered(m.get("readme_length", 0), [(300, 5), (1000, 10), (3000, 14)])
        + _award(m.get("readme_has_install_instructions", False), 12)
        + _award(m.get("readme_has_usage_section", False), 10)
        + _award(m.get("readme_has_code_examples", False), 8)
        + _award(m.get("has_examples", False), 8)
    )
    # -- Gobernanza y evaluabilidad del proyecto (22 pts) --------------------
    gobernanza = (
        _award(m.get("has_license", False), 10)
        + _award(m.get("has_contributing", False), 4)
        + _award(m.get("has_changelog", False), 3)
        + _award(m.get("has_architecture_docs", False), 3)
        + _award(m.get("has_api_docs", False), 2)
    )
    # -- Completitud funcional: lo que falta por hacer (18 pts) --------------
    # Solo se acredita si de verdad se escaneo codigo: sin archivos mirados,
    # "no tiene funciones sin implementar" no es un merito, es desconocimiento.
    if m.get("completeness_files_scanned", 0) > 0:
        completitud = _award(m.get("unimplemented_stub_count", 0) == 0, 10) + _tiered(
            -m.get("pending_markers_per_file", 0.0), [(-2.0, 3), (-1.0, 6), (-0.3, 8)]
        )
    else:
        completitud = 0.0
    return pertinencia + gobernanza + completitud


def _score_reliability(m: dict) -> float:
    """Fiabilidad (ISO 25010).

    Sub-caracteristicas cubiertas:
    - Madurez: existencia y densidad de pruebas automaticas.
    - Tolerancia a fallos: el codigo contempla que las cosas fallen.
    - Recuperabilidad: deja rastro y sus cambios de estado son reversibles.
    """
    # Sin nada escaneado no se puede acreditar nada: premiar la AUSENCIA de
    # problemas cuando no se ha mirado ningun archivo es el mismo error que
    # este modulo corrige, colado por la puerta de atras.
    if m.get("code_files_scanned", 0) == 0 and m.get("test_file_count", 0) == 0:
        return 0.0

    # -- Madurez: pruebas automaticas (55 pts) -------------------------------
    if m.get("test_file_count", 0) == 0:
        madurez = 0.0
    else:
        madurez = (
            12.0
            + _tiered(m.get("test_ratio", 0.0), [(0.05, 4), (0.10, 9), (0.20, 14), (0.35, 18), (0.50, 21)])
            + _award(m.get("has_integration_tests", False), 12)
            + _award(m.get("has_e2e_tests", False), 10)
        )
    # -- Tolerancia a fallos (30 pts) ----------------------------------------
    tolerancia = (
        _tiered(m.get("error_handling_ratio", 0.0), [(0.10, 5), (0.25, 10), (0.40, 14)])
        + _award(m.get("silent_catch_count", 0) == 0, 8)
        + _award(m.get("bare_except_count", 0) == 0, 4)
        + _award(m.get("uses_timeouts", False), 2)
        + _award(m.get("uses_retries", False), 2)
    )
    # -- Recuperabilidad (15 pts) --------------------------------------------
    recuperabilidad = (
        _tiered(m.get("logging_ratio", 0.0), [(0.05, 4), (0.15, 8), (0.30, 10)])
        + _award(m.get("has_migrations", False), 5)
    )
    return madurez + tolerancia + recuperabilidad


def _score_maintainability(m: dict) -> float:
    """Mantenibilidad (ISO 25010).

    Sub-caracteristicas cubiertas:
    - Modularidad: tamano de archivos y funciones, estructura de carpetas.
    - Analizabilidad: comentarios, documentacion de funciones, anidamiento.
    - Modificabilidad: linter, tipos, ausencia de duplicacion.
    """
    if m.get("code_file_count", 0) == 0 and m.get("analyzed_code_files", 0) == 0:
        return 0.0

    # -- Modularidad (38 pts) -------------------------------------------------
    modularidad = (
        _tiered(-m.get("average_file_lines", 0.0), [(-400, 4), (-250, 8), (-150, 12)])
        + _tiered(-m.get("largest_file_lines", 0), [(-1500, 3), (-800, 7), (-400, 10)])
        + _tiered(-m.get("average_function_lines", 0.0), [(-60, 3), (-35, 6), (-20, 8)])
        + _award(m.get("top_level_directory_count", 0) >= 2, 5)
        + _award(m.get("project_shape", "unknown") != "unknown", 3)
    )
    # -- Analizabilidad (30 pts) ---------------------------------------------
    analizabilidad = (
        _tiered(m.get("comment_ratio", 0.0), [(0.02, 4), (0.05, 8), (0.10, 11)])
        + _tiered(m.get("function_documentation_ratio", 0.0), [(0.10, 3), (0.30, 6), (0.60, 9)])
        + _tiered(-m.get("max_nesting_depth", 0), [(-8, 3), (-6, 6), (-4, 10)])
    )
    # -- Modificabilidad (32 pts) --------------------------------------------
    modificabilidad = (
        _award(m.get("has_linter_config", False), 10)
        + _award(m.get("has_gitignore", False), 5)
        + _award(m.get("has_dependency_manifest", False), 5)
        + _tiered(m.get("type_annotation_ratio", 0.0), [(0.20, 3), (0.50, 6), (0.80, 8)])
        + _award(m.get("duplicated_file_count", 0) == 0, 4)
    )
    return modularidad + analizabilidad + modificabilidad


def _score_security(m: dict) -> float:
    """Seguridad (ISO 25010).

    Sub-caracteristicas cubiertas de forma estatica:
    - Confidencialidad: no hay credenciales expuestas.
    - Integridad: dependencias fijadas, sin ejecucion de codigo dinamico ni
      SQL construido por concatenacion.

    Nota: es una cobertura parcial hasta que Gitleaks y Semgrep entren en el
    sandbox; por eso el techo alcanzable aqui refleja solo lo comprobado.
    """
    if m.get("code_files_scanned", 0) == 0:
        return 0.0
    # -- Confidencialidad (55 pts) -------------------------------------------
    confidencialidad = (
        _award(not m.get("committed_secret_files"), 25)
        + _award(m.get("hardcoded_secret_file_count", 0) == 0, 20)
        + _award(m.get("gitignore_covers_env", False), 10)
    )
    # -- Integridad (45 pts) --------------------------------------------------
    integridad = (
        _award(m.get("dangerous_eval_file_count", 0) == 0, 18)
        + _award(m.get("sql_concatenation_file_count", 0) == 0, 17)
        + _award(m.get("has_dependency_lockfile", False), 10)
    )
    return confidencialidad + integridad


def _score_portability(m: dict) -> float:
    """Portabilidad (ISO 25010).

    Sub-caracteristicas cubiertas:
    - Instalabilidad: contenedor, dependencias fijadas.
    - Adaptabilidad: configuracion por entorno, sin rutas de una maquina.
    """
    # -- Instalabilidad (50 pts) ---------------------------------------------
    instalabilidad = (
        _award(m.get("has_container_definition", False), 25)
        + _award(m.get("has_dependency_lockfile", False), 25)
    )
    # -- Adaptabilidad (50 pts) ----------------------------------------------
    adaptabilidad = (
        _award(m.get("uses_environment_config", False), 20)
        + _award(m.get("has_env_example", False), 12)
        + _award(m.get("hardcoded_absolute_path_count", 0) == 0, 10)
        + _award(m.get("has_infrastructure_as_code", False), 8)
    )
    return instalabilidad + adaptabilidad


DIMENSION_RUBRICS = {
    "functional_suitability": _score_documentation,
    "reliability": _score_reliability,
    "maintainability": _score_maintainability,
    "security": _score_security,
    "portability": _score_portability,
}


def score_dimension(dimension: str, metrics: dict, findings: list[FindingData]) -> float:
    """Puntua una dimension de 0 a 100 sumando evidencia positiva.

    Una dimension sin rubrica todavia (seguridad, portabilidad, actividad)
    devuelve 0: no se puede acreditar calidad que aun no se mide, y darle 100
    por defecto es justamente el error que este modulo corrige.
    """
    rubric = DIMENSION_RUBRICS.get(dimension)
    if rubric is None:
        return 0.0
    return round(max(0.0, min(100.0, rubric(metrics))), 2)


def calculate_overall_score(
    dimension_scores: dict[str, float],
    findings: list[FindingData] | None = None,
) -> float:
    """Media ponderada, normalizada sobre los pesos de lo realmente medido.

    Si hay hallazgos graves se aplica un techo: el spec pide explicitamente
    que los riesgos criticos bloqueen las puntuaciones altas.
    """
    present = {d: s for d, s in dimension_scores.items() if d in REPOSITORY_WEIGHTS}
    if not present:
        return 0.0

    total_weight = sum(REPOSITORY_WEIGHTS[d] for d in present)
    weighted = sum(REPOSITORY_WEIGHTS[d] * score for d, score in present.items())
    score = weighted / total_weight

    severities = {f.severity for f in (findings or [])}
    if "critical" in severities:
        score = min(score, CRITICAL_FINDING_SCORE_CAP)
    elif "high" in severities:
        score = min(score, HIGH_FINDING_SCORE_CAP)

    return round(score, 2)


def calculate_confidence(results: list[AnalyzerResult]) -> float:
    """Confianza segun cuanta evidencia se logro recoger, de 0 a 100."""
    evidence = sum(len(result.metrics) for result in results)
    return round(min(100.0, 100.0 * evidence / EVIDENCE_FOR_FULL_CONFIDENCE), 2)
