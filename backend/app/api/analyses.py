import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.models.analysis import Analysis, Dimension, Discrepancy, Finding
from app.models.repository import Repository
from app.models.user import User
from app.models.deployed_app import DeployedApp
from app.schemas.analysis import (
    AnalysisListItem,
    AnalysisOut,
    CombinedOut,
    CorrespondenceOut,
    DimensionOut,
    FindingOut,
    PlanItemOut,
)
from app.services.rate_limit_service import RateLimitExceeded, check_and_reserve, release
from app.services.report_service import aviso_de_cobertura, build_analysis_report
from app.tasks import queue_combined_analysis, queue_repository_analysis, queue_url_analysis

router = APIRouter(prefix="/api/analyses", tags=["analyses"])

# Orden en que se presentan los hallazgos: lo mas grave primero, para que el
# usuario vea antes lo que de verdad importa.
SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}

# Estados desde los que todavia se puede cancelar.
EN_MARCHA = ("pending", "cloning", "running", "scoring")
# Y desde los que se puede reintentar.
TERMINADOS_MAL = ("failed", "timeout", "cancelled")

# Reintentos que no cuentan para la cuota horaria. Con un corte de red, cobrarle
# al usuario el fallo no tiene sentido; sin tope, seria una forma de saltarse
# los limites de uso.
MAX_FREE_RETRIES = 3

_COLAS = {
    "repository": queue_repository_analysis,
    "url": queue_url_analysis,
    "combined": queue_combined_analysis,
}


def _analisis_propio(db: Session, analysis_id: uuid.UUID, user: User) -> Analysis:
    analysis = db.get(Analysis, analysis_id)
    # 404 tanto si no existe como si es de otro usuario: no se revela que
    # analisis existen en cuentas ajenas.
    if analysis is None or analysis.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="analisis no encontrado")
    return analysis


# Va antes que "/{analysis_id}" a proposito: si fuera despues, la ruta con
# parametro se lo tragaria y "" nunca llegaria aqui.
@router.get("", response_model=list[AnalysisListItem])
def list_analyses(
    limit: int = 20,
    offset: int = 0,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[AnalysisListItem]:
    """Los analisis de quien pregunta, del mas reciente al mas antiguo.

    Sin esto no habia forma de volver a un analisis de URL: se llegaba a uno
    por su identificador o por el historico de un repositorio, y los de URL no
    cuelgan de ninguno. Cerrar la pestaña equivalia a perderlo.
    """
    limit = max(1, min(limit, 100))
    offset = max(0, offset)

    analisis = db.scalars(
        select(Analysis)
        .where(Analysis.user_id == current_user.id)
        .order_by(Analysis.created_at.desc())
        .limit(limit)
        .offset(offset)
    ).all()

    # Los objetivos se piden en bloque y no uno por linea: con veinte lineas,
    # una consulta por cada una son veinte viajes a la base para nada.
    repos = _por_id(db, Repository, {a.repository_id for a in analisis})
    apps = _por_id(db, DeployedApp, {a.app_id for a in analisis})

    return [
        AnalysisListItem(
            id=str(a.id),
            analysis_type=a.analysis_type,
            status=a.status,
            target=_nombre_del_objetivo(a, repos, apps),
            overall_score=float(a.overall_score) if a.overall_score is not None else None,
            created_at=a.created_at.isoformat(),
        )
        for a in analisis
    ]


def _por_id(db: Session, modelo, ids: set) -> dict:
    concretos = {i for i in ids if i is not None}
    if not concretos:
        return {}
    return {fila.id: fila for fila in db.scalars(select(modelo).where(modelo.id.in_(concretos)))}


def _nombre_del_objetivo(analysis: Analysis, repos: dict, apps: dict) -> str:
    repositorio = repos.get(analysis.repository_id)
    aplicacion = apps.get(analysis.app_id)
    if analysis.analysis_type == "combined" and repositorio and aplicacion:
        return f"{repositorio.full_name} + {aplicacion.url}"
    if repositorio:
        return repositorio.full_name
    if aplicacion:
        return aplicacion.url
    # El objetivo pudo borrarse; el analisis sigue siendo suyo y tiene que
    # poder abrirlo.
    return "(objetivo eliminado)"


@router.get("/{analysis_id}", response_model=AnalysisOut)
def get_analysis(
    analysis_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AnalysisOut:
    return serialize_analysis(db, _analisis_propio(db, analysis_id, current_user))


def serialize_analysis(db: Session, analysis: Analysis) -> AnalysisOut:
    dimensions = db.scalars(select(Dimension).where(Dimension.analysis_id == analysis.id)).all()
    findings = db.scalars(select(Finding).where(Finding.analysis_id == analysis.id)).all()
    repository = (
        db.get(Repository, analysis.repository_id) if analysis.repository_id else None
    )

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
        repository_full_name=repository.full_name if repository else None,
        combined=_combined_block(db, analysis),
        coverage_notice=aviso_de_cobertura(dimensions),
        dimensions=[
            DimensionOut(
                name=d.name,
                score=float(d.score),
                weight=float(d.weight),
                subcharacteristics=d.subcharacteristics,
            )
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
    analysis = _analisis_propio(db, analysis_id, current_user)
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


@router.post("/{analysis_id}/cancel", status_code=status.HTTP_204_NO_CONTENT)
def cancel_analysis(
    analysis_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    """Cancela un analisis en marcha y devuelve el hueco.

    No se mata la tarea: se marca en la base y el worker lo comprueba en sus
    puntos de control (antes de clonar, al terminar el clonado y antes de
    puntuar). Matar un proceso a medias deja el directorio temporal sin borrar
    y el hueco sin liberar; que el propio trabajo se entere y salga por su pie
    no deja nada a medias.
    """
    analysis = _analisis_propio(db, analysis_id, current_user)
    if analysis.status not in EN_MARCHA:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="este analisis ya termino",
        )

    analysis.status = "cancelled"
    analysis.completed_at = datetime.now(timezone.utc)
    db.commit()
    # El hueco se devuelve ya: el worker puede tardar en enterarse, y mientras
    # tanto no tiene sentido que la cuenta lo siga teniendo ocupado.
    release(current_user.id, str(analysis.id))


@router.post("/{analysis_id}/retry", status_code=status.HTTP_202_ACCEPTED)
def retry_analysis(
    analysis_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Reintenta un analisis que no llego a terminar.

    Se reutiliza la misma fila en vez de crear otra, para que el enlace y el
    identificador que el usuario ya tenia sigan valiendo.

    Los primeros reintentos no cuentan para la cuota horaria: si fallo por un
    corte de red, cobrarselo al usuario no tiene sentido. El hueco de
    simultaneos si se toma, porque ese protege la maquina.
    """
    analysis = _analisis_propio(db, analysis_id, current_user)
    if analysis.status not in TERMINADOS_MAL:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="solo se reintentan los analisis que no terminaron bien",
        )
    if analysis.analysis_type not in _COLAS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="este analisis no se puede reintentar"
        )

    gratis = analysis.retry_count < MAX_FREE_RETRIES
    try:
        check_and_reserve(current_user.id, str(analysis.id), contar=not gratis)
    except RateLimitExceeded as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=exc.message,
            headers={"Retry-After": str(exc.retry_after_seconds)},
        ) from exc

    analysis.status = "pending"
    analysis.error_message = None
    analysis.started_at = None
    analysis.completed_at = None
    analysis.retry_count += 1
    db.commit()

    _COLAS[analysis.analysis_type](str(analysis.id))
    return {"analysis_id": str(analysis.id), "retry_count": analysis.retry_count}
