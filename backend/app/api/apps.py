"""Analisis de aplicaciones desplegadas (Modo 2)."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.models.analysis import Analysis
from app.models.deployed_app import DeployedApp
from app.models.user import User
from app.models.repository import Repository
from app.services.rate_limit_service import RateLimitExceeded, check_and_reserve
from app.tasks import queue_combined_analysis, queue_url_analysis
from app.utils.url_validation import UnsafeUrlError, validate_public_url

router = APIRouter(prefix="/api/apps", tags=["apps"])


class AnalyzeUrlRequest(BaseModel):
    url: str
    name: str | None = None


@router.post("/analyze", status_code=status.HTTP_202_ACCEPTED)
def analyze_url(
    payload: AnalyzeUrlRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Encola el analisis de una URL publica.

    Nota de alcance: el spec permite analizar una URL sin autenticacion, pero
    ese endpoint hace peticiones salientes por orden de quien lo llame, asi
    que sin limites de uso seria un amplificador de abuso. Se exige sesion
    hasta que exista el rate limiting (Semana 5).
    """
    try:
        # Se valida antes de guardar nada: no se registra una URL que no
        # vamos a poder analizar.
        objetivo = validate_public_url(payload.url)
    except UnsafeUrlError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    analysis_id = uuid.uuid4()
    reservar_o_429(current_user.id, analysis_id)

    app_row = DeployedApp(
        id=uuid.uuid4(),
        user_id=current_user.id,
        name=(payload.name or objetivo.hostname)[:255],
        url=objetivo.url,
    )
    db.add(app_row)
    db.flush()

    analysis = Analysis(
        id=analysis_id,
        user_id=current_user.id,
        app_id=app_row.id,
        analysis_type="url",
        status="pending",
    )
    db.add(analysis)
    db.commit()

    queue_url_analysis(str(analysis.id))
    return {"analysis_id": str(analysis.id)}


class AnalyzeCombinedRequest(BaseModel):
    repository_id: uuid.UUID
    url: str


@router.post("/analyze-combined", status_code=status.HTTP_202_ACCEPTED)
def analyze_combined(
    payload: AnalyzeCombinedRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Analiza el repositorio y su despliegue, y compara ambos resultados."""
    repository = db.get(Repository, payload.repository_id)
    if repository is None or repository.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="repositorio no encontrado"
        )
    if repository.is_private:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="solo se analizan repositorios publicos",
        )

    try:
        objetivo = validate_public_url(payload.url)
    except UnsafeUrlError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    analysis_id = uuid.uuid4()
    reservar_o_429(current_user.id, analysis_id)

    app_row = DeployedApp(
        id=uuid.uuid4(),
        user_id=current_user.id,
        name=objetivo.hostname[:255],
        url=objetivo.url,
    )
    db.add(app_row)
    db.flush()

    analysis = Analysis(
        id=analysis_id,
        user_id=current_user.id,
        repository_id=repository.id,
        app_id=app_row.id,
        analysis_type="combined",
        status="pending",
    )
    db.add(analysis)
    db.commit()

    queue_combined_analysis(str(analysis.id))
    return {"analysis_id": str(analysis.id)}


def reservar_o_429(user_id, analysis_id) -> None:
    """Comprueba los limites de uso antes de crear y encolar nada.

    Va aqui y no en el worker porque un 202 para algo que despues se descarta
    en silencio seria mentir al cliente.
    """
    try:
        check_and_reserve(user_id, str(analysis_id))
    except RateLimitExceeded as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=exc.message,
            headers={"Retry-After": str(exc.retry_after_seconds)},
        ) from exc
