import uuid

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.models.analysis import Analysis, Dimension, Discrepancy, Finding
from app.models.repository import Repository
from app.models.user import User
from app.schemas.analysis import (
    AnalysisOut,
    CombinedOut,
    CorrespondenceOut,
    DimensionOut,
    FindingOut,
    PlanItemOut,
)
from app.services.report_service import build_analysis_report

router = APIRouter(prefix="/api/analyses", tags=["analyses"])

# Orden en que se presentan los hallazgos: lo mas grave primero, para que el
# usuario vea antes lo que de verdad importa.
SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}


@router.get("/{analysis_id}", response_model=AnalysisOut)
def get_analysis(
    analysis_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AnalysisOut:
    analysis = db.get(Analysis, analysis_id)
    # 404 tanto si no existe como si es de otro usuario: no revelamos que
    # analisis existen en cuentas ajenas.
    if analysis is None or analysis.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="analisis no encontrado")

    dimensions = db.scalars(select(Dimension).where(Dimension.analysis_id == analysis.id)).all()
    findings = db.scalars(select(Finding).where(Finding.analysis_id == analysis.id)).all()

    return AnalysisOut(
        id=str(analysis.id),
        status=analysis.status,
        overall_score=float(analysis.overall_score) if analysis.overall_score is not None else None,
        confidence_level=(
            float(analysis.confidence_level) if analysis.confidence_level is not None else None
        ),
        commit_hash=analysis.commit_hash,
        commit_message=analysis.commit_message,
        error_message=analysis.error_message,
        summary_text=analysis.summary_text,
        summary_source=analysis.summary_source,
        analysis_type=analysis.analysis_type,
        combined=_combined_block(db, analysis),
        dimensions=[
            DimensionOut(name=d.name, score=float(d.score), weight=float(d.weight))
            for d in dimensions
        ],
        findings=[
            FindingOut(
                type=f.type,
                severity=f.severity,
                title=f.title,
                description=f.description,
                file_path=f.file_path,
                url=f.url,
                recommendation=f.recommendation,
            )
            for f in sorted(findings, key=lambda f: SEVERITY_ORDER.get(f.severity, 99))
        ],
    )


def _combined_block(db: Session, analysis: Analysis) -> CombinedOut | None:
    """Reune los datos propios del modo combinado, si el analisis es de ese tipo.

    Viven en dos sitios: la tabla `discrepancies` y el `raw_data` del analisis.
    Se juntan aqui para que el cliente reciba un unico bloque coherente.
    """
    if analysis.analysis_type != "combined":
        return None

    bruto = analysis.raw_data or {}
    correspondencia = bruto.get("correspondence")
    discrepancia = db.scalar(
        select(Discrepancy).where(Discrepancy.analysis_id == analysis.id)
    )

    return CombinedOut(
        repository_score=bruto.get("repository_score"),
        url_score=bruto.get("url_score"),
        delta=float(discrepancia.delta) if discrepancia else None,
        explanation=discrepancia.explanation if discrepancia else None,
        recommendations=discrepancia.recommendations if discrepancia else None,
        improvement_plan=[PlanItemOut(**item) for item in bruto.get("improvement_plan", [])],
        correspondence=CorrespondenceOut(**correspondencia) if correspondencia else None,
    )


@router.get("/{analysis_id}/report.pdf")
def download_report(
    analysis_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    analysis = db.get(Analysis, analysis_id)
    if analysis is None or analysis.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="analisis no encontrado")
    if analysis.status != "completed":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="el analisis todavia no ha terminado",
        )

    repository = db.get(Repository, analysis.repository_id) if analysis.repository_id else None
    dimensions = db.scalars(select(Dimension).where(Dimension.analysis_id == analysis.id)).all()
    findings = db.scalars(select(Finding).where(Finding.analysis_id == analysis.id)).all()

    pdf = build_analysis_report(
        repository_full_name=repository.full_name if repository else "proyecto",
        analysis=analysis,
        dimensions=list(dimensions),
        findings=list(findings),
    )

    nombre_base = (repository.name if repository else "analisis").replace("/", "-")
    fecha = analysis.completed_at.strftime("%Y-%m-%d") if analysis.completed_at else "informe"
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="qalitiradar-{nombre_base}-{fecha}.pdf"'
        },
    )
