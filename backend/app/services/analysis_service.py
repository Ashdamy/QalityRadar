"""Orquesta el ciclo de vida completo de un analisis de repositorio.

El codigo del usuario nunca se ejecuta: se clona de forma superficial, se leen
sus archivos, y el clon se borra siempre al terminar. En base de datos solo
quedan metricas y hallazgos, nunca codigo fuente.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.analyzers.base import AnalyzerResult, FindingData
from app.analyzers.repository.activity import ActivityAnalyzer
from app.analyzers.repository.cicd import CicdAnalyzer
from app.analyzers.repository.code_quality import CodeQualityAnalyzer
from app.analyzers.repository.dependencies import DependenciesAnalyzer
from app.analyzers.repository.completeness import CompletenessAnalyzer
from app.analyzers.repository.documentation import DocumentationAnalyzer
from app.analyzers.repository.error_handling import ErrorHandlingAnalyzer
from app.analyzers.repository.portability import PortabilityAnalyzer
from app.analyzers.repository.secrets_scan import SecretsScanAnalyzer
from app.analyzers.repository.security_basics import SecurityBasicsAnalyzer
from app.analyzers.repository.structure import StructureAnalyzer
from app.analyzers.repository.tests_analyzer import TestsAnalyzer
from app.core.database import SessionLocal
from app.models.analysis import Analysis, Dimension, Finding
from app.models.repository import Repository
from app.services.comparison_service import compare_analyses, find_previous_analysis
from app.services.repo_service import clone_repository, read_head_commit
from app.services.scoring_service import (
    REPOSITORY_WEIGHTS,
    calculate_confidence,
    calculate_overall_score,
    score_dimension,
)

ANALYZERS = (
    StructureAnalyzer(),        # mantenibilidad: estructura
    CodeQualityAnalyzer(),      # mantenibilidad: legibilidad y modularidad
    DocumentationAnalyzer(),    # adecuacion funcional: documentacion
    CompletenessAnalyzer(),     # adecuacion funcional: completitud
    TestsAnalyzer(),            # fiabilidad: cobertura de pruebas
    ErrorHandlingAnalyzer(),    # fiabilidad: tolerancia a fallos
    SecurityBasicsAnalyzer(),   # seguridad: confidencialidad e integridad
    PortabilityAnalyzer(),      # portabilidad: adaptabilidad e instalabilidad
    CicdAnalyzer(),             # portabilidad: automatizacion de integracion
    SecretsScanAnalyzer(),      # seguridad: Gitleaks dentro del sandbox
    DependenciesAnalyzer(),     # seguridad: vulnerabilidades conocidas
)


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
                # La actividad no esta en un clon superficial: se consulta a
                # GitHub, y por eso este analizador necesita el nombre del
                # repositorio y se construye aqui.
                results.append(ActivityAnalyzer(repository.full_name).analyze())
        except Exception as exc:  # noqa: BLE001 - se guarda un mensaje seguro
            _mark_failed(db, analysis, _safe_error_message(exc))
            return

        analysis.status = "scoring"
        db.commit()

        # Varios analizadores pueden alimentar la misma dimension (por ejemplo
        # estructura y calidad de codigo aportan ambos a mantenibilidad), asi
        # que primero se fusionan sus metricas y hallazgos y luego se puntua
        # la dimension una sola vez: `dimensions` es unica por analisis y
        # nombre.
        merged = _merge_by_dimension(results)

        dimension_scores: dict[str, float] = {}
        for dimension, (metrics, findings) in merged.items():
            score = score_dimension(dimension, metrics, findings)
            dimension_scores[dimension] = score
            db.add(
                Dimension(
                    id=uuid.uuid4(),
                    analysis_id=analysis.id,
                    name=dimension,
                    score=score,
                    weight=REPOSITORY_WEIGHTS[dimension],
                    raw_metrics=metrics,
                )
            )
            for finding in findings:
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

        all_findings = [finding for _, findings in merged.values() for finding in findings]
        analysis.overall_score = calculate_overall_score(dimension_scores, all_findings)
        analysis.confidence_level = calculate_confidence(results)
        analysis.commit_hash = commit_hash
        analysis.commit_message = commit_message
        analysis.branch = repository.default_branch
        analysis.raw_data = {dim: metrics for dim, (metrics, _) in merged.items()}
        analysis.status = "completed"
        analysis.completed_at = datetime.now(timezone.utc)

        repository.last_analyzed_at = analysis.completed_at
        db.commit()

        # Regla de negocio del spec: cada analisis nuevo se compara
        # automaticamente con el anterior. Si es el primero no hay con que
        # comparar, y un fallo aqui no debe invalidar un analisis ya completado.
        previous = find_previous_analysis(db, analysis)
        if previous is not None:
            try:
                compare_analyses(db, previous, analysis)
            except Exception:  # noqa: BLE001
                db.rollback()
    finally:
        db.close()


def _merge_by_dimension(
    results: list[AnalyzerResult],
) -> dict[str, tuple[dict, list[FindingData]]]:
    """Agrupa los resultados de varios analizadores por dimension."""
    merged: dict[str, tuple[dict, list[FindingData]]] = {}
    for result in results:
        metrics, findings = merged.setdefault(result.dimension, ({}, []))
        metrics.update(result.metrics)
        findings.extend(result.findings)
    return merged


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
