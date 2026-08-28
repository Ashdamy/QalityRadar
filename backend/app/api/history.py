"""Histórico de análisis y comparación entre ellos."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.core.config import get_settings
from app.models.analysis import Analysis, AnalysisComparison, Improvement, Regression
from app.models.repository import Repository
from app.models.user import User
from app.schemas.analysis import (
    ChangeOut,
    ComparisonOut,
    ProgressOut,
    TimelineEntry,
)
from app.services.comparison_service import DIMENSION_LABELS, compare_analyses
from app.services.summary_service import build_summary

router = APIRouter(prefix="/api", tags=["history"])


def _owned_repository(db: Session, repository_id: uuid.UUID, user: User) -> Repository:
    repository = db.get(Repository, repository_id)
    # 404 tanto si no existe como si es de otro usuario: no se revela que
    # repositorios hay en cuentas ajenas.
    if repository is None or repository.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="repositorio no encontrado")
    return repository


def _completed_analyses(db: Session, repository_id: uuid.UUID) -> list[Analysis]:
    return list(
        db.scalars(
            select(Analysis)
            .where(Analysis.repository_id == repository_id, Analysis.status == "completed")
            .order_by(Analysis.created_at.asc())
        ).all()
    )


@router.get("/repositories/{repository_id}/timeline", response_model=list[TimelineEntry])
def get_timeline(
    repository_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[TimelineEntry]:
    _owned_repository(db, repository_id, current_user)

    analyses = list(
        db.scalars(
            select(Analysis)
            .where(Analysis.repository_id == repository_id)
            .order_by(Analysis.created_at.asc())
        ).all()
    )

    entradas: list[TimelineEntry] = []
    anterior: float | None = None
    for analysis in analyses:
        score = float(analysis.overall_score) if analysis.overall_score is not None else None
        delta = round(score - anterior, 2) if (score is not None and anterior is not None) else None
        entradas.append(
            TimelineEntry(
                id=str(analysis.id),
                status=analysis.status,
                overall_score=score,
                commit_hash=analysis.commit_hash,
                commit_message=analysis.commit_message,
                created_at=analysis.created_at.isoformat(),
                delta=delta,
            )
        )
        if score is not None:
            anterior = score

    # Lo mas reciente primero, que es como se lee un historial.
    entradas.reverse()
    return entradas


@router.get("/repositories/{repository_id}/progress", response_model=ProgressOut)
def get_progress(
    repository_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ProgressOut:
    _owned_repository(db, repository_id, current_user)
    completados = _completed_analyses(db, repository_id)

    if not completados:
        return ProgressOut(total_analyses=0)

    puntuaciones = [(a, float(a.overall_score)) for a in completados if a.overall_score is not None]
    if not puntuaciones:
        return ProgressOut(total_analyses=len(completados))

    mejor_analisis, mejor = max(puntuaciones, key=lambda par: par[1])
    primero = puntuaciones[0][1]
    actual = puntuaciones[-1][1]
    dias = (completados[-1].created_at - completados[0].created_at).days

    return ProgressOut(
        total_analyses=len(completados),
        current_score=actual,
        best_score=mejor,
        best_score_at=mejor_analisis.created_at.isoformat(),
        first_score=primero,
        total_delta=round(actual - primero, 2),
        days_tracked=dias,
    )


@router.get("/analyses/{analysis_id}/comparison/{other_id}", response_model=ComparisonOut)
def get_comparison(
    analysis_id: uuid.UUID,
    other_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ComparisonOut:
    uno = db.get(Analysis, analysis_id)
    otro = db.get(Analysis, other_id)
    if uno is None or otro is None or uno.user_id != current_user.id or otro.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="analisis no encontrado")
    if uno.id == otro.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="hay que comparar dos analisis distintos",
        )
    if uno.repository_id != otro.repository_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="solo se comparan analisis del mismo repositorio",
        )

    # La comparacion es dirigida: el mas antiguo es el punto de partida, para
    # que "mejora" y "regresion" signifiquen siempre lo mismo.
    previo, actual = (uno, otro) if uno.created_at <= otro.created_at else (otro, uno)

    comparison = db.scalar(
        select(AnalysisComparison).where(
            AnalysisComparison.analysis_1_id == previo.id,
            AnalysisComparison.analysis_2_id == actual.id,
        )
    )
    if comparison is None:
        # Comparar dos analisis cualesquiera del historial es un caso valido:
        # se calcula al vuelo si no existia.
        resultado = compare_analyses(db, previo, actual)
        comparison = db.get(AnalysisComparison, resultado.comparison_id)

    mejoras = db.scalars(
        select(Improvement).where(Improvement.comparison_id == comparison.id)
    ).all()
    regresiones = db.scalars(
        select(Regression).where(Regression.comparison_id == comparison.id)
    ).all()

    origen = None
    if comparison.summary_text is None:
        repository = db.get(Repository, actual.repository_id)
        dias = (actual.created_at - previo.created_at).days
        texto, origen = build_summary(
            repository_name=repository.full_name if repository else "el proyecto",
            previous_score=float(previo.overall_score or 0),
            current_score=float(actual.overall_score or 0),
            days_between=dias,
            improvements=[m.description for m in mejoras],
            regressions=[r.description for r in regresiones],
            api_key=getattr(get_settings(), "huggingface_api_key", None) or None,
        )
        comparison.summary_text = texto
        db.commit()

    delta = float(comparison.score_delta)
    return ComparisonOut(
        id=str(comparison.id),
        analysis_1_id=str(previo.id),
        analysis_2_id=str(actual.id),
        previous_score=float(previo.overall_score) if previo.overall_score is not None else None,
        current_score=float(actual.overall_score) if actual.overall_score is not None else None,
        score_delta=delta,
        trend="mejorando" if delta > 0 else "empeorando" if delta < 0 else "estable",
        summary_text=comparison.summary_text,
        summary_source=origen,
        improvements=[_to_change(m) for m in mejoras],
        regressions=[_to_change(r, severity=True) for r in regresiones],
    )


def _to_change(row, severity: bool = False) -> ChangeOut:
    return ChangeOut(
        dimension=DIMENSION_LABELS.get(row.dimension, row.dimension),
        previous_score=float(row.previous_score) if row.previous_score is not None else None,
        current_score=float(row.current_score) if row.current_score is not None else None,
        delta=float(row.delta),
        description=row.description,
        severity=getattr(row, "severity", None) if severity else None,
    )
