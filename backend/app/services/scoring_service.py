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
    """Adecuacion funcional: puede alguien entender y usar este proyecto."""
    return (
        _award(m.get("has_readme", False), 12)
        + _tiered(
            m.get("readme_length", 0),
            [(300, 8), (1000, 16), (3000, 22)],
        )
        + _award(m.get("readme_has_install_instructions", False), 16)
        + _award(m.get("readme_has_usage_section", False), 12)
        + _award(m.get("readme_has_code_examples", False), 10)
        + _award(m.get("has_license", False), 14)
        + _award(m.get("has_contributing", False), 6)
        + _award(m.get("has_changelog", False), 4)
        + _award(m.get("has_architecture_docs", False), 4)
    )


def _score_reliability(m: dict) -> float:
    """Fiabilidad: hay red de seguridad automatica contra regresiones."""
    if m.get("test_file_count", 0) == 0:
        return 0.0
    return (
        20.0  # existir tests ya vale, pero solo una quinta parte
        + _tiered(
            m.get("test_ratio", 0.0),
            [(0.05, 8), (0.10, 16), (0.20, 26), (0.35, 34), (0.50, 40)],
        )
        + _award(m.get("has_integration_tests", False), 22)
        + _award(m.get("has_e2e_tests", False), 18)
    )


def _score_maintainability(m: dict) -> float:
    """Mantenibilidad: se puede entender, revisar y cambiar sin miedo."""
    code_files = m.get("code_file_count", 0)
    if code_files == 0:
        return 0.0

    average_lines = m.get("average_file_lines", 0.0)
    largest = m.get("largest_file_lines", 0)
    return (
        _award(m.get("has_gitignore", False), 14)
        + _award(m.get("has_dependency_manifest", False), 14)
        + _award(m.get("has_linter_config", False), 18)
        # Codigo descompuesto: media de lineas por archivo.
        + _tiered(-average_lines, [(-400, 6), (-250, 14), (-150, 22)])
        # Ausencia de archivos monstruo.
        + _tiered(-largest, [(-1500, 6), (-800, 14), (-400, 18)])
        # Estructura real de carpetas, no un volcado plano de archivos.
        + _award(m.get("top_level_directory_count", 0) >= 2, 8)
        + _award(m.get("project_shape", "unknown") != "unknown", 6)
    )


DIMENSION_RUBRICS = {
    "functional_suitability": _score_documentation,
    "reliability": _score_reliability,
    "maintainability": _score_maintainability,
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
