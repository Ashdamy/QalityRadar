"""Comparacion entre dos analisis del mismo repositorio.

Regla de negocio del spec: cada analisis nuevo se compara automaticamente con
el anterior. Si es el primero, no hay comparacion.

La comparacion no se limita a restar puntuaciones: distingue si una dimension
cambio porque el proyecto mejoro o porque ahora se mide algo que antes no se
media, y detecta que hallazgos concretos se resolvieron y cuales aparecieron.
"""

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.analysis import (
    Analysis,
    AnalysisComparison,
    Dimension,
    Finding,
    Improvement,
    Regression,
)

# Por debajo de esto el cambio es ruido, no una mejora ni una regresion.
SIGNIFICANT_DELTA = 1.0

DIMENSION_LABELS = {
    "functional_suitability": "Adecuacion funcional",
    "reliability": "Fiabilidad",
    "security": "Seguridad",
    "maintainability": "Mantenibilidad",
    "portability": "Portabilidad",
    "project_activity": "Actividad del proyecto",
}

SEVERITY_RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}


@dataclass
class ComparisonOutcome:
    comparison_id: uuid.UUID
    score_delta: float
    improvements: int
    regressions: int


def find_previous_analysis(db: Session, analysis: Analysis) -> Analysis | None:
    """El analisis completado inmediatamente anterior del mismo objetivo."""
    if analysis.repository_id is None:
        return None
    return db.scalars(
        select(Analysis)
        .where(
            Analysis.repository_id == analysis.repository_id,
            Analysis.id != analysis.id,
            Analysis.status == "completed",
            Analysis.created_at < analysis.created_at,
        )
        .order_by(Analysis.created_at.desc())
        .limit(1)
    ).first()


def compare_analyses(db: Session, previous: Analysis, current: Analysis) -> ComparisonOutcome:
    """Crea la comparacion entre dos analisis y persiste sus diferencias."""

    existing = db.scalar(
        select(AnalysisComparison).where(
            AnalysisComparison.analysis_1_id == previous.id,
            AnalysisComparison.analysis_2_id == current.id,
        )
    )
    if existing is not None:
        return ComparisonOutcome(
            comparison_id=existing.id,
            score_delta=float(existing.score_delta),
            improvements=existing.improvements_count,
            regressions=existing.regressions_count,
        )

    previous_dims = _dimensions_by_name(db, previous.id)
    current_dims = _dimensions_by_name(db, current.id)

    mejoras: list[tuple[str, float, float, float, str]] = []
    regresiones: list[tuple[str, float, float, float, str, str]] = []

    for name, current_score in current_dims.items():
        etiqueta = DIMENSION_LABELS.get(name, name)
        if name not in previous_dims:
            # Dimension nueva: antes no se medía. No es una mejora del
            # proyecto, asi que no cuenta como tal.
            continue
        previous_score = previous_dims[name]
        delta = round(current_score - previous_score, 2)
        if delta >= SIGNIFICANT_DELTA:
            mejoras.append(
                (
                    name,
                    previous_score,
                    current_score,
                    delta,
                    f"{etiqueta} subio de {previous_score:.0f} a {current_score:.0f} (+{delta:.0f}).",
                )
            )
        elif delta <= -SIGNIFICANT_DELTA:
            regresiones.append(
                (
                    name,
                    previous_score,
                    current_score,
                    delta,
                    f"{etiqueta} bajo de {previous_score:.0f} a {current_score:.0f} ({delta:.0f}).",
                    _severity_for_drop(abs(delta)),
                )
            )

    resueltos, nuevos = _diff_findings(db, previous.id, current.id)

    score_delta = round(
        float(current.overall_score or 0) - float(previous.overall_score or 0), 2
    )
    comparison = AnalysisComparison(
        id=uuid.uuid4(),
        analysis_1_id=previous.id,
        analysis_2_id=current.id,
        score_delta=score_delta,
        improvements_count=len(mejoras) + len(resueltos),
        regressions_count=len(regresiones) + len(nuevos),
    )
    db.add(comparison)
    db.flush()

    for name, prev, curr, delta, descripcion in mejoras:
        db.add(
            Improvement(
                id=uuid.uuid4(),
                comparison_id=comparison.id,
                dimension=name,
                previous_score=prev,
                current_score=curr,
                delta=delta,
                description=descripcion,
                evidence={"tipo": "dimension"},
            )
        )
    for finding in resueltos:
        db.add(
            Improvement(
                id=uuid.uuid4(),
                comparison_id=comparison.id,
                dimension=_dimension_for_finding_type(finding.type),
                previous_score=None,
                current_score=None,
                delta=0.0,
                description=f"Resuelto: {finding.title}",
                evidence={"tipo": "hallazgo", "severidad": finding.severity},
            )
        )

    for name, prev, curr, delta, descripcion, severidad in regresiones:
        db.add(
            Regression(
                id=uuid.uuid4(),
                comparison_id=comparison.id,
                dimension=name,
                previous_score=prev,
                current_score=curr,
                delta=delta,
                description=descripcion,
                evidence={"tipo": "dimension"},
                severity=severidad,
            )
        )
    for finding in nuevos:
        db.add(
            Regression(
                id=uuid.uuid4(),
                comparison_id=comparison.id,
                dimension=_dimension_for_finding_type(finding.type),
                previous_score=None,
                current_score=None,
                delta=0.0,
                description=f"Nuevo problema: {finding.title}",
                evidence={"tipo": "hallazgo"},
                severity=finding.severity,
            )
        )

    db.commit()
    return ComparisonOutcome(
        comparison_id=comparison.id,
        score_delta=score_delta,
        improvements=comparison.improvements_count,
        regressions=comparison.regressions_count,
    )


def _dimensions_by_name(db: Session, analysis_id: uuid.UUID) -> dict[str, float]:
    return {
        d.name: float(d.score)
        for d in db.scalars(select(Dimension).where(Dimension.analysis_id == analysis_id)).all()
    }


def _diff_findings(
    db: Session, previous_id: uuid.UUID, current_id: uuid.UUID
) -> tuple[list[Finding], list[Finding]]:
    """Hallazgos que desaparecieron y hallazgos que aparecieron.

    Se identifican por titulo y ruta, no por id: cada analisis crea filas
    nuevas, asi que comparar ids no diria nada.
    """
    anteriores = db.scalars(select(Finding).where(Finding.analysis_id == previous_id)).all()
    actuales = db.scalars(select(Finding).where(Finding.analysis_id == current_id)).all()

    def clave(f: Finding) -> tuple[str, str]:
        return (f.title, f.file_path or "")

    claves_anteriores = {clave(f) for f in anteriores}
    claves_actuales = {clave(f) for f in actuales}

    resueltos = [f for f in anteriores if clave(f) not in claves_actuales]
    nuevos = [f for f in actuales if clave(f) not in claves_anteriores]

    # Lo mas grave primero, para que el resumen destaque lo que importa.
    resueltos.sort(key=lambda f: SEVERITY_RANK.get(f.severity, 9))
    nuevos.sort(key=lambda f: SEVERITY_RANK.get(f.severity, 9))
    return resueltos, nuevos


def _severity_for_drop(magnitude: float) -> str:
    if magnitude >= 25:
        return "critical"
    if magnitude >= 12:
        return "high"
    if magnitude >= 5:
        return "medium"
    return "low"


def _dimension_for_finding_type(finding_type: str) -> str:
    return {
        "security": "security",
        "dependency": "security",
        "test_coverage": "reliability",
        "documentation": "functional_suitability",
        "structure": "maintainability",
        "cicd": "portability",
        "activity": "project_activity",
    }.get(finding_type, "maintainability")
