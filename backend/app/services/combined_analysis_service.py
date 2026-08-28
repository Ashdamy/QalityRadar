"""Ejecuta el analisis combinado: repositorio y URL, y los compara.

Se apoya en los dos pipelines existentes en vez de duplicar su logica: cada
mitad se ejecuta como un analisis propio y completo (que queda guardado y se
puede consultar por separado), y despues se consolidan sus resultados en el
analisis combinado.
"""

import uuid

from sqlalchemy import select

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.services.rate_limit_service import release
from app.models.analysis import Analysis, Finding
from app.utils.safe_http import fetch_public_page
from app.models.deployed_app import DeployedApp
from app.models.repository import Repository
from app.services.analysis_service import run_repository_analysis
from app.services.correspondence_service import check_correspondence
from app.services.combined_service import (
    apply_severity_cap,
    clear_copied_results,
    build_improvement_plan,
    consolidate_score,
    copy_results_into,
    now,
    persist_discrepancy,
)
from app.services.scoring_service import REPOSITORY_WEIGHTS, URL_WEIGHTS
from app.services.summary_service import build_combined_summary
from app.services.url_analysis_service import run_url_analysis


def run_combined_analysis(analysis_id: str) -> None:
    db = SessionLocal()
    try:
        analysis = db.get(Analysis, uuid.UUID(analysis_id))
        if analysis is None:
            return
        repository = db.get(Repository, analysis.repository_id)
        app_row = db.get(DeployedApp, analysis.app_id)
        if repository is None or app_row is None:
            _fallar(db, analysis, "falta el repositorio o la aplicacion a analizar")
            return

        analysis.status = "running"
        analysis.started_at = now()
        db.commit()

        # Cada mitad se ejecuta como un analisis propio, con su fila. Asi el
        # usuario puede abrirlos por separado y entran en el historico.
        sub_repo = _crear_subanalisis(db, analysis, repository_id=repository.id)
        sub_url = _crear_subanalisis(db, analysis, app_id=app_row.id)

        run_repository_analysis(str(sub_repo))
        run_url_analysis(str(sub_url))

        db.expire_all()
        repo_analysis = db.get(Analysis, sub_repo)
        url_analysis = db.get(Analysis, sub_url)

        fallidos = [
            nombre
            for nombre, sub in (("el repositorio", repo_analysis), ("la URL", url_analysis))
            if sub is None or sub.status != "completed"
        ]
        if fallidos:
            motivo = (url_analysis.error_message if url_analysis else None) or (
                repo_analysis.error_message if repo_analysis else None
            )
            _fallar(
                db,
                analysis,
                f"no se pudo analizar {' ni '.join(fallidos)}"
                + (f": {motivo}" if motivo else ""),
            )
            return

        analysis.status = "scoring"
        db.commit()

        repo_score = float(repo_analysis.overall_score or 0)
        url_score = float(url_analysis.overall_score or 0)

        # Se copian dimensiones y hallazgos para que el combinado sea
        # autocontenido: al exportarlo o compararlo no hay que reconstruirlo.
        # Un reintento no debe chocar con lo que dejo el intento anterior.
        clear_copied_results(db, analysis)
        copy_results_into(db, analysis, repo_analysis, REPOSITORY_WEIGHTS, "codigo")
        copy_results_into(db, analysis, url_analysis, URL_WEIGHTS, "produccion")

        hallazgos_repo = list(
            db.scalars(select(Finding).where(Finding.analysis_id == repo_analysis.id)).all()
        )
        hallazgos_url = list(
            db.scalars(select(Finding).where(Finding.analysis_id == url_analysis.id)).all()
        )

        # Antes de interpretar la discrepancia hay que saber si ambos lados
        # son de verdad el mismo proyecto: comparar el codigo de uno con la web
        # de otro no significa nada.
        correspondencia = _comprobar_correspondencia(
            repository.full_name, app_row.url, repo_analysis.raw_data
        )
        if correspondencia and correspondencia.warning:
            db.add(
                Finding(
                    id=uuid.uuid4(),
                    analysis_id=analysis.id,
                    type="structure",
                    severity="high",
                    title=(
                        "No hay aplicacion desplegada en esa direccion"
                        if correspondencia.kind == "no_deployment"
                        else "El repositorio y la direccion podrian no ser el mismo proyecto"
                    ),
                    description=correspondencia.warning
                    + " Motivos: "
                    + " ".join(correspondencia.reasons),
                    url=app_row.url,
                    recommendation=(
                        "Comprueba que la direccion sea el despliegue de este repositorio. "
                        "Si lo es, ignora este aviso."
                    ),
                )
            )

        discrepancia = persist_discrepancy(db, analysis, repo_score, url_score)
        plan = build_improvement_plan(
            hallazgos_repo,
            hallazgos_url,
            discrepancia.recommendations if discrepancia else None,
        )

        consolidada = consolidate_score(repo_score, url_score)
        analysis.overall_score = apply_severity_cap(
            consolidada, hallazgos_repo + hallazgos_url
        )
        analysis.confidence_level = round(
            (float(repo_analysis.confidence_level or 0) + float(url_analysis.confidence_level or 0))
            / 2,
            2,
        )
        analysis.commit_hash = repo_analysis.commit_hash
        analysis.commit_message = repo_analysis.commit_message
        analysis.branch = repo_analysis.branch
        analysis.raw_data = {
            "repository_analysis_id": str(repo_analysis.id),
            "url_analysis_id": str(url_analysis.id),
            "repository_score": repo_score,
            "url_score": url_score,
            "improvement_plan": plan,
            "correspondence": (
                {
                    "kind": correspondencia.kind,
                    "looks_related": correspondencia.looks_related,
                    "confidence": correspondencia.confidence,
                    "reasons": correspondencia.reasons,
                    "warning": correspondencia.warning,
                }
                if correspondencia
                else None
            ),
        }

        analysis.summary_text, analysis.summary_source = build_combined_summary(
            repository_name=repository.full_name,
            url=app_row.url,
            repo_score=repo_score,
            url_score=url_score,
            consolidated_score=float(analysis.overall_score),
            discrepancy_explanation=discrepancia.explanation if discrepancia else None,
            plan=[(item["severity"], item["title"]) for item in plan],
            api_key=get_settings().huggingface_api_key or None,
        )

        analysis.status = "completed"
        analysis.completed_at = now()
        repository.last_analyzed_at = analysis.completed_at
        app_row.last_analyzed_at = analysis.completed_at
        db.commit()
    except Exception as exc:  # noqa: BLE001
        # Sin esto un fallo inesperado deja el analisis en "scoring" para
        # siempre y el cliente lo sondea hasta agotar los reintentos. Se marca
        # como fallado y se deja que Celery registre la traza.
        db.rollback()
        analisis = db.get(Analysis, uuid.UUID(analysis_id))
        if analisis is not None and analisis.status not in ("completed", "failed"):
            _fallar(db, analisis, f"error inesperado: {exc}")
        raise
    finally:
        # Se libera el hueco de analisis simultaneos pase lo que pase: si no,
        # un fallo dejaria la cuenta bloqueada hasta que caducara el TTL.
        _liberar_hueco(db, analysis_id)
        db.close()


def _crear_subanalisis(
    db, parent: Analysis, *, repository_id=None, app_id=None
) -> uuid.UUID:
    sub = Analysis(
        id=uuid.uuid4(),
        user_id=parent.user_id,
        repository_id=repository_id,
        app_id=app_id,
        analysis_type="repository" if repository_id else "url",
        status="pending",
    )
    db.add(sub)
    db.commit()
    return sub.id


def _fallar(db, analysis: Analysis, mensaje: str) -> None:
    analysis.status = "failed"
    analysis.error_message = mensaje[:300]
    analysis.completed_at = now()
    db.commit()


def _comprobar_correspondencia(repository_full_name: str, url: str, repo_raw_data):
    """Contrasta el repositorio con la pagina servida en esa direccion.

    Solo hace falta descargar la pagina: las senales del lado del repositorio
    salen de las metricas que el analizador de estructura ya calculo. Si la
    descarga falla se omite el aviso en vez de invalidar el analisis.
    """
    try:
        fetched = fetch_public_page(url)
    except Exception:  # noqa: BLE001
        return None

    return check_correspondence(
        repository_full_name=repository_full_name,
        url=url,
        html=fetched.text,
        structure_metrics=(repo_raw_data or {}).get("structure"),
    )


def _liberar_hueco(db, analysis_id: str) -> None:
    """Devuelve el hueco de simultaneos al terminar (bien o mal)."""
    try:
        fila = db.get(Analysis, uuid.UUID(analysis_id))
        if fila is not None:
            release(fila.user_id, analysis_id)
    except Exception:  # noqa: BLE001
        # Nunca debe tapar el resultado real del analisis.
        pass
