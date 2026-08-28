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

# Pesos de context/claude.md seccion 6, tabla "Para analisis de URL".
URL_WEIGHTS: dict[str, float] = {
    "performance": 0.25,
    "security": 0.25,
    "usability": 0.20,
    "accessibility": 0.15,
    "compatibility": 0.15,
}


def _score_url_security(m: dict) -> float:
    """Seguridad de una app desplegada (ISO 25010: confidencialidad,
    integridad). Sin HTTPS la nota se hunde: todo lo demas depende de que el
    canal este cifrado."""
    if not m.get("uses_https", False):
        # Sin cifrado, ninguna cabecera compensa: el trafico va en claro.
        return 5.0
    return (
        30.0  # usa HTTPS
        + _award(m.get("has_hsts", False), 14)
        + _award((m.get("hsts_max_age") or 0) >= 15768000, 4)
        + _award(m.get("has_csp", False), 18)
        + _award(m.get("has_csp", False) and not m.get("csp_allows_unsafe_inline", True), 8)
        + _award(m.get("has_x_frame_options", False), 10)
        + _award(m.get("has_x_content_type_options", False), 6)
        + _award(m.get("has_referrer_policy", False), 4)
        + _award(m.get("has_permissions_policy", False), 3)
        + _award(not m.get("leaks_server_version", True) and not m.get("leaks_powered_by", True), 3)
    )


def _score_url_performance(m: dict) -> float:
    """Eficiencia de desempeno (ISO 25010: comportamiento temporal).

    Cobertura parcial declarada: mide el tiempo de respuesta del servidor, no
    el renderizado. Lighthouse llega mas adelante.
    """
    if "response_seconds" not in m:
        return 0.0
    return (
        _tiered(-m.get("response_seconds", 99), [(-2.0, 12), (-1.2, 24), (-0.6, 36), (-0.3, 45)])
        + _award(m.get("uses_compression", False), 25)
        + _award(m.get("has_cache_control", False), 15)
        + _tiered(-m.get("html_bytes", 10**9), [(-500_000, 4), (-250_000, 8), (-100_000, 10)])
        + _tiered(-m.get("redirect_count", 99), [(-3, 2), (-1, 5)])
    )


def _score_url_accessibility(m: dict) -> float:
    """Accesibilidad (ISO 25010). Comprobaciones estaticas del HTML."""
    if "image_count" not in m:
        return 0.0
    imagenes = m.get("image_count", 0)
    entradas = m.get("form_inputs", 0)
    sin_alt = m.get("images_without_alt", 0)
    sin_label = m.get("inputs_without_label", 0)
    return (
        _award(m.get("declares_language", False), 20)
        # Si no hay imagenes no se acredita ni se penaliza: no hay nada que juzgar.
        + (25.0 if imagenes == 0 else _tiered(-(sin_alt / imagenes), [(-0.5, 8), (-0.2, 17), (-0.001, 25)]))
        + (25.0 if entradas == 0 else _tiered(-(sin_label / entradas), [(-0.5, 8), (-0.2, 17), (-0.001, 25)]))
        + _award(m.get("has_h1", False), 15)
        + _award(m.get("uses_semantic_html", False), 15)
    )


def _score_url_compatibility(m: dict) -> float:
    """Compatibilidad (ISO 25010): que funcione fuera del escritorio."""
    if "has_viewport" not in m:
        return 0.0
    return (
        _award(m.get("has_viewport", False), 55)
        + _award(m.get("uses_semantic_html", False), 25)
        + _award(m.get("has_title", False), 20)
    )


def _score_url_usability(m: dict) -> float:
    """Usabilidad (ISO 25010: reconocibilidad, aprendizaje).

    Sin navegador solo se puede juzgar si la pagina se presenta de forma
    comprensible: titulo, descripcion, encabezado y estructura semantica.
    """
    if "has_title" not in m:
        return 0.0
    titulo_util = 10 <= m.get("title_length", 0) <= 70
    return (
        _award(m.get("has_title", False), 25)
        + _award(titulo_util, 15)
        + _award(m.get("has_meta_description", False), 20)
        + _award(m.get("has_h1", False), 20)
        + _award(m.get("uses_semantic_html", False), 20)
    )


URL_RUBRICS = {
    "security": _score_url_security,
    "performance": _score_url_performance,
    "accessibility": _score_url_accessibility,
    "compatibility": _score_url_compatibility,
    "usability": _score_url_usability,
}


def score_url_dimension(dimension: str, metrics: dict) -> float:
    rubrica = URL_RUBRICS.get(dimension)
    if rubrica is None:
        return 0.0
    return round(max(0.0, min(100.0, rubrica(metrics))), 2)


def calculate_url_overall_score(
    dimension_scores: dict[str, float],
    findings: list[FindingData] | None = None,
) -> float:
    present = {d: s for d, s in dimension_scores.items() if d in URL_WEIGHTS}
    if not present:
        return 0.0
    total_weight = sum(URL_WEIGHTS[d] for d in present)
    score = sum(URL_WEIGHTS[d] * s for d, s in present.items()) / total_weight

    severities = {f.severity for f in (findings or [])}
    if "critical" in severities:
        score = min(score, CRITICAL_FINDING_SCORE_CAP)
    elif "high" in severities:
        score = min(score, HIGH_FINDING_SCORE_CAP)
    return round(score, 2)


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
    # -- Confidencialidad (50 pts) -------------------------------------------
    confidencialidad = (
        _award(not m.get("committed_secret_files"), 14)
        + _award(m.get("hardcoded_secret_file_count", 0) == 0, 10)
        + _award(m.get("gitignore_covers_env", False), 6)
        # Gitleaks solo acredita si de verdad llego a ejecutarse: si fallo o
        # se agoto el tiempo, no se puede afirmar que no haya secretos.
        + _award(
            m.get("secret_scan_available", False) and m.get("leaked_secret_count", 1) == 0,
            20,
        )
    )
    # -- Integridad (50 pts) --------------------------------------------------
    integridad = (
        _award(m.get("dangerous_eval_file_count", 0) == 0, 12)
        + _award(m.get("sql_concatenation_file_count", 0) == 0, 12)
        + _award(m.get("has_dependency_lockfile", False), 8)
        + _award(
            m.get("vulnerability_scan_status") in {"ok", "sin dependencias declaradas"}
            and m.get("vulnerable_dependency_count", 1) == 0,
            18,
        )
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
    # -- Adaptabilidad (30 pts) ----------------------------------------------
    adaptabilidad = (
        _award(m.get("uses_environment_config", False), 12)
        + _award(m.get("has_env_example", False), 8)
        + _award(m.get("hardcoded_absolute_path_count", 0) == 0, 6)
        + _award(m.get("has_infrastructure_as_code", False), 4)
    )
    # -- Automatizacion: CI/CD (20 pts) --------------------------------------
    automatizacion = (
        _award(m.get("has_ci", False), 8)
        + _award(m.get("ci_runs_tests", False), 7)
        + _award(m.get("ci_runs_lint", False), 3)
        + _award(m.get("ci_has_deploy_stage", False), 2)
    )
    return instalabilidad + adaptabilidad + automatizacion


def _score_activity(m: dict) -> float:
    """Actividad del proyecto.

    OJO: esta dimension NO pertenece a ISO/IEC 25010. Es un anadido del spec
    de QalitiRadar, util para juzgar si un proyecto esta vivo, pero no forma
    parte de la norma. Ver docs/ISO_25010_MAPPING.md.
    """
    if m.get("activity_scan_status") != "ok":
        return 0.0
    if m.get("is_archived"):
        return 0.0

    dias = m.get("days_since_last_push")
    frescura = 0.0 if dias is None else _tiered(-dias, [(-365, 10), (-180, 25), (-90, 40), (-30, 55)])
    # Senales de que el proyecto se cuida y se presenta.
    cuidado = (
        _award(m.get("has_description", False), 12)
        + _award(m.get("has_topics", False), 8)
    )
    # Interes de terceros: no es calidad por si mismo, pero si senal de uso
    # real y de que hay ojos encima del codigo.
    interes = _tiered(m.get("stars", 0), [(1, 5), (10, 12), (100, 18)]) + _tiered(
        m.get("forks", 0), [(1, 3), (10, 7)]
    )
    return frescura + cuidado + interes


DIMENSION_RUBRICS = {
    "functional_suitability": _score_documentation,
    "reliability": _score_reliability,
    "maintainability": _score_maintainability,
    "security": _score_security,
    "portability": _score_portability,
    "project_activity": _score_activity,
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
