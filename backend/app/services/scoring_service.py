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
from app.analyzers.repository.code_quality import COBERTURA_MINIMA

# Pesos de context/claude.md seccion 6, tabla "Para analisis de repositorio",
# sin la actividad del proyecto (15%) y renormalizados para sumar 1.0: se
# conserva la proporcion entre las cinco caracteristicas ISO.
_PESOS_DEL_SPEC = {
    "functional_suitability": 0.15,
    "reliability": 0.20,
    "security": 0.20,
    "maintainability": 0.20,
    "portability": 0.10,
}
REPOSITORY_WEIGHTS: dict[str, float] = {
    dimension: peso / sum(_PESOS_DEL_SPEC.values()) for dimension, peso in _PESOS_DEL_SPEC.items()
}

# Se calculan y se ensenan, pero NO son ISO/IEC 25010 y no entran en la nota.
# La actividad puntua estrellas, forks y frescura: senales de que un proyecto
# esta vivo y tiene ojos encima, no de su calidad. Antes pesaba un 15%.
HEALTH_INDICATORS: tuple[str, ...] = ("project_activity",)


def dimension_weight(dimension: str) -> float:
    """Peso con el que se guarda una dimension: 0 si no entra en la nota."""
    return REPOSITORY_WEIGHTS.get(dimension, 0.0)

# Pesos de context/claude.md seccion 6, tabla "Para analisis de URL".
URL_WEIGHTS: dict[str, float] = {
    "performance": 0.25,
    "security": 0.25,
    "usability": 0.20,
    "accessibility": 0.15,
    "compatibility": 0.15,
}


def _score_url_security(m: dict) -> float:
    """Seguridad de una app desplegada (ISO 25010).

    Sub-caracteristicas: confidencialidad (cifrado y cookies), integridad
    (CSP, SRI, sin contenido mixto) y resistencia (aislamiento de origen).
    Sin HTTPS la nota se hunde: todo lo demas depende del canal cifrado.
    """
    if "uses_https" not in m:
        return {}
    if not m.get("uses_https", False):
        return {"Confidencialidad": 5.0}

    # -- Confidencialidad del canal (26 pts) ---------------------------------
    canal = (
        14.0
        + _award(m.get("has_hsts", False), 6)
        + _award((m.get("hsts_max_age") or 0) >= 15768000, 4)
        + _award(m.get("hsts_includes_subdomains", False), 2)
    )
    # -- Cookies (14 pts). Sin cookies no se acredita ni se penaliza. --------
    if m.get("cookie_count", 0) == 0:
        cookies = 14.0
    else:
        cookies = (
            _award(m.get("cookies_without_httponly", 1) == 0, 6)
            + _award(m.get("cookies_without_secure", 1) == 0, 4)
            + _award(m.get("cookies_without_samesite", 1) == 0, 4)
        )
    # -- Integridad del contenido (34 pts) -----------------------------------
    integridad = (
        _award(m.get("has_csp", False) and not m.get("csp_is_report_only", False), 12)
        + _award(m.get("has_csp", False) and not m.get("csp_allows_unsafe_inline", True), 5)
        + _award(m.get("has_csp", False) and not m.get("csp_allows_unsafe_eval", True), 4)
        + _tiered(len(m.get("csp_directives_present", [])), [(2, 2), (4, 4)])
        + _award(m.get("mixed_content_count", 1) == 0, 5)
        + _award(m.get("external_scripts_without_sri", 1) == 0, 4)
    )
    # -- Resistencia y exposicion (26 pts) -----------------------------------
    resistencia = (
        _award(m.get("has_x_frame_options", False) or m.get("has_frame_ancestors", False), 8)
        + _award(m.get("has_x_content_type_options", False), 4)
        + _award(m.get("has_referrer_policy", False), 3)
        + _award(m.get("has_permissions_policy", False), 3)
        + _award(m.get("has_coop", False) or m.get("has_corp", False), 2)
        + _award(not m.get("cors_allows_any_origin", False), 3)
        + _award(not m.get("form_posts_over_http", False), 1)
        + _award(
            not m.get("leaks_server_version", True) and not m.get("leaks_powered_by", True), 2
        )
    )
    return {"Confidencialidad": canal + cookies, "Integridad": integridad, "Resistencia": resistencia}


def _score_url_performance(m: dict) -> float:
    """Eficiencia de desempeno (ISO 25010: comportamiento temporal y uso de
    recursos).

    Cobertura parcial declarada: mide la respuesta del servidor y como esta
    construida la pagina, no el renderizado. Lighthouse llega mas adelante.
    """
    if "response_seconds" not in m:
        return {}

    # -- Comportamiento temporal (34 pts) ------------------------------------
    if _tiene_web_vitals(m):
        # Medido en un navegador real: lo que tarda en verse (LCP), lo que el
        # hilo principal queda bloqueado (TBT) y cuanto salta el contenido
        # al cargar (CLS). Umbrales de Google; ver navegador.UMBRALES.
        vitals = m["browser"]
        temporal = (
            _tiered(-vitals["lcp_ms"], [(-4000, 8), (-2500, 16)])
            + _tiered(-vitals["tbt_ms"], [(-600, 5), (-200, 10)])
            + _tiered(-vitals["cls"], [(-0.25, 4), (-0.1, 8)])
        )
    else:
        temporal = _tiered(
            -m.get("response_seconds", 99), [(-2.0, 8), (-1.2, 17), (-0.6, 27), (-0.3, 34)]
        )
    # -- Transferencia (28 pts) ----------------------------------------------
    transferencia = (
        _award(m.get("uses_compression", False), 14)
        + _award(m.get("has_cache_control", False), 8)
        + _award(m.get("has_etag", False), 3)
        + _tiered(-m.get("redirect_count", 99), [(-3, 1), (-1, 3)])
    )
    # -- Construccion de la pagina (38 pts) ----------------------------------
    imagenes = m.get("image_count", 0)
    sin_lazy = m.get("images_without_lazy_loading", 0)
    sin_dim = m.get("images_without_dimensions", 0)
    construccion = (
        _award(m.get("render_blocking_scripts", 1) == 0, 12)
        + _tiered(-m.get("render_blocking_styles", 99), [(-8, 2), (-4, 5), (-2, 7)])
        + _tiered(-m.get("third_party_origin_count", 99), [(-8, 2), (-4, 4), (-1, 6)])
        + _tiered(-m.get("html_bytes", 10**9), [(-500_000, 2), (-250_000, 4), (-100_000, 6)])
        + (4.0 if imagenes == 0 else _tiered(-(sin_lazy / imagenes), [(-0.7, 1), (-0.3, 4)]))
        + (3.0 if imagenes == 0 else _tiered(-(sin_dim / imagenes), [(-0.7, 1), (-0.3, 3)]))
    )
    return {
        "Comportamiento temporal": temporal,
        # Lo que pesa y como se sirve la pagina: los recursos que consume.
        "Utilización de recursos": transferencia + construccion,
    }


# Origen de una parte de la nota cuando puede venir del navegador real.
LIGHTHOUSE = "lighthouse"
AXE_CORE = "axe-core"
QALITIRADAR = "qalitiradar"


def _tiene_web_vitals(m: dict) -> bool:
    navegador = m.get("browser") or {}
    return all(k in navegador for k in ("lcp_ms", "tbt_ms", "cls"))


def _tiene_axe(m: dict) -> bool:
    return isinstance((m.get("browser") or {}).get("axe"), dict)


def _score_url_accessibility(m: dict) -> float:
    """Accesibilidad: la inclusividad de ISO 25010:2023.

    Con la medicion del navegador, sale de axe-core, que comprueba la pagina
    ya renderizada y con muchas mas reglas que el analisis estatico. Sin ella,
    comprobaciones estaticas del HTML.
    """
    if _tiene_axe(m):
        axe = m["browser"]["axe"]
        por_impacto = {i: 0 for i in ("critical", "serious", "moderate", "minor")}
        for v in axe["violations"]:
            por_impacto[v["impact"]] += 1
        # -- Sin violaciones graves (60 pts) ---------------------------------
        graves = _award(por_impacto["critical"] == 0, 35) + (
            25.0 if por_impacto["serious"] == 0 else _award(por_impacto["serious"] <= 2, 12)
        )
        # -- Reglas superadas (40 pts) ---------------------------------------
        reglas = axe["passes"] + len(axe["violations"])
        superadas = _tiered(axe["passes"] / reglas if reglas else 0.0, [(0.7, 10), (0.85, 20), (0.93, 30), (0.97, 40)])
        return {"Sin violaciones graves (axe-core)": graves, "Reglas superadas (axe-core)": superadas}

    if "image_count" not in m:
        return {}

    imagenes = m.get("image_count", 0)
    entradas = m.get("form_inputs", 0)
    iframes = m.get("iframe_count", 0)

    # -- Percepcion: se puede leer y entender el contenido (40 pts) ----------
    percepcion = (
        _award(m.get("declares_language", False), 10)
        + _award(not m.get("blocks_zoom", False), 12)
        + (
            10.0
            if imagenes == 0
            else _tiered(
                -(m.get("images_without_alt", 0) / imagenes),
                [(-0.5, 3), (-0.2, 7), (-0.001, 10)],
            )
        )
        + _award(m.get("tables_without_headers", 1) == 0, 4)
        + _award(not m.get("has_autoplay_media", False), 4)
    )
    # -- Operabilidad: se puede usar sin raton (28 pts) ----------------------
    operabilidad = (
        (
            12.0
            if entradas == 0
            else _tiered(
                -(m.get("inputs_without_label", 0) / entradas),
                [(-0.5, 4), (-0.2, 8), (-0.001, 12)],
            )
        )
        + _award(m.get("positive_tabindex_count", 1) == 0, 6)
        + (5.0 if iframes == 0 else _award(m.get("iframes_without_title", 1) == 0, 5))
        + _tiered(-m.get("generic_link_text_count", 99), [(-6, 2), (-2, 5)])
    )
    # -- Estructura: se puede navegar por encabezados y regiones (32 pts) ----
    estructura = (
        _award(m.get("has_h1", False), 9)
        + _award(m.get("h1_count", 0) == 1, 4)
        + _tiered(-m.get("heading_level_skips", 99), [(-3, 2), (-1, 5)])
        + _award(m.get("uses_semantic_html", False), 5)
        + _award(m.get("has_main_landmark", False), 5)
        + _award(m.get("duplicate_id_count", 1) == 0, 4)
    )
    return {
        "Perceptible (WCAG)": percepcion,
        "Operable (WCAG)": operabilidad,
        "Estructura navegable (WCAG)": estructura,
    }


def _score_url_compatibility(m: dict) -> float:
    """Compatibilidad (ISO 25010): interoperabilidad y adaptacion."""
    if "has_viewport" not in m:
        return {}

    imagenes = m.get("image_count", 0)
    responsivas = m.get("responsive_image_count", 0)
    # -- Adaptacion a dispositivos (46 pts)
    adaptacion = _award(m.get("has_viewport", False), 30) + (
        16.0
        if imagenes == 0 or m.get("uses_picture_element", False)
        else _tiered(responsivas / imagenes if imagenes else 0, [(0.1, 6), (0.5, 11), (0.9, 16)])
    )
    # -- Interoperabilidad: estandares bien declarados (40 pts)
    interoperabilidad = (
        _award(m.get("has_doctype", False), 16)
        + _award(m.get("declares_charset", False), 14)
        + _award(m.get("declares_content_language", False), 10)
    )
    # -- Ausencia de tecnologia retirada (14 pts)
    vigente = _award(not m.get("deprecated_tags"), 10) + _award(m.get("has_web_manifest", False), 4)
    return {
        "Interoperabilidad": interoperabilidad,
        "Adaptación a dispositivos": adaptacion,
        "Tecnología vigente": vigente,
    }


def _score_url_usability(m: dict) -> float:
    """Capacidad de interaccion (ISO 25010:2023, antes usabilidad): reconocibilidad y autodescriptividad.

    Sin navegador solo se juzga si la pagina se presenta e identifica de forma
    comprensible; la operabilidad real requiere interaccion.
    """
    if "has_title" not in m:
        return {}
    titulo_util = 10 <= m.get("title_length", 0) <= 70
    # -- Reconocibilidad: se sabe que es y de quien (58 pts)
    reconocibilidad = (
        _award(m.get("has_title", False), 18)
        + _award(titulo_util, 10)
        + _award(m.get("has_meta_description", False), 12)
        + _award(m.get("has_favicon", False), 8)
        + _award(m.get("has_open_graph", False), 6)
        + _award(m.get("has_canonical", False), 4)
    )
    # -- Estructura comprensible (42 pts)
    autodescriptividad = (
        _award(m.get("has_main_landmark", False), 14)
        + _award(m.get("uses_semantic_html", False), 12)
        + _award(m.get("has_nav", False), 10)
        + _award(m.get("has_theme_color", False), 6)
    )
    return {
        "Reconocibilidad de la adecuación": reconocibilidad,
        "Autodescriptividad": autodescriptividad,
    }


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
    return round(max(0.0, min(100.0, sum(rubrica(metrics).values()))), 2)


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
    return {
        "Pertinencia funcional": pertinencia,
        "Completitud funcional": completitud,
        "Gobernanza del proyecto": gobernanza,
    }


def _score_reliability(m: dict) -> float:
    """Fiabilidad (ISO 25010).

    Sub-caracteristicas cubiertas:
    - Ausencia de fallos (la madurez de 2011): existencia y densidad de pruebas.
    - Tolerancia a fallos: el codigo contempla que las cosas fallen.
    - Recuperabilidad: deja rastro y sus cambios de estado son reversibles.
    """
    # Sin nada escaneado no se puede acreditar nada: premiar la AUSENCIA de
    # problemas cuando no se ha mirado ningun archivo es el mismo error que
    # este modulo corrige, colado por la puerta de atras.
    if m.get("code_files_scanned", 0) == 0 and m.get("test_file_count", 0) == 0:
        return {}

    # -- Ausencia de fallos: pruebas automaticas (55 pts) --------------------
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
    return {
        "Ausencia de fallos": madurez,
        "Tolerancia a fallos": tolerancia,
        "Recuperabilidad": recuperabilidad,
    }


# Origen de cada parte de la nota de mantenibilidad, para que el usuario sepa
# de donde sale: medido por SonarCloud, medido por QalitiRadar (QALITIRADAR,
# definido arriba), estimado por QalitiRadar a partir de senales indirectas,
# o sin medir.
SONARCLOUD = "sonarcloud"
ESTIMADO = "estimado"
SIN_MEDIR = "sin_medir"

# Si SonarCloud aporta cobertura de pruebas, la capacidad de prueba pasa a
# valer 20 puntos y el resto se escala para que el maximo siga siendo 100.
_PUNTOS_CAPACIDAD_DE_PRUEBA = 20
_ESCALA_CON_COBERTURA = (100 - _PUNTOS_CAPACIDAD_DE_PRUEBA) / 100


def _partes_de_mantenibilidad(m: dict) -> list[tuple[str, float, float, str]]:
    """Mantenibilidad (ISO 25010), como (nombre, puntos, maximo, origen).

    Sub-caracteristicas cubiertas:
    - Modularidad: tamano de archivos y funciones, estructura de carpetas.
    - Analizabilidad: comentarios, documentacion de funciones, anidamiento;
      o la complejidad cognitiva de SonarCloud si se importo.
    - Modificabilidad: linter, tipos, ausencia de duplicacion; o la deuda
      tecnica y la duplicacion de SonarCloud si se importaron.
    - Capacidad de prueba: solo con la cobertura de SonarCloud.

    Las medidas de SonarCloud sustituyen a las estimadas porque son mejores:
    cubren todos los lenguajes del proyecto y no heuristicas. Formula en
    docs/ISO_25010_MAPPING.md.
    """
    sonar = m.get("sonar") or {}
    if m.get("code_file_count", 0) == 0 and m.get("analyzed_code_files", 0) == 0 and not sonar:
        return []

    # -- Modularidad (38 pts) -------------------------------------------------
    modularidad = (
        _tiered(-m.get("average_file_lines", 0.0), [(-400, 4), (-250, 8), (-150, 12)])
        + _tiered(-m.get("largest_file_lines", 0), [(-1500, 3), (-800, 7), (-400, 10)])
        + _tiered(-m.get("average_function_lines", 0.0), [(-60, 3), (-35, 6), (-20, 8)])
        + _award(m.get("top_level_directory_count", 0) >= 2, 5)
        + _award(m.get("project_shape", "unknown") != "unknown", 3)
    )
    partes = [("Modularidad", modularidad, 38.0, QALITIRADAR)]

    # -- Analizabilidad (30 pts) ---------------------------------------------
    if "cognitive_complexity" in sonar and sonar.get("ncloc"):
        # Por cada mil lineas: el total crece con el tamano del proyecto.
        densidad = 1000 * sonar["cognitive_complexity"] / sonar["ncloc"]
        analizabilidad = _tiered(-densidad, [(-250, 6), (-150, 14), (-100, 22), (-60, 30)])
        partes.append(("Analizabilidad", analizabilidad, 30.0, SONARCLOUD))
    else:
        analizabilidad = (
            _tiered(m.get("comment_ratio", 0.0), [(0.02, 4), (0.05, 8), (0.10, 11)])
            + _tiered(m.get("function_documentation_ratio", 0.0), [(0.10, 3), (0.30, 6), (0.60, 9)])
            + _tiered(-m.get("max_nesting_depth", 0), [(-8, 3), (-6, 6), (-4, 10)])
        )
        partes.append(("Analizabilidad", analizabilidad, 30.0, ESTIMADO))

    # -- Modificabilidad (32 pts) --------------------------------------------
    if "sqale_rating" in sonar and "duplicated_lines_density" in sonar:
        # sqale_rating: 1 = A ... 5 = E.
        modificabilidad = _tiered(
            -sonar["sqale_rating"], [(-4, 5), (-3, 10), (-2, 15), (-1, 20)]
        ) + _tiered(-sonar["duplicated_lines_density"], [(-10, 4), (-5, 8), (-3, 12)])
        partes.append(("Modificabilidad", modificabilidad, 32.0, SONARCLOUD))
    else:
        modificabilidad = (
            _award(m.get("has_linter_config", False), 10)
            + _award(m.get("has_gitignore", False), 5)
            + _award(m.get("has_dependency_manifest", False), 5)
            + _tiered(m.get("type_annotation_ratio", 0.0), [(0.20, 3), (0.50, 6), (0.80, 8)])
            + _award(m.get("duplicated_file_count", 0) == 0, 4)
        )
        partes.append(("Modificabilidad", modificabilidad, 32.0, ESTIMADO))

    # -- Capacidad de prueba (20 pts, solo con SonarCloud) -------------------
    if "coverage" in sonar:
        partes = [(n, p * _ESCALA_CON_COBERTURA, x * _ESCALA_CON_COBERTURA, o) for n, p, x, o in partes]
        cobertura = _tiered(sonar["coverage"], [(20, 4), (40, 8), (60, 14), (80, _PUNTOS_CAPACIDAD_DE_PRUEBA)])
        partes.append(("Capacidad de prueba", cobertura, float(_PUNTOS_CAPACIDAD_DE_PRUEBA), SONARCLOUD))
    return partes


def _score_maintainability(m: dict) -> dict:
    return {nombre: puntos for nombre, puntos, _, _ in _partes_de_mantenibilidad(m)}


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
        return {}
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
    return {"Confidencialidad": confidencialidad, "Integridad": integridad}


def _score_portability(m: dict) -> float:
    """Flexibilidad (ISO 25010:2023, antes portabilidad).

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
    return {
        "Instalabilidad": instalabilidad,
        "Adaptabilidad": adaptabilidad,
        "Automatización (CI/CD)": automatizacion,
    }


def _score_activity(m: dict) -> float:
    """Actividad del proyecto.

    OJO: esta dimension NO pertenece a ISO/IEC 25010. Es un anadido del spec
    de QalitiRadar, util para juzgar si un proyecto esta vivo, pero no forma
    parte de la norma. Ver docs/ISO_25010_MAPPING.md.
    """
    if m.get("activity_scan_status") != "ok":
        return {}
    if m.get("is_archived"):
        return {}

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
    return {"Frescura": frescura, "Cuidado del proyecto": cuidado, "Interés de terceros": interes}


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
    return round(max(0.0, min(100.0, sum(rubric(metrics).values()))), 2)


# --- Desglose por subcaracteristica (ISO/IEC 25010:2023) ---------------------
#
# Cada rubrica devuelve sus puntos por grupo; aqui se dice como se llama cada
# grupo, cuanto vale como maximo y si es de verdad una subcaracteristica de la
# norma. Algunos grupos puntuan cosas utiles que la norma no recoge (la
# gobernanza del proyecto, el CI/CD): suman, pero se marcan `iso: False` para
# no hacerlos pasar por lo que no son.
#
# `sin_medir` son las subcaracteristicas que la norma define y aqui no se
# comprueban. Se listan para que se vea el hueco, nunca con un 0: un 0 diria
# "se miro y esta mal", y la verdad es "no se miro".

# (nombre, maximo, es subcaracteristica ISO)
_Grupo = tuple[str, float, bool]

_DESGLOSE_REPOSITORIO: dict[str, tuple[list[_Grupo], list[str]]] = {
    "functional_suitability": (
        [("Pertinencia funcional", 60, True), ("Completitud funcional", 18, True),
         ("Gobernanza del proyecto", 22, False)],
        ["Corrección funcional"],
    ),
    "reliability": (
        # "Ausencia de fallos" es la madurez de 2011, renombrada en 2023.
        [("Ausencia de fallos", 55, True), ("Tolerancia a fallos", 30, True),
         ("Recuperabilidad", 15, True)],
        ["Disponibilidad"],
    ),
    # Mantenibilidad no esta aqui: sus maximos cambian si hay datos de
    # SonarCloud, ver _desglose_de_mantenibilidad.
    "security": (
        [("Confidencialidad", 50, True), ("Integridad", 50, True)],
        ["No repudio", "Responsabilidad", "Autenticidad", "Resistencia"],
    ),
    "portability": (
        [("Instalabilidad", 50, True), ("Adaptabilidad", 30, True),
         ("Automatización (CI/CD)", 20, False)],
        ["Escalabilidad", "Reemplazabilidad"],
    ),
    "project_activity": (
        [("Frescura", 55, False), ("Cuidado del proyecto", 20, False),
         ("Interés de terceros", 25, False)],
        [],
    ),
}

_DESGLOSE_URL: dict[str, tuple[list[_Grupo], list[str]]] = {
    "security": (
        [("Confidencialidad", 40, True), ("Integridad", 34, True), ("Resistencia", 26, True)],
        ["No repudio", "Responsabilidad", "Autenticidad"],
    ),
    "performance": (
        [("Comportamiento temporal", 34, True), ("Utilización de recursos", 66, True)],
        ["Capacidad"],
    ),
    # Toda la dimension es la inclusividad de 2023; sus partes siguen los
    # principios de WCAG, que es con lo que se comprueba.
    "accessibility": (
        [("Perceptible (WCAG)", 40, False), ("Operable (WCAG)", 28, False),
         ("Estructura navegable (WCAG)", 32, False)],
        [],
    ),
    "compatibility": (
        [("Interoperabilidad", 40, True), ("Adaptación a dispositivos", 46, False),
         ("Tecnología vigente", 14, False)],
        ["Coexistencia"],
    ),
    "usability": (
        [("Reconocibilidad de la adecuación", 58, True), ("Autodescriptividad", 42, True)],
        ["Aprendizaje", "Operabilidad", "Protección frente a errores del usuario",
         "Compromiso del usuario", "Asistencia al usuario"],
    ),
}


def subcharacteristics(dimension: str, metrics: dict, *, url: bool = False) -> list[dict]:
    """Puntos de una dimension repartidos por subcaracteristica.

    Las medidas suman exactamente la nota de la dimension. Las que la norma
    define y aqui no se miden van al final con `measured: False` y sin puntos.
    """
    rubricas, desgloses = (URL_RUBRICS, _DESGLOSE_URL) if url else (DIMENSION_RUBRICS, _DESGLOSE_REPOSITORIO)
    if not url and dimension == "maintainability":
        return _desglose_de_mantenibilidad(metrics)
    if dimension not in rubricas:
        return []
    puntos = rubricas[dimension](metrics)
    grupos, sin_medir = desgloses[dimension]
    origenes: dict[str, str] = {}
    if url and dimension == "accessibility" and _tiene_axe(metrics):
        grupos = [("Sin violaciones graves (axe-core)", 60, False), ("Reglas superadas (axe-core)", 40, False)]
        origenes = {nombre: AXE_CORE for nombre, _, _ in grupos}
    elif url and dimension in ("performance", "accessibility"):
        # Se marca el origen solo donde puede venir del navegador, para que
        # se vea que parte es medida real y que parte analisis estatico.
        origenes = {nombre: QALITIRADAR for nombre, _, _ in grupos}
        if dimension == "performance" and _tiene_web_vitals(metrics):
            origenes["Comportamiento temporal"] = LIGHTHOUSE
    return [
        {"name": nombre, "earned": round(puntos.get(nombre, 0.0), 2), "max": maximo,
         "measured": True, "iso": iso, **({"origin": origenes[nombre]} if nombre in origenes else {})}
        for nombre, maximo, iso in grupos
    ] + [
        {"name": nombre, "earned": None, "max": None, "measured": False, "iso": True}
        for nombre in sin_medir
    ]


def _desglose_de_mantenibilidad(metrics: dict) -> list[dict]:
    """Como `subcharacteristics`, con el origen de cada parte (`origin`)."""
    partes = _partes_de_mantenibilidad(metrics)
    if not partes:
        # Sin codigo no hay puntos, pero se ensena la estructura igual.
        partes = [("Modularidad", 0.0, 38.0, QALITIRADAR), ("Analizabilidad", 0.0, 30.0, ESTIMADO),
                  ("Modificabilidad", 0.0, 32.0, ESTIMADO)]
    medidas = {nombre for nombre, *_ in partes}
    return [
        {"name": nombre, "earned": round(puntos, 2), "max": round(maximo, 2),
         "measured": True, "iso": True, "origin": origen}
        for nombre, puntos, maximo, origen in partes
    ] + [
        {"name": nombre, "earned": None, "max": None, "measured": False, "iso": True, "origin": SIN_MEDIR}
        for nombre in ("Reusabilidad", "Capacidad de prueba")
        if nombre not in medidas
    ]


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


# Metricas que describen cuanto se pudo mirar, no como es el codigo: no
# cuentan como evidencia.
_NO_SON_EVIDENCIA = {"language_coverage"}


def calculate_confidence(results: list[AnalyzerResult]) -> float:
    """Confianza segun cuanta evidencia se logro recoger, de 0 a 100.

    Si la calidad del codigo solo pudo analizarse en parte del proyecto (un
    repositorio en Java, por ejemplo), se rebaja en la parte de la nota que
    descansa sobre codigo sin analizar: el peso de mantenibilidad por la
    proporcion que quedo fuera.
    """
    evidence = sum(len(set(result.metrics) - _NO_SON_EVIDENCIA) for result in results)
    confianza = min(100.0, 100.0 * evidence / EVIDENCE_FOR_FULL_CONFIDENCE)

    coberturas = [
        r.metrics["language_coverage"]["ratio"]
        for r in results
        if isinstance(r.metrics.get("language_coverage"), dict)
    ]
    if coberturas and coberturas[0] < COBERTURA_MINIMA:
        confianza *= 1 - REPOSITORY_WEIGHTS["maintainability"] * (1 - coberturas[0])
    return round(confianza, 2)
