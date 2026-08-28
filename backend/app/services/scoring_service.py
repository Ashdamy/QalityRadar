"""Convierte hallazgos en puntuaciones ISO/IEC 25010.

La formula es la del spec: puntuacion = sum(peso_i * metrica_i) / sum(pesos).
Se normaliza sobre los pesos de las dimensiones realmente medidas, para no
penalizar a un proyecto por dimensiones que este analisis todavia no cubre
(en la Semana 2A solo se miden tres de las seis).

Advertencia deliberada: esto es una aproximacion util, no una certificacion
ISO. El estandar define caracteristicas de calidad, no un algoritmo de
puntuacion; el reparto de pesos y las penalizaciones son criterio nuestro.
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

# Cuanto resta cada hallazgo segun su gravedad. Un solo hallazgo critico deja
# la dimension en 60: suficiente para que se note, sin que un unico problema
# la hunda a cero.
SEVERITY_PENALTY: dict[str, float] = {
    "critical": 40.0,
    "high": 20.0,
    "medium": 10.0,
    "low": 4.0,
    "info": 0.0,
}

# Cantidad de metricas recogidas a partir de la cual se considera que hay
# evidencia suficiente para confiar plenamente en el resultado.
EVIDENCE_FOR_FULL_CONFIDENCE = 12


def score_dimension(dimension: str, metrics: dict, findings: list[FindingData]) -> float:
    """Puntua una dimension de 0 a 100 restando el peso de sus hallazgos."""
    penalty = sum(SEVERITY_PENALTY.get(finding.severity, 0.0) for finding in findings)
    return round(max(0.0, 100.0 - penalty), 2)


def calculate_overall_score(dimension_scores: dict[str, float]) -> float:
    """Media ponderada, normalizada sobre los pesos de lo realmente medido."""
    present = {d: s for d, s in dimension_scores.items() if d in REPOSITORY_WEIGHTS}
    if not present:
        return 0.0
    total_weight = sum(REPOSITORY_WEIGHTS[d] for d in present)
    weighted = sum(REPOSITORY_WEIGHTS[d] * score for d, score in present.items())
    return round(weighted / total_weight, 2)


def calculate_confidence(results: list[AnalyzerResult]) -> float:
    """Confianza segun cuanta evidencia se logro recoger, de 0 a 100."""
    evidence = sum(len(result.metrics) for result in results)
    return round(min(100.0, 100.0 * evidence / EVIDENCE_FOR_FULL_CONFIDENCE), 2)
