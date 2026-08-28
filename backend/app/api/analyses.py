import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.models.analysis import Analysis, Dimension, Finding
from app.models.user import User
from app.schemas.analysis import AnalysisOut, DimensionOut, FindingOut

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
                recommendation=f.recommendation,
            )
            for f in sorted(findings, key=lambda f: SEVERITY_ORDER.get(f.severity, 99))
        ],
    )
