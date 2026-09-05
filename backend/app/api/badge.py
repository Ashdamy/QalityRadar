"""Insignia de calidad para el README del repositorio analizado."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.core.config import get_settings
from app.models.repository import Repository
from app.models.user import User
from app.services.badge_service import (
    CACHE_SECONDS,
    issue_badge_token,
    render_badge,
    revoke_badge_token,
    score_for_token,
)

router = APIRouter(tags=["badge"])


class BadgeOut(BaseModel):
    token: str
    image_url: str
    # Listo para pegar: es lo unico que el usuario necesita de aqui.
    markdown: str


def _repositorio_propio(db: Session, repository_id: uuid.UUID, user: User) -> Repository:
    repositorio = db.get(Repository, repository_id)
    # 404 tambien si es de otro: no se revela que repositorios hay en cuentas
    # ajenas.
    if repositorio is None or repositorio.user_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="repositorio no encontrado"
        )
    return repositorio


@router.post(
    "/api/repositories/{repository_id}/badge",
    response_model=BadgeOut,
    status_code=status.HTTP_201_CREATED,
)
def create_badge(
    repository_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> BadgeOut:
    """Enciende la insignia y devuelve el markdown para pegar en el README.

    Pedirla dos veces devuelve la misma: si el token cambiara, la insignia ya
    pegada dejaria de funcionar sin que nadie la tocara.
    """
    repositorio = _repositorio_propio(db, repository_id, current_user)
    token = issue_badge_token(db, repositorio)
    db.commit()

    url = f"{get_settings().public_base_url}/api/badge/{token}.svg"
    return BadgeOut(
        token=token,
        image_url=url,
        markdown=f"[![Calidad]({url})]({get_settings().public_base_url})",
    )


@router.delete(
    "/api/repositories/{repository_id}/badge", status_code=status.HTTP_204_NO_CONTENT
)
def delete_badge(
    repository_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    """Apaga la insignia. La imagen ya pegada pasa a decir "sin analizar"."""
    repositorio = _repositorio_propio(db, repository_id, current_user)
    if not revoke_badge_token(db, repositorio):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="este repositorio no tiene insignia"
        )
    db.commit()


@router.get("/api/badge/{token}.svg")
def read_badge(token: str, db: Session = Depends(get_db)) -> Response:
    """Devuelve el SVG. Sin autenticacion: lo pide el navegador de cualquiera
    que visite el README.

    Un token que no existe y uno revocado dan la misma imagen, para que esto no
    sirva de oraculo sobre que tokens han existido. Y devuelve una insignia
    valida en vez de un 404, porque un 404 deja una imagen rota en la portada
    de un proyecto.
    """
    svg = render_badge(score_for_token(db, token))
    return Response(
        content=svg,
        media_type="image/svg+xml",
        headers={
            # GitHub sirve las imagenes del README por su propia cache, asi que
            # esto le dice cada cuanto volver a preguntar. Cinco minutos: lo
            # justo para que un analisis nuevo se vea pronto sin convertir cada
            # visita al repositorio en una consulta a la base de datos.
            "Cache-Control": f"public, max-age={CACHE_SECONDS}",
        },
    )
