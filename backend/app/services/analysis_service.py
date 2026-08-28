"""Orquesta el ciclo de vida completo de un analisis de repositorio.

El codigo del usuario nunca se ejecuta: se clona de forma superficial, se leen
sus archivos, y el clon se borra siempre al terminar. En base de datos solo
quedan metricas y hallazgos, nunca codigo fuente.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.analyzers.repository.documentation import DocumentationAnalyzer
from app.analyzers.repository.structure import StructureAnalyzer
from app.analyzers.repository.tests_analyzer import TestsAnalyzer
from app.core.database import SessionLocal
from app.models.analysis import Analysis, Dimension, Finding
from app.models.repository import Repository
from app.services.repo_service import clone_repository, read_head_commit
from app.services.scoring_service import (
    REPOSITORY_WEIGHTS,
    calculate_confidence,
    calculate_overall_score,
    score_dimension,
)

ANALYZERS = (StructureAnalyzer(), DocumentationAnalyzer(), TestsAnalyzer())


def run_repository_analysis(analysis_id: str) -> None:
    db = SessionLocal()
    try:
        analysis = db.get(Analysis, uuid.UUID(analysis_id))
        if analysis is None:
            return
        repository = db.get(Repository, analysis.repository_id)
        if repository is None:
            _mark_failed(db, analysis, "el repositorio ya no existe")
            return

        analysis.status = "cloning"
        analysis.started_at = datetime.now(timezone.utc)
        db.commit()

        clone_url = f"https://github.com/{repository.full_name}"
        try:
            with clone_repository(clone_url, repository.default_branch) as repo_dir:
                analysis.status = "running"
                db.commit()

                commit_hash, commit_message = read_head_commit(repo_dir)
                results = [analyzer.analyze(repo_dir) for analyzer in ANALYZERS]
        except Exception as exc:  # noqa: BLE001 - se guarda un mensaje seguro
            _mark_failed(db, analysis, _safe_error_message(exc))
            return

        analysis.status = "scoring"
        db.commit()

        dimension_scores: dict[str, float] = {}
        for result in results:
            score = score_dimension(result.dimension, result.metrics, result.findings)
            dimension_scores[result.dimension] = score
            db.add(
                Dimension(
                    id=uuid.uuid4(),
                    analysis_id=analysis.id,
                    name=result.dimension,
                    score=score,
                    weight=REPOSITORY_WEIGHTS[result.dimension],
                    raw_metrics=result.metrics,
                )
            )
            for finding in result.findings:
                db.add(
                    Finding(
                        id=uuid.uuid4(),
                        analysis_id=analysis.id,
                        type=finding.type,
                        severity=finding.severity,
                        title=finding.title,
                        description=finding.description,
                        file_path=finding.file_path,
                        recommendation=finding.recommendation,
                    )
                )

        analysis.overall_score = calculate_overall_score(dimension_scores)
        analysis.confidence_level = calculate_confidence(results)
        analysis.commit_hash = commit_hash
        analysis.commit_message = commit_message
        analysis.branch = repository.default_branch
        analysis.raw_data = {result.dimension: result.metrics for result in results}
        analysis.status = "completed"
        analysis.completed_at = datetime.now(timezone.utc)

        repository.last_analyzed_at = analysis.completed_at
        db.commit()
    finally:
        db.close()


def _mark_failed(db: Session, analysis: Analysis, message: str) -> None:
    analysis.status = "failed"
    analysis.error_message = message
    analysis.completed_at = datetime.now(timezone.utc)
    db.commit()


def _safe_error_message(exc: Exception) -> str:
    """Mensaje apto para mostrar al usuario: sin rutas internas ni tokens."""
    text = str(exc)
    if "/tmp/" in text or "\\Temp\\" in text or "qaliti-clone-" in text:
        return "el analisis fallo al preparar el repositorio"
    return text[:300] or "el analisis fallo por un error inesperado"
