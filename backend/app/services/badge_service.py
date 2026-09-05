"""Insignia de calidad para el README del repositorio analizado.

Un SVG con la nota, servido sin autenticacion, que el dueno pega en su portada.
Es la unica parte del sistema pensada para que la vea gente que no tiene cuenta
aqui, y de eso salen las decisiones:

- **El token no caduca.** El resto de enlaces publicos caducan a los 7 dias; uno
  que se apagara solo dejaria una imagen rota en la portada de un proyecto
  ajeno. Se revoca a mano, que es lo que corresponde a algo que su dueno
  decidio publicar.
- **Apunta al repositorio, no a un analisis.** Si apuntara a uno concreto, la
  insignia se quedaria congelada en la nota de aquel dia.
- **Solo sale el numero.** Ni el nombre del repositorio ni los hallazgos: el
  informe sigue detras de su propio enlace, con su caducidad. Si el token se
  filtrara antes de publicarlo, lo que se lleva quien lo tenga es una cifra.

Del SVG no forma parte ningun texto que venga de fuera: la etiqueta es fija y
la nota se formatea desde un numero. No hay nada que escapar porque no entra
nada que escapar.
"""

import secrets
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.analysis import Analysis
from app.models.repository import Repository

# Los mismos tramos con los que se presenta la nota en la aplicacion, para que
# la insignia no cuente una historia distinta de la del informe.
_TRAMOS = (
    (80, "#2f8f4e"),  # verde
    (60, "#8a9a2b"),  # oliva
    (40, "#c8811a"),  # ambar
    (0, "#c0392b"),   # rojo
)
_GRIS = "#8a8f98"

CACHE_SECONDS = 300


def issue_badge_token(db: Session, repository: Repository) -> str:
    """Devuelve el token de la insignia, creandolo la primera vez.

    Pedirla dos veces da el mismo token a proposito: si cambiara, la insignia
    ya pegada en un README dejaria de funcionar sin que nadie lo tocara.
    """
    if repository.badge_token is None:
        repository.badge_token = secrets.token_urlsafe(24)
    return repository.badge_token


def revoke_badge_token(db: Session, repository: Repository) -> bool:
    """Apaga la insignia. Devuelve si habia alguna encendida."""
    if repository.badge_token is None:
        return False
    repository.badge_token = None
    return True


def score_for_token(db: Session, token: str) -> float | None:
    """Nota del ultimo analisis terminado del repositorio de ese token.

    None si el token no existe o si el repositorio no tiene ningun analisis
    terminado. Los dos casos dan la misma insignia, para que no sirva de
    oraculo sobre que tokens han existido.
    """
    if not token:
        return None

    repositorio = db.scalar(select(Repository).where(Repository.badge_token == token))
    if repositorio is None:
        return None

    return db.scalar(
        select(Analysis.overall_score)
        .where(
            Analysis.repository_id == repositorio.id,
            Analysis.status == "completed",
            Analysis.overall_score.is_not(None),
        )
        .order_by(Analysis.created_at.desc())
        .limit(1)
    )


def _color(score: float | None) -> str:
    if score is None:
        return _GRIS
    for minimo, color in _TRAMOS:
        if score >= minimo:
            return color
    return _GRIS


def _ancho_del_texto(texto: str) -> int:
    """Ancho aproximado en pixeles a 11px, sin medir la fuente de verdad.

    Basta con acercarse: el SVG se dibuja con la fuente que tenga el navegador,
    asi que la medida exacta no existe. Se redondea hacia arriba para que el
    texto nunca se salga de su mitad.
    """
    return int(len(texto) * 6.5) + 10


def render_badge(score: float | None) -> str:
    """SVG de la insignia. Sin texto de fuera, asi que no hay nada que escapar."""
    etiqueta = "calidad"
    valor = f"{score:.0f}/100" if score is not None else "sin analizar"

    ancho_etiqueta = _ancho_del_texto(etiqueta)
    ancho_valor = _ancho_del_texto(valor)
    total = ancho_etiqueta + ancho_valor
    color = _color(score)

    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{total}" height="20" '
        f'role="img" aria-label="{etiqueta}: {valor}">'
        f"<title>{etiqueta}: {valor}</title>"
        '<linearGradient id="s" x2="0" y2="100%">'
        '<stop offset="0" stop-color="#bbb" stop-opacity=".1"/>'
        '<stop offset="1" stop-opacity=".1"/></linearGradient>'
        f'<clipPath id="r"><rect width="{total}" height="20" rx="3" fill="#fff"/></clipPath>'
        '<g clip-path="url(#r)">'
        f'<rect width="{ancho_etiqueta}" height="20" fill="#3f4550"/>'
        f'<rect x="{ancho_etiqueta}" width="{ancho_valor}" height="20" fill="{color}"/>'
        f'<rect width="{total}" height="20" fill="url(#s)"/></g>'
        '<g fill="#fff" text-anchor="middle" '
        'font-family="Verdana,Geneva,DejaVu Sans,sans-serif" font-size="11">'
        # La sombra desplazada un pixel es lo que hace legible el texto claro
        # sobre los tonos mas claros de la escala.
        f'<text x="{ancho_etiqueta / 2}" y="15" fill="#010101" fill-opacity=".3">{etiqueta}</text>'
        f'<text x="{ancho_etiqueta / 2}" y="14">{etiqueta}</text>'
        f'<text x="{ancho_etiqueta + ancho_valor / 2}" y="15" fill="#010101" '
        f'fill-opacity=".3">{valor}</text>'
        f'<text x="{ancho_etiqueta + ancho_valor / 2}" y="14">{valor}</text>'
        "</g></svg>"
    )
