"""Rendimiento, accesibilidad y compatibilidad observables sin navegador.

Nota de alcance, importante para no exagerar lo que medimos: Lighthouse y
axe-core necesitan un navegador sin interfaz (unos 400 MB de contenedor) y
llegan mas adelante. Lo de aqui se obtiene del HTML y de las cabeceras, y es
util pero mas superficial:

- Rendimiento: tiempo de respuesta real, tamano del documento, compresion y
  cabeceras de cache. NO mide el renderizado ni el tiempo hasta que la pagina
  es usable, que es lo que mide Lighthouse.
- Accesibilidad: comprobaciones estaticas sobre el HTML (idioma declarado,
  texto alternativo, etiquetas de formulario). NO sustituye a axe-core, que
  evalua el arbol de accesibilidad ya renderizado.
- Compatibilidad: etiqueta viewport y declaraciones que afectan al movil.
"""

import re

from app.analyzers.base import AnalyzerResult, FindingData
from app.utils.safe_http import FetchResult

# Umbrales de tiempo de respuesta del servidor (no de carga completa).
FAST_RESPONSE_SECONDS = 0.6
SLOW_RESPONSE_SECONDS = 2.0
# Un HTML por encima de esto suele indicar contenido que deberia ir aparte.
LARGE_HTML_BYTES = 250_000

_TAG_IMG = re.compile(r"<img\b[^>]*>", re.I)
_ATTR_ALT = re.compile(r"\balt\s*=", re.I)
_TAG_INPUT = re.compile(r"<input\b[^>]*>", re.I)
_INPUT_SIN_ETIQUETA = re.compile(r'type\s*=\s*["\']?(hidden|submit|button|image|reset)', re.I)
_ATTR_ARIA_LABEL = re.compile(r'\b(aria-label|aria-labelledby|title)\s*=', re.I)
_ATTR_ID = re.compile(r'\bid\s*=\s*["\']([^"\']+)', re.I)
_TAG_LABEL_FOR = re.compile(r'<label\b[^>]*\bfor\s*=\s*["\']([^"\']+)', re.I)
_TAG_TITLE = re.compile(r"<title[^>]*>(.*?)</title>", re.I | re.S)
_META_DESC = re.compile(r'<meta[^>]+name\s*=\s*["\']description["\'][^>]*>', re.I)
_META_VIEWPORT = re.compile(r'<meta[^>]+name\s*=\s*["\']viewport["\'][^>]*>', re.I)
_HTML_LANG = re.compile(r"<html\b[^>]*\blang\s*=", re.I)
_TAG_H1 = re.compile(r"<h1\b", re.I)
_SEMANTIC = re.compile(r"<(main|nav|header|footer|article|section|aside)\b", re.I)


class PerformanceAnalyzer:
    name = "url_performance"

    def analyze(self, fetched: FetchResult) -> AnalyzerResult:
        encoding = fetched.headers.get("content-encoding", "")
        cache_control = fetched.headers.get("cache-control", "")

        metrics = {
            "response_seconds": round(fetched.elapsed_seconds, 3),
            "html_bytes": fetched.content_bytes,
            "uses_compression": bool(encoding and encoding != "identity"),
            "has_cache_control": bool(cache_control),
            "redirect_count": max(0, len(fetched.redirect_chain) - 1),
            "measurement": "tiempo de respuesta del servidor, no de carga completa",
        }

        findings: list[FindingData] = []
        if fetched.elapsed_seconds > SLOW_RESPONSE_SECONDS:
            findings.append(
                FindingData(
                    type="performance",
                    severity="high",
                    title=f"El servidor tarda {fetched.elapsed_seconds:.1f} s en responder",
                    description=(
                        "Ese es el tiempo hasta el primer byte, antes siquiera de empezar a "
                        "dibujar la pagina. Por encima de dos segundos la mayoria de visitantes "
                        "percibe el sitio como lento."
                    ),
                    url=fetched.url,
                    recommendation="Revisa consultas lentas, anade cache de servidor o una CDN.",
                )
            )
        if not metrics["uses_compression"]:
            findings.append(
                FindingData(
                    type="performance",
                    severity="medium",
                    title="La respuesta no viaja comprimida",
                    description=(
                        "Sin compresion gzip o brotli el HTML se envia entero. Comprimirlo suele "
                        "reducir su tamano entre un 60 y un 80 por ciento."
                    ),
                    url=fetched.url,
                    recommendation="Activa la compresion en el servidor o en la CDN.",
                )
            )
        if not cache_control:
            findings.append(
                FindingData(
                    type="performance",
                    severity="low",
                    title="No hay cabeceras de cache",
                    description=(
                        "Sin Cache-Control, cada visita vuelve a descargarlo todo aunque nada haya "
                        "cambiado."
                    ),
                    url=fetched.url,
                    recommendation="Define Cache-Control segun el tipo de recurso.",
                )
            )
        if fetched.content_bytes > LARGE_HTML_BYTES:
            findings.append(
                FindingData(
                    type="performance",
                    severity="medium",
                    title=f"El HTML pesa {fetched.content_bytes // 1024} KB",
                    description=(
                        "Un documento tan grande tarda en descargarse y en procesarse, sobre todo "
                        "en moviles con conexion lenta."
                    ),
                    url=fetched.url,
                    recommendation="Separa el contenido que pueda cargarse despues.",
                )
            )
        if metrics["redirect_count"] >= 2:
            findings.append(
                FindingData(
                    type="performance",
                    severity="low",
                    title=f"Hay {metrics['redirect_count']} redirecciones antes de llegar",
                    description="Cada redireccion anade una ida y vuelta completa a la red.",
                    url=fetched.url,
                    recommendation="Apunta directamente al destino final.",
                )
            )

        return AnalyzerResult(dimension="performance", metrics=metrics, findings=findings)


class AccessibilityAnalyzer:
    name = "url_accessibility"

    def analyze(self, fetched: FetchResult) -> AnalyzerResult:
        html = fetched.text
        imagenes = _TAG_IMG.findall(html)
        sin_alt = [img for img in imagenes if not _ATTR_ALT.search(img)]

        entradas = [i for i in _TAG_INPUT.findall(html) if not _INPUT_SIN_ETIQUETA.search(i)]
        ids_con_label = set(_TAG_LABEL_FOR.findall(html))
        sin_etiqueta = []
        for entrada in entradas:
            if _ATTR_ARIA_LABEL.search(entrada):
                continue
            match_id = _ATTR_ID.search(entrada)
            if match_id and match_id.group(1) in ids_con_label:
                continue
            sin_etiqueta.append(entrada)

        metrics = {
            "declares_language": bool(_HTML_LANG.search(html)),
            "image_count": len(imagenes),
            "images_without_alt": len(sin_alt),
            "form_inputs": len(entradas),
            "inputs_without_label": len(sin_etiqueta),
            "has_h1": bool(_TAG_H1.search(html)),
            "uses_semantic_html": bool(_SEMANTIC.search(html)),
            "coverage": "comprobaciones estaticas del HTML, no sustituyen a axe-core",
        }

        findings: list[FindingData] = []
        if not metrics["declares_language"]:
            findings.append(
                FindingData(
                    type="accessibility",
                    severity="medium",
                    title="La pagina no declara su idioma",
                    description=(
                        "Falta el atributo lang en la etiqueta html. Los lectores de pantalla no "
                        "saben en que idioma pronunciar el contenido."
                    ),
                    url=fetched.url,
                    recommendation='Anade lang="es" (o el idioma que corresponda) al elemento html.',
                )
            )
        if sin_alt:
            findings.append(
                FindingData(
                    type="accessibility",
                    severity="medium",
                    title=f"Hay {len(sin_alt)} imagenes sin texto alternativo",
                    description=(
                        "Quien use un lector de pantalla no sabra que muestran esas imagenes. Si "
                        "son decorativas, deben llevar alt vacio para que se omitan."
                    ),
                    url=fetched.url,
                    recommendation='Anade alt descriptivo, o alt="" si la imagen es decorativa.',
                )
            )
        if sin_etiqueta:
            findings.append(
                FindingData(
                    type="accessibility",
                    severity="high",
                    title=f"Hay {len(sin_etiqueta)} campos de formulario sin etiqueta",
                    description=(
                        "Un campo sin etiqueta asociada es imposible de interpretar con un lector "
                        "de pantalla: la persona no sabe que se le esta pidiendo."
                    ),
                    url=fetched.url,
                    recommendation="Asocia cada campo con un <label for> o un aria-label.",
                )
            )
        if not metrics["has_h1"]:
            findings.append(
                FindingData(
                    type="accessibility",
                    severity="low",
                    title="La pagina no tiene encabezado principal",
                    description=(
                        "Sin un h1, quien navega por encabezados no encuentra el punto de entrada "
                        "al contenido."
                    ),
                    url=fetched.url,
                    recommendation="Anade un h1 que describa el contenido de la pagina.",
                )
            )

        return AnalyzerResult(dimension="accessibility", metrics=metrics, findings=findings)


class SeoCompatibilityAnalyzer:
    """SEO y compatibilidad movil: ambos se leen del mismo HTML."""

    name = "url_seo"

    def analyze(self, fetched: FetchResult) -> AnalyzerResult:
        html = fetched.text
        titulo = _TAG_TITLE.search(html)
        texto_titulo = (titulo.group(1).strip() if titulo else "")

        metrics = {
            "has_title": bool(texto_titulo),
            "title_length": len(texto_titulo),
            "has_meta_description": bool(_META_DESC.search(html)),
            "has_viewport": bool(_META_VIEWPORT.search(html)),
            "uses_semantic_html": bool(_SEMANTIC.search(html)),
        }

        findings: list[FindingData] = []
        if not texto_titulo:
            findings.append(
                FindingData(
                    type="seo",
                    severity="medium",
                    title="La pagina no tiene titulo",
                    description=(
                        "Sin etiqueta title, los buscadores y las pestanas del navegador muestran "
                        "la URL en su lugar."
                    ),
                    url=fetched.url,
                    recommendation="Anade un <title> descriptivo de unos 50 a 60 caracteres.",
                )
            )
        if not metrics["has_meta_description"]:
            findings.append(
                FindingData(
                    type="seo",
                    severity="low",
                    title="Falta la meta descripcion",
                    description=(
                        "Los buscadores mostraran un fragmento arbitrario de la pagina en lugar de "
                        "un resumen escrito a proposito."
                    ),
                    url=fetched.url,
                    recommendation="Anade una meta description de unos 150 caracteres.",
                )
            )
        if not metrics["has_viewport"]:
            findings.append(
                FindingData(
                    type="compatibility",
                    severity="high",
                    title="La pagina no se adapta a moviles",
                    description=(
                        "Sin la etiqueta viewport, los moviles muestran la version de escritorio "
                        "reducida: el texto queda diminuto y hay que ampliar para leer."
                    ),
                    url=fetched.url,
                    recommendation='Anade <meta name="viewport" content="width=device-width, initial-scale=1">.',
                )
            )

        return AnalyzerResult(dimension="compatibility", metrics=metrics, findings=findings)
