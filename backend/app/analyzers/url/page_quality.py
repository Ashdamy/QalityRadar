"""Rendimiento, accesibilidad, usabilidad y compatibilidad de una pagina.

Alcance, dicho sin adornos: Lighthouse y axe-core necesitan un navegador sin
interfaz (unos 400 MB de contenedor) y llegan mas adelante. Todo lo de aqui
se obtiene del HTML y de las cabeceras. Es mucho mas que "existe o no existe"
—se miden recursos bloqueantes, jerarquia de encabezados, zoom bloqueado,
imagenes responsivas, etiquetas obsoletas— pero no sustituye a un analisis
con renderizado real: no se puede medir contraste de color efectivo, tiempo
hasta que la pagina es usable ni el arbol de accesibilidad final.
"""

import re
from collections import Counter
from urllib.parse import urlparse

from app.analyzers.base import AnalyzerResult, FindingData
from app.utils.safe_http import FetchResult

# --- Umbrales ---------------------------------------------------------------
SLOW_RESPONSE_SECONDS = 2.0
LARGE_HTML_BYTES = 250_000
MANY_BLOCKING_RESOURCES = 5
MANY_THIRD_PARTY_ORIGINS = 5

# --- Expresiones ------------------------------------------------------------
_HEAD = re.compile(r"<head\b.*?</head>", re.I | re.S)
_SCRIPT_TAG = re.compile(r"<script\b[^>]*>", re.I)
_SCRIPT_SRC = re.compile(r"<script\b[^>]*\bsrc\s*=\s*[\"']([^\"']+)[\"'][^>]*>", re.I)
_LINK_TAG = re.compile(r"<link\b[^>]*>", re.I)
_IMG_TAG = re.compile(r"<img\b[^>]*>", re.I)
_IFRAME_TAG = re.compile(r"<iframe\b[^>]*>", re.I)
_INPUT_TAG = re.compile(r"<input\b[^>]*>", re.I)
_TABLE_TAG = re.compile(r"<table\b.*?</table>", re.I | re.S)
_A_TAG = re.compile(r"<a\b[^>]*>(.*?)</a>", re.I | re.S)
_HEADING = re.compile(r"<h([1-6])\b", re.I)
_ATTR = lambda nombre: re.compile(rf"\b{nombre}\s*=\s*[\"']?([^\"'\s>]*)", re.I)  # noqa: E731
_ATTR_PRESENTE = lambda nombre: re.compile(rf"\b{nombre}\s*=", re.I)  # noqa: E731
# defer y async son atributos booleanos: se escriben sin "=". Exigir el signo
# igual marcaria como bloqueantes scripts que si estan optimizados.
_ATTR_BOOLEANO = lambda nombre: re.compile(rf"\b{nombre}\b", re.I)  # noqa: E731
_ID_ATTR = re.compile(r"\bid\s*=\s*[\"']([^\"']+)[\"']", re.I)
_LABEL_FOR = re.compile(r"<label\b[^>]*\bfor\s*=\s*[\"']([^\"']+)[\"']", re.I)
_INPUT_SIN_ETIQUETA = re.compile(r"type\s*=\s*[\"']?(hidden|submit|button|image|reset)", re.I)
_ARIA_LABEL = re.compile(r"\b(aria-label|aria-labelledby|title)\s*=", re.I)
_TITLE = re.compile(r"<title[^>]*>(.*?)</title>", re.I | re.S)
_META = lambda n: re.compile(rf'<meta[^>]+name\s*=\s*[\"\']{n}[\"\'][^>]*>', re.I)  # noqa: E731
_META_VIEWPORT_CONTENT = re.compile(
    r'<meta[^>]+name\s*=\s*[\"\']viewport[\"\'][^>]*content\s*=\s*[\"\']([^\"\']*)', re.I
)
_LINK_REL = lambda r: re.compile(rf'<link[^>]+rel\s*=\s*[\"\'][^\"\']*{r}[^\"\']*[\"\']', re.I)  # noqa: E731
_HTML_LANG = re.compile(r"<html\b[^>]*\blang\s*=", re.I)
_DOCTYPE = re.compile(r"^\s*<!doctype\s+html\s*>", re.I)
_CHARSET = re.compile(r"<meta[^>]+charset\s*=", re.I)
_SEMANTIC = re.compile(r"<(main|nav|header|footer|article|section|aside)\b", re.I)
_LANDMARK_MAIN = re.compile(r"<main\b|role\s*=\s*[\"']main[\"']", re.I)
_DEPRECATED = re.compile(r"<(center|font|marquee|blink|frameset|frame|big|strike|tt)\b", re.I)
_AUTOPLAY = re.compile(r"<(video|audio)\b[^>]*\bautoplay\b", re.I)
_TEXTO_GENERICO = re.compile(
    r"^(aqu[ií]|clic|click|click here|pincha aqu[ií]|leer m[áa]s|read more|m[áa]s|more|link|enlace|ver)$",
    re.I,
)
_ETIQUETAS = re.compile(r"<[^>]+>")


class PerformanceAnalyzer:
    """Eficiencia de desempeño: comportamiento temporal y uso de recursos."""

    name = "url_performance"

    def analyze(self, fetched: FetchResult) -> AnalyzerResult:
        html = fetched.text
        head = (_HEAD.search(html).group(0) if _HEAD.search(html) else "")

        # Recursos que bloquean el primer dibujado de la pagina.
        estilos_bloqueantes = [
            t for t in _LINK_TAG.findall(head) if _LINK_REL("stylesheet").search(t)
        ]
        scripts_head = _SCRIPT_TAG.findall(head)
        scripts_bloqueantes = [
            t
            for t in scripts_head
            if "src=" in t.lower()
            and not _ATTR_BOOLEANO("defer").search(t)
            and not _ATTR_BOOLEANO("async").search(t)
        ]

        # Origenes de terceros: cada uno anade resolucion DNS y handshake TLS.
        propio = urlparse(fetched.url).netloc
        origenes = {
            urlparse(src if src.startswith("http") else f"https:{src}").netloc
            for src in _SCRIPT_SRC.findall(html)
            if src.startswith(("http", "//"))
        }
        terceros = {o for o in origenes if o and o != propio}

        imagenes = _IMG_TAG.findall(html)
        sin_lazy = [
            i for i in imagenes if not re.search(r'loading\s*=\s*["\']?lazy', i, re.I)
        ]
        sin_dimensiones = [
            i
            for i in imagenes
            if not (_ATTR_PRESENTE("width").search(i) and _ATTR_PRESENTE("height").search(i))
        ]

        encoding = fetched.headers.get("content-encoding", "")
        cache_control = fetched.headers.get("cache-control", "")

        metrics = {
            "response_seconds": round(fetched.elapsed_seconds, 3),
            "html_bytes": fetched.content_bytes,
            "uses_compression": bool(encoding and encoding != "identity"),
            "compression_algorithm": encoding or None,
            "has_cache_control": bool(cache_control),
            "has_etag": bool(fetched.headers.get("etag")),
            "redirect_count": max(0, len(fetched.redirect_chain) - 1),
            "render_blocking_styles": len(estilos_bloqueantes),
            "render_blocking_scripts": len(scripts_bloqueantes),
            "external_script_count": len(_SCRIPT_SRC.findall(html)),
            "third_party_origin_count": len(terceros),
            "image_count": len(imagenes),
            "images_without_lazy_loading": len(sin_lazy),
            "images_without_dimensions": len(sin_dimensiones),
            "has_resource_hints": bool(
                _LINK_REL("preconnect").search(html) or _LINK_REL("dns-prefetch").search(html)
            ),
            "measurement_scope": "tiempo de respuesta del servidor, no de carga completa",
        }

        findings: list[FindingData] = []
        url = fetched.url

        if fetched.elapsed_seconds > SLOW_RESPONSE_SECONDS:
            findings.append(FindingData(
                type="performance", severity="high", url=url,
                title=f"El servidor tarda {fetched.elapsed_seconds:.1f} s en responder",
                description=(
                    "Ese es el tiempo hasta el primer byte, antes siquiera de empezar a dibujar la "
                    "página. Por encima de dos segundos la mayoría de visitantes percibe el sitio "
                    "como lento."
                ),
                recommendation="Revisa consultas lentas, añade caché de servidor o una CDN.",
            ))
        if not metrics["uses_compression"]:
            findings.append(FindingData(
                type="performance", severity="medium", url=url,
                title="La respuesta no viaja comprimida",
                description=(
                    "Sin compresión gzip o brotli el HTML se envía entero. Comprimirlo suele reducir "
                    "su tamaño entre un 60 y un 80 por ciento."
                ),
                recommendation="Activa la compresión en el servidor o en la CDN.",
            ))
        if not cache_control:
            findings.append(FindingData(
                type="performance", severity="low", url=url,
                title="No hay cabeceras de caché",
                description="Sin Cache-Control, cada visita vuelve a descargarlo todo aunque nada haya cambiado.",
                recommendation="Define Cache-Control según el tipo de recurso.",
            ))
        if metrics["render_blocking_scripts"]:
            findings.append(FindingData(
                type="performance", severity="high", url=url,
                title=f"Hay {metrics['render_blocking_scripts']} scripts que bloquean el dibujado",
                description=(
                    "Son scripts en la cabecera sin defer ni async: el navegador detiene el análisis "
                    "del HTML hasta descargarlos y ejecutarlos, así que la página queda en blanco "
                    "mientras tanto."
                ),
                recommendation="Añade defer (o async si el orden no importa) a esos scripts.",
            ))
        if metrics["render_blocking_styles"] > MANY_BLOCKING_RESOURCES:
            findings.append(FindingData(
                type="performance", severity="medium", url=url,
                title=f"Hay {metrics['render_blocking_styles']} hojas de estilo en la cabecera",
                description=(
                    "Cada hoja de estilo bloquea el primer dibujado hasta que se descarga. Muchas "
                    "peticiones separadas retrasan el momento en que se ve algo."
                ),
                recommendation="Une las hojas de estilo o incorpora el CSS crítico en la página.",
            ))
        if len(terceros) > MANY_THIRD_PARTY_ORIGINS:
            findings.append(FindingData(
                type="performance", severity="medium", url=url,
                title=f"Se cargan scripts de {len(terceros)} dominios de terceros",
                description=(
                    "Cada dominio adicional obliga a resolver DNS y negociar TLS por separado, y su "
                    "rendimiento queda fuera de tu control."
                ),
                recommendation="Reduce los terceros o al menos añade preconnect a los imprescindibles.",
            ))
        if len(sin_lazy) > 5:
            findings.append(FindingData(
                type="performance", severity="medium", url=url,
                title=f"{len(sin_lazy)} imágenes se cargan de inmediato",
                description=(
                    "Sin loading=\"lazy\", el navegador descarga también las imágenes que están fuera "
                    "de la pantalla, compitiendo con lo que el usuario sí está viendo."
                ),
                recommendation='Añade loading="lazy" a las imágenes que no aparecen al abrir la página.',
            ))
        if len(sin_dimensiones) > 3:
            findings.append(FindingData(
                type="performance", severity="medium", url=url,
                title=f"{len(sin_dimensiones)} imágenes sin dimensiones declaradas",
                description=(
                    "Sin width y height, el navegador no reserva su espacio y el contenido salta "
                    "cuando cargan. Es la causa más común de que se pulse un botón equivocado."
                ),
                recommendation="Declara width y height (o aspect-ratio) en cada imagen.",
            ))
        if fetched.content_bytes > LARGE_HTML_BYTES:
            findings.append(FindingData(
                type="performance", severity="medium", url=url,
                title=f"El HTML pesa {fetched.content_bytes // 1024} KB",
                description=(
                    "Un documento tan grande tarda en descargarse y en procesarse, sobre todo en "
                    "móviles con conexión lenta."
                ),
                recommendation="Separa el contenido que pueda cargarse después.",
            ))
        if metrics["redirect_count"] >= 2:
            findings.append(FindingData(
                type="performance", severity="low", url=url,
                title=f"Hay {metrics['redirect_count']} redirecciones antes de llegar",
                description="Cada redirección añade una ida y vuelta completa a la red.",
                recommendation="Apunta directamente al destino final.",
            ))

        return AnalyzerResult(dimension="performance", metrics=metrics, findings=findings)


class AccessibilityAnalyzer:
    """Accesibilidad: que el sitio pueda usarlo cualquiera."""

    name = "url_accessibility"

    def analyze(self, fetched: FetchResult) -> AnalyzerResult:
        html = fetched.text
        url = fetched.url

        imagenes = _IMG_TAG.findall(html)
        sin_alt = [i for i in imagenes if not _ATTR_PRESENTE("alt").search(i)]

        entradas = [i for i in _INPUT_TAG.findall(html) if not _INPUT_SIN_ETIQUETA.search(i)]
        ids_con_label = set(_LABEL_FOR.findall(html))
        sin_etiqueta = [
            e
            for e in entradas
            if not _ARIA_LABEL.search(e)
            and not (
                (m := _ID_ATTR.search(e)) and m.group(1) in ids_con_label
            )
        ]

        # Jerarquia de encabezados: saltarse niveles rompe la navegacion por
        # encabezados de un lector de pantalla.
        niveles = [int(n) for n in _HEADING.findall(html)]
        saltos = sum(
            1 for anterior, actual in zip(niveles, niveles[1:]) if actual - anterior > 1
        )

        # Zoom bloqueado: impide ampliar a quien lo necesita para leer.
        viewport = _META_VIEWPORT_CONTENT.search(html)
        contenido_viewport = (viewport.group(1).lower() if viewport else "")
        bloquea_zoom = "user-scalable=no" in contenido_viewport.replace(" ", "") or bool(
            re.search(r"maximum-scale\s*=\s*1(\.0)?\b", contenido_viewport)
        )

        # tabindex positivo: altera el orden natural de tabulacion.
        tabindex_positivos = [
            v for v in _ATTR("tabindex").findall(html) if v.strip().lstrip("+").isdigit() and int(v) > 0
        ]

        ids = _ID_ATTR.findall(html)
        duplicados = [i for i, n in Counter(ids).items() if n > 1]

        iframes = _IFRAME_TAG.findall(html)
        iframes_sin_titulo = [f for f in iframes if not _ATTR_PRESENTE("title").search(f)]

        enlaces_genericos = [
            texto
            for _, texto in ((m, _ETIQUETAS.sub("", m).strip()) for m in _A_TAG.findall(html))
            if _TEXTO_GENERICO.match(texto)
        ]

        tablas = _TABLE_TAG.findall(html)
        tablas_sin_cabecera = [t for t in tablas if "<th" not in t.lower()]

        metrics = {
            "declares_language": bool(_HTML_LANG.search(html)),
            "image_count": len(imagenes),
            "images_without_alt": len(sin_alt),
            "form_inputs": len(entradas),
            "inputs_without_label": len(sin_etiqueta),
            "has_h1": 1 in niveles,
            "h1_count": niveles.count(1),
            "heading_level_skips": saltos,
            "uses_semantic_html": bool(_SEMANTIC.search(html)),
            "has_main_landmark": bool(_LANDMARK_MAIN.search(html)),
            "blocks_zoom": bloquea_zoom,
            "positive_tabindex_count": len(tabindex_positivos),
            "duplicate_id_count": len(duplicados),
            "iframe_count": len(iframes),
            "iframes_without_title": len(iframes_sin_titulo),
            "generic_link_text_count": len(enlaces_genericos),
            "tables_without_headers": len(tablas_sin_cabecera),
            "has_autoplay_media": bool(_AUTOPLAY.search(html)),
            "coverage_scope": "comprobaciones estáticas del HTML; no sustituyen a axe-core",
        }

        findings: list[FindingData] = []
        if not metrics["declares_language"]:
            findings.append(FindingData(
                type="accessibility", severity="medium", url=url,
                title="La página no declara su idioma",
                description=(
                    "Falta el atributo lang en la etiqueta html. Los lectores de pantalla no saben "
                    "en qué idioma pronunciar el contenido."
                ),
                recommendation='Añade lang="es" (o el idioma que corresponda) al elemento html.',
            ))
        if bloquea_zoom:
            findings.append(FindingData(
                type="accessibility", severity="high", url=url,
                title="La página impide ampliar el contenido",
                description=(
                    "El viewport bloquea el zoom. Quien necesite ampliar para leer —por baja visión "
                    "o simplemente por un texto pequeño— no puede hacerlo."
                ),
                recommendation="Quita user-scalable=no y maximum-scale del meta viewport.",
            ))
        if sin_alt:
            findings.append(FindingData(
                type="accessibility", severity="medium", url=url,
                title=f"Hay {len(sin_alt)} imágenes sin texto alternativo",
                description=(
                    "Quien use un lector de pantalla no sabrá qué muestran esas imágenes. Si son "
                    'decorativas, deben llevar alt="" para que se omitan.'
                ),
                recommendation='Añade alt descriptivo, o alt="" si la imagen es decorativa.',
            ))
        if sin_etiqueta:
            findings.append(FindingData(
                type="accessibility", severity="high", url=url,
                title=f"Hay {len(sin_etiqueta)} campos de formulario sin etiqueta",
                description=(
                    "Un campo sin etiqueta asociada es imposible de interpretar con un lector de "
                    "pantalla: la persona no sabe qué se le está pidiendo."
                ),
                recommendation="Asocia cada campo con un <label for> o un aria-label.",
            ))
        if not metrics["has_h1"]:
            findings.append(FindingData(
                type="accessibility", severity="medium", url=url,
                title="La página no tiene encabezado principal",
                description=(
                    "Sin un h1, quien navega por encabezados no encuentra el punto de entrada al "
                    "contenido."
                ),
                recommendation="Añade un h1 que describa el contenido de la página.",
            ))
        elif metrics["h1_count"] > 1:
            findings.append(FindingData(
                type="accessibility", severity="low", url=url,
                title=f"Hay {metrics['h1_count']} encabezados principales",
                description=(
                    "Varios h1 diluyen la estructura: deja de estar claro cuál es el tema de la "
                    "página."
                ),
                recommendation="Deja un único h1 y baja el resto a h2.",
            ))
        if saltos:
            findings.append(FindingData(
                type="accessibility", severity="low", url=url,
                title=f"La jerarquía de encabezados se salta {saltos} niveles",
                description=(
                    "Pasar de h2 a h4, por ejemplo, hace que quien navega por encabezados crea que "
                    "se ha perdido una sección."
                ),
                recommendation="Usa los niveles de encabezado en orden, sin saltos.",
            ))
        if duplicados:
            findings.append(FindingData(
                type="accessibility", severity="medium", url=url,
                title=f"Hay {len(duplicados)} identificadores duplicados en el HTML",
                description=(
                    "Un id debe ser único. Cuando se repite, las asociaciones de etiquetas de "
                    "formulario y las referencias ARIA apuntan al elemento equivocado."
                ),
                recommendation="Haz único cada atributo id.",
            ))
        if iframes_sin_titulo:
            findings.append(FindingData(
                type="accessibility", severity="medium", url=url,
                title=f"Hay {len(iframes_sin_titulo)} iframes sin título",
                description=(
                    "Un lector de pantalla anuncia el iframe sin poder decir qué contiene, así que "
                    "la persona no sabe si merece la pena entrar."
                ),
                recommendation="Añade un atributo title descriptivo a cada iframe.",
            ))
        if tabindex_positivos:
            findings.append(FindingData(
                type="accessibility", severity="low", url=url,
                title=f"Hay {len(tabindex_positivos)} elementos con tabindex positivo",
                description=(
                    "Un tabindex mayor que cero altera el orden natural de tabulación y suele dejar "
                    "el foco saltando de forma impredecible."
                ),
                recommendation="Usa tabindex=\"0\" y ordena los elementos en el HTML.",
            ))
        if len(enlaces_genericos) > 2:
            findings.append(FindingData(
                type="accessibility", severity="low", url=url,
                title=f"Hay {len(enlaces_genericos)} enlaces con texto poco descriptivo",
                description=(
                    'Textos como "aquí" o "leer más" no dicen nada fuera de contexto, y los lectores '
                    "de pantalla permiten listar los enlaces sueltos."
                ),
                recommendation="Escribe textos de enlace que describan su destino.",
            ))
        if tablas_sin_cabecera:
            findings.append(FindingData(
                type="accessibility", severity="low", url=url,
                title=f"Hay {len(tablas_sin_cabecera)} tablas sin celdas de cabecera",
                description=(
                    "Sin elementos th, un lector de pantalla no puede relacionar cada celda con lo "
                    "que significa."
                ),
                recommendation="Marca las cabeceras con <th> y su atributo scope.",
            ))
        if metrics["has_autoplay_media"]:
            findings.append(FindingData(
                type="accessibility", severity="medium", url=url,
                title="Hay contenido multimedia que se reproduce solo",
                description=(
                    "El audio o vídeo automático interfiere con los lectores de pantalla y resulta "
                    "especialmente molesto para personas con trastornos de atención."
                ),
                recommendation="Quita autoplay o al menos silencia y permite pausar.",
            ))

        return AnalyzerResult(dimension="accessibility", metrics=metrics, findings=findings)


class UsabilityAnalyzer:
    """Usabilidad: reconocibilidad y facilidad de uso."""

    name = "url_usability"

    def analyze(self, fetched: FetchResult) -> AnalyzerResult:
        html = fetched.text
        url = fetched.url
        titulo = _TITLE.search(html)
        texto_titulo = _ETIQUETAS.sub("", titulo.group(1)).strip() if titulo else ""
        descripcion = _META("description").search(html)

        metrics = {
            "has_title": bool(texto_titulo),
            "title_length": len(texto_titulo),
            "has_meta_description": bool(descripcion),
            "has_favicon": bool(_LINK_REL("icon").search(html)),
            "has_open_graph": bool(re.search(r'property\s*=\s*["\']og:', html, re.I)),
            "has_canonical": bool(_LINK_REL("canonical").search(html)),
            "has_theme_color": bool(_META("theme-color").search(html)),
            "has_main_landmark": bool(_LANDMARK_MAIN.search(html)),
            "uses_semantic_html": bool(_SEMANTIC.search(html)),
            "has_nav": bool(re.search(r"<nav\b", html, re.I)),
        }

        findings: list[FindingData] = []
        if not texto_titulo:
            findings.append(FindingData(
                type="seo", severity="medium", url=url,
                title="La página no tiene título",
                description=(
                    "Sin etiqueta title, los buscadores y las pestañas del navegador muestran la URL "
                    "en su lugar."
                ),
                recommendation="Añade un <title> descriptivo de unos 50 a 60 caracteres.",
            ))
        elif not 10 <= len(texto_titulo) <= 70:
            findings.append(FindingData(
                type="seo", severity="low", url=url,
                title=f"El título tiene {len(texto_titulo)} caracteres",
                description=(
                    "Los títulos muy cortos no informan y los muy largos se cortan en los resultados "
                    "de búsqueda y en las pestañas."
                ),
                recommendation="Ajusta el título a entre 10 y 70 caracteres.",
            ))
        if not metrics["has_meta_description"]:
            findings.append(FindingData(
                type="seo", severity="low", url=url,
                title="Falta la meta descripción",
                description=(
                    "Los buscadores mostrarán un fragmento arbitrario de la página en lugar de un "
                    "resumen escrito a propósito."
                ),
                recommendation="Añade una meta description de unos 150 caracteres.",
            ))
        if not metrics["has_favicon"]:
            findings.append(FindingData(
                type="usability", severity="low", url=url,
                title="La página no declara un icono",
                description=(
                    "Sin favicon, la pestaña y los marcadores muestran un icono genérico y el sitio "
                    "se vuelve difícil de localizar entre varias pestañas abiertas."
                ),
                recommendation='Añade <link rel="icon"> con el icono del sitio.',
            ))
        if not metrics["has_open_graph"]:
            findings.append(FindingData(
                type="usability", severity="low", url=url,
                title="No hay metadatos para compartir en redes",
                description=(
                    "Sin etiquetas Open Graph, al compartir el enlace en redes o mensajería aparece "
                    "una vista previa pobre o vacía."
                ),
                recommendation="Añade og:title, og:description y og:image.",
            ))
        if not metrics["has_main_landmark"]:
            findings.append(FindingData(
                type="usability", severity="low", url=url,
                title="No hay una región principal marcada",
                description=(
                    "Sin un elemento main, ni los lectores de pantalla ni el modo lectura saben qué "
                    "parte es el contenido y qué es adorno."
                ),
                recommendation="Envuelve el contenido principal en <main>.",
            ))

        return AnalyzerResult(dimension="usability", metrics=metrics, findings=findings)


class CompatibilityAnalyzer:
    """Compatibilidad: que funcione fuera de un navegador de escritorio."""

    name = "url_compatibility"

    def analyze(self, fetched: FetchResult) -> AnalyzerResult:
        html = fetched.text
        url = fetched.url
        imagenes = _IMG_TAG.findall(html)
        responsivas = [i for i in imagenes if _ATTR_PRESENTE("srcset").search(i)]
        obsoletas = sorted({m.lower() for m in _DEPRECATED.findall(html)})

        metrics = {
            "has_viewport": bool(_META_VIEWPORT_CONTENT.search(html)),
            "has_doctype": bool(_DOCTYPE.search(html)),
            "declares_charset": bool(_CHARSET.search(html)),
            "image_count": len(imagenes),
            "responsive_image_count": len(responsivas),
            "uses_picture_element": bool(re.search(r"<picture\b", html, re.I)),
            "deprecated_tags": obsoletas,
            "has_web_manifest": bool(_LINK_REL("manifest").search(html)),
            "declares_content_language": bool(fetched.headers.get("content-language"))
            or bool(_HTML_LANG.search(html)),
        }

        findings: list[FindingData] = []
        if not metrics["has_viewport"]:
            findings.append(FindingData(
                type="compatibility", severity="high", url=url,
                title="La página no se adapta a móviles",
                description=(
                    "Sin la etiqueta viewport, los móviles muestran la versión de escritorio reducida: "
                    "el texto queda diminuto y hay que ampliar para leer."
                ),
                recommendation='Añade <meta name="viewport" content="width=device-width, initial-scale=1">.',
            ))
        if not metrics["has_doctype"]:
            findings.append(FindingData(
                type="compatibility", severity="medium", url=url,
                title="Falta la declaración de tipo de documento",
                description=(
                    "Sin <!DOCTYPE html> el navegador entra en modo de compatibilidad antiguo, donde "
                    "el diseño se comporta de forma distinta y difícil de predecir."
                ),
                recommendation="Empieza el documento con <!DOCTYPE html>.",
            ))
        if not metrics["declares_charset"]:
            findings.append(FindingData(
                type="compatibility", severity="medium", url=url,
                title="La página no declara su codificación",
                description=(
                    "Sin declarar la codificación, los acentos y las eñes pueden mostrarse como "
                    "símbolos ilegibles según la configuración del navegador."
                ),
                recommendation='Añade <meta charset="utf-8"> al principio de la cabecera.',
            ))
        if obsoletas:
            findings.append(FindingData(
                type="compatibility", severity="low", url=url,
                title=f"Se usan etiquetas HTML obsoletas: {', '.join(obsoletas)}",
                description=(
                    "Son etiquetas retiradas del estándar. Los navegadores aún las toleran, pero su "
                    "comportamiento no está garantizado y pueden dejar de funcionar."
                ),
                recommendation="Sustitúyelas por CSS o por elementos actuales equivalentes.",
            ))
        if imagenes and len(responsivas) == 0 and len(imagenes) > 3 and not metrics["uses_picture_element"]:
            findings.append(FindingData(
                type="compatibility", severity="medium", url=url,
                title="Las imágenes no se adaptan al tamaño de pantalla",
                description=(
                    "Ninguna imagen usa srcset ni picture, así que un móvil descarga la misma versión "
                    "grande que un monitor, gastando datos y batería para nada."
                ),
                recommendation="Ofrece varios tamaños con srcset o con el elemento picture.",
            ))

        return AnalyzerResult(dimension="compatibility", metrics=metrics, findings=findings)


# Nombre anterior, conservado para no romper importaciones existentes.
SeoCompatibilityAnalyzer = CompatibilityAnalyzer
