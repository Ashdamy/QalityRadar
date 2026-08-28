"""Compartir un informe mediante un enlace publico y temporal."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.analyses import serialize_analysis
from app.api.deps import get_current_user, get_db
from app.models.analysis import Analysis
from app.models.user import User
from app.schemas.analysis import AnalysisOut, ShareLinkOut
from app.services.rate_limit_service import current_usage
from app.services.share_service import (
    DEFAULT_EXPIRY_DAYS,
    MAX_EXPIRY_DAYS,
    create_share_link,
    resolve_share_token,
    revoke_share_link,
)

router = APIRouter(tags=["share"])


class ShareRequest(BaseModel):
    expiry_days: int | None = None


def _analisis_propio(analysis_id: uuid.UUID, current_user: User, db: Session) -> Analysis:
    analysis = db.get(Analysis, analysis_id)
    # 404 tambien si es de otro usuario: no revelamos que analisis existen en
    # cuentas ajenas.
    if analysis is None or analysis.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="analisis no encontrado"
        )
    return analysis


@router.post(
    "/api/analyses/{analysis_id}/share",
    response_model=ShareLinkOut,
    status_code=status.HTTP_201_CREATED,
)
def share_analysis(
    analysis_id: uuid.UUID,
    payload: ShareRequest | None = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ShareLinkOut:
    """Crea un enlace publico al informe. Caduca a los 7 dias por defecto."""
    analysis = _analisis_propio(analysis_id, current_user, db)
    if analysis.status != "completed":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="solo se pueden compartir analisis terminados",
        )

    enlace = create_share_link(db, analysis, payload.expiry_days if payload else None)
    db.commit()
    db.refresh(enlace)
    return ShareLinkOut(token=enlace.token, expires_at=enlace.expires_at.isoformat())


@router.delete(
    "/api/analyses/{analysis_id}/share/{token}", status_code=status.HTTP_204_NO_CONTENT
)
def unshare_analysis(
    analysis_id: uuid.UUID,
    token: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    """Invalida un enlace ya repartido."""
    analysis = _analisis_propio(analysis_id, current_user, db)
    if not revoke_share_link(db, analysis, token):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="enlace no encontrado")
    db.commit()


@router.get("/api/reports/shared/{token}", response_model=AnalysisOut)
def read_shared_report(token: str, db: Session = Depends(get_db)) -> AnalysisOut:
    """Lee un informe compartido. Sin autenticacion: el token es la credencial.

    Un token inexistente y uno caducado dan la misma respuesta, para que este
    endpoint no sirva de oraculo sobre que tokens han existido.
    """
    analysis = resolve_share_token(db, token)
    if analysis is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="el enlace no existe o ha caducado",
        )
    return serialize_analysis(db, analysis)


@router.get("/api/reports/shared-config")
def share_config() -> dict:
    """Limites de caducidad, para que el cliente no los duplique."""
    return {"default_expiry_days": DEFAULT_EXPIRY_DAYS, "max_expiry_days": MAX_EXPIRY_DAYS}


@router.get("/api/usage")
def read_usage(current_user: User = Depends(get_current_user)) -> dict:
    """Consumo actual frente a los limites, para mostrarlo antes de analizar."""
    return current_usage(current_user.id)
