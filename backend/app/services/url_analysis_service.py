"""Orquesta el analisis de una aplicacion desplegada (Modo 2 del producto).

A diferencia del analisis de repositorio, aqui no se clona ni se ejecuta
nada: se descarga la pagina publica una sola vez y todos los analizadores
trabajan sobre esa misma respuesta. Descargarla varias veces seria molesto
para el servidor ajeno y daria medidas inconsistentes entre analizadores.

La descarga pasa por `fetch_public_page`, que valida cada salto de
redireccion contra SSRF.
"""

import uuid
from datetime import datetime, timezone

import httpx
from sqlalchemy.orm import Session

from app.analyzers.url.page_quality import (
    AccessibilityAnalyzer,
    PerformanceAnalyzer,
    SeoCompatibilityAnalyzer,
)
from app.analyzers.url.security_headers import SecurityHeadersAnalyzer
from app.core.database import SessionLocal
from app.models.analysis import Analysis, Dimension, Finding
from app.models.deployed_app import DeployedApp
from app.services.scoring_service import (
    URL_WEIGHTS,
    calculate_confidence,
    calculate_url_overall_score,
    score_url_dimension,
)
from app.utils.safe_http import fetch_public_page
from app.utils.url_validation import UnsafeUrlError

ANALYZERS = (
    SecurityHeadersAnalyzer(),
    PerformanceAnalyzer(),
    AccessibilityAnalyzer(),
    SeoCompatibilityAnalyzer(),
)


def run_url_analysis(analysis_id: str) -> None:
    db = SessionLocal()
    try:
        analysis = db.get(Analysis, uuid.UUID(analysis_id))
        if analysis is None:
            return
        app_row = db.get(DeployedApp, analysis.app_id) if analysis.app_id else None
        if app_row is None:
            _mark_failed(db, analysis, "la aplicacion ya no existe")
            return

        analysis.status = "running"
        analysis.started_at = datetime.now(timezone.utc)
        db.commit()

        try:
            fetched = fetch_public_page(app_row.url)
        except UnsafeUrlError as exc:
            # El motivo aqui SI se muestra: explica por que rechazamos la URL.
            _mark_failed(db, analysis, str(exc))
            return
        except httpx.RequestError:
            _mark_failed(db, analysis, "no se pudo conectar con la direccion indicada")
            return

        if fetched.status_code >= 400:
            _mark_failed(
                db,
                analysis,
                f"la direccion respondio con el codigo {fetched.status_code}",
            )
            return

        results = [analyzer.analyze(fetched) for analyzer in ANALYZERS]

        analysis.status = "scoring"
        db.commit()

        # La usabilidad se puntua con las mismas senales que recoge el
        # analizador de SEO (titulo, descripcion, encabezado, semantica), asi
        # que se alimenta de ahi en vez de descargar la pagina otra vez.
        metricas_por_dimension = {r.dimension: r.metrics for r in results}
        seo_y_accesibilidad = {
            **metricas_por_dimension.get("compatibility", {}),
            **metricas_por_dimension.get("accessibility", {}),
        }
        metricas_por_dimension["usability"] = seo_y_accesibilidad

        todos_los_hallazgos = [f for r in results for f in r.findings]

        dimension_scores: dict[str, float] = {}
        for dimension, metrics in metricas_por_dimension.items():
            if dimension not in URL_WEIGHTS:
                continue
            score = score_url_dimension(dimension, metrics)
            dimension_scores[dimension] = score
            db.add(
                Dimension(
                    id=uuid.uuid4(),
                    analysis_id=analysis.id,
                    name=dimension,
                    score=score,
                    weight=URL_WEIGHTS[dimension],
                    raw_metrics=metrics,
                )
            )

        for finding in todos_los_hallazgos:
            db.add(
                Finding(
                    id=uuid.uuid4(),
                    analysis_id=analysis.id,
                    type=finding.type,
                    severity=finding.severity,
                    title=finding.title,
                    description=finding.description,
                    url=finding.url,
                    recommendation=finding.recommendation,
                )
            )

        analysis.overall_score = calculate_url_overall_score(dimension_scores, todos_los_hallazgos)
        analysis.confidence_level = calculate_confidence(results)
        analysis.raw_data = metricas_por_dimension
        analysis.status = "completed"
        analysis.completed_at = datetime.now(timezone.utc)
        app_row.last_analyzed_at = analysis.completed_at
        db.commit()
    finally:
        db.close()


def _mark_failed(db: Session, analysis: Analysis, message: str) -> None:
    analysis.status = "failed"
    analysis.error_message = message[:300]
    analysis.completed_at = datetime.now(timezone.utc)
    db.commit()
