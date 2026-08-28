"""Comprueba si el repositorio y la URL parecen ser el mismo proyecto.

Es facil equivocarse de direccion al lanzar un analisis combinado, y entonces
la comparacion no significa nada: se estaria contrastando el codigo de un
proyecto con la web de otro.

Decision deliberada: esto **avisa, no bloquea**. No se puede demostrar que una
URL sea el despliegue de un repositorio, y hay casos perfectamente validos
donde los nombres no coinciden: dominio propio, monorepos, proyectos
renombrados, despliegues bajo la marca de un cliente. Bloquear ahi seria peor
que el problema que resuelve.

Se distinguen dos tipos de senal. La pagina por defecto de la plataforma es
un hecho comprobable (dice literalmente que ahi no hay despliegue) y advierte
por si sola. Las otras dos son heuristicas con explicaciones inocentes por
separado, asi que solo advierten cuando coinciden las dos.
"""

import re
from dataclasses import dataclass
from urllib.parse import urlparse

# Paginas por defecto de las plataformas: si la URL devuelve esto, no hay una
# aplicacion desplegada ahi que analizar.
PLACEHOLDER_MARKERS = (
    "deployment not found",
    "the deployment could not be found",
    "404: not_found",
    "no production deployment",
    "site not found",
    "there isn't a github pages site here",
    "your new nuxt project",
    "welcome to nginx",
    "future home of something quite cool",
)

# Extensiones que solo aparecen en un proyecto que genera interfaz web.
WEB_EXTENSIONS = {".html", ".htm", ".jsx", ".tsx", ".vue", ".svelte", ".astro"}
WEB_LANGUAGES = {"JavaScript", "TypeScript"}

# Palabras que aparecen en casi cualquier nombre y no distinguen nada.
STOPWORDS = {
    "app", "web", "site", "www", "com", "io", "dev", "org", "net", "github",
    "vercel", "netlify", "pages", "main", "my", "the", "project", "demo", "test",
}


@dataclass
class CorrespondenceCheck:
    # "ok", "no_deployment" o "possible_mismatch". Quien consume el resultado
    # decide por este campo, no leyendo el texto del aviso.
    kind: str
    looks_related: bool
    confidence: str  # "alta", "media" o "baja"
    reasons: list[str]
    warning: str | None


def _tokens(texto: str) -> set[str]:
    partes = re.split(r"[^a-z0-9]+", texto.lower())
    return {p for p in partes if len(p) > 2 and p not in STOPWORDS}


def check_correspondence(
    *,
    repository_full_name: str,
    url: str,
    html: str,
    structure_metrics: dict | None = None,
) -> CorrespondenceCheck:
    """Evalua si la URL parece ser el despliegue de ese repositorio.

    `structure_metrics` son las metricas que el analizador de estructura ya
    calculo para este mismo repositorio. Se reutilizan en vez de volver a
    clonarlo: la informacion necesaria (extensiones, lenguajes y forma del
    proyecto) ya esta ahi.
    """
    razones: list[str] = []

    # -- Senal fuerte: la pagina es un marcador de posicion de la plataforma --
    # No es una heuristica: la pagina dice literalmente que ahi no hay ningun
    # despliegue, asi que basta por si sola para advertir.
    es_placeholder = any(m in html[:20000].lower() for m in PLACEHOLDER_MARKERS)
    if es_placeholder:
        razones.append(
            "La direccion devuelve una pagina por defecto de la plataforma, no una "
            "aplicacion desplegada."
        )

    # -- Senal debil 1: el nombre del repositorio aparece en el dominio -------
    hostname = urlparse(url).hostname or ""
    repo_name = repository_full_name.split("/")[-1]
    nombre_coincide = bool(_tokens(repository_full_name) & _tokens(hostname))
    if nombre_coincide:
        razones.append(f"El nombre del repositorio aparece en el dominio ({hostname}).")
    else:
        razones.append(
            f"El dominio ({hostname}) no contiene el nombre del repositorio ({repo_name}). "
            "Es normal si usas un dominio propio."
        )

    # -- Senal debil 2: el repositorio no produce una web --------------------
    # Solo se evalua si hay metricas: su ausencia no es evidencia de nada.
    no_es_web = bool(structure_metrics) and not _parece_proyecto_web(structure_metrics)
    if no_es_web:
        razones.append(
            "El repositorio no parece generar una interfaz web: no contiene plantillas "
            "ni componentes de front-end."
        )

    # Las dos senales debiles tienen explicaciones inocentes por separado: un
    # dominio propio, o un backend desplegado como API. Solo cuando coinciden
    # ambas deja de haber una lectura benigna.
    debiles = (not nombre_coincide) and no_es_web
    aviso = None
    tipo = "ok"
    if es_placeholder:
        tipo = "no_deployment"
        # Aqui no hay duda que matizar: no hay aplicacion que analizar, asi que
        # todo lo que mida el lado de produccion es ruido.
        aviso = (
            "En esa direccion no hay ninguna aplicacion desplegada: la plataforma "
            "devuelve su pagina de error. Las metricas de produccion de este analisis "
            "no describen tu proyecto. Comprueba la direccion o vuelve a desplegar "
            "antes de interpretar los resultados."
        )
    elif debiles:
        tipo = "possible_mismatch"
        aviso = (
            "El repositorio y la direccion podrian no corresponder al mismo proyecto. "
            "La comparacion entre codigo y produccion solo tiene sentido si ambos son "
            "las dos caras del mismo despliegue: revisa la direccion antes de sacar "
            "conclusiones de la discrepancia."
        )

    # La confianza sale de las mismas senales que el aviso, para que nunca
    # puedan contarse historias distintas.
    if aviso:
        confianza = "baja"
    elif not nombre_coincide or no_es_web:
        confianza = "media"
    else:
        confianza = "alta"

    return CorrespondenceCheck(
        kind=tipo,
        looks_related=aviso is None,
        confidence=confianza,
        reasons=razones,
        warning=aviso,
    )


def _parece_proyecto_web(structure_metrics: dict) -> bool:
    """Busca en las metricas de estructura indicios de una interfaz web."""
    extensiones = structure_metrics.get("extensions") or {}
    if any(ext in WEB_EXTENSIONS for ext in extensiones):
        return True

    lenguajes = structure_metrics.get("languages") or {}
    if any(lenguaje in WEB_LANGUAGES for lenguaje in lenguajes):
        return True

    # Un repositorio organizado en frontend/ declara su intencion aunque el
    # conteo de extensiones no lo delate.
    return structure_metrics.get("project_shape") in ("frontend", "fullstack")
