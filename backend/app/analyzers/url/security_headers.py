"""Seguridad de una aplicacion desplegada.

Sub-caracteristicas de "Security" en ISO/IEC 25010 observables desde las
cabeceras HTTP y el HTML:

- Confidencialidad: el trafico va cifrado (HTTPS, HSTS) y las cookies de
  sesion no se pueden robar (Secure, HttpOnly, SameSite).
- Integridad: el contenido no se puede alterar ni suplantar (CSP, SRI,
  ausencia de contenido mixto, aislamiento de origen).
- Resistencia: el sitio no se puede incrustar ni abusar desde otro origen
  (X-Frame-Options, CORS restrictivo).

Cada hallazgo explica el ataque que deja de estar mitigado: decir "falta
X-Frame-Options" no significa nada para quien no conoce la cabecera.
"""

import re
from urllib.parse import urlparse

from app.analyzers.base import AnalyzerResult, FindingData
from app.utils.safe_http import FetchResult

# Duracion minima recomendada de HSTS: seis meses.
MIN_HSTS_MAX_AGE = 15768000

# Directivas de CSP que cierran vias de ataque concretas.
IMPORTANT_CSP_DIRECTIVES = ("default-src", "object-src", "base-uri", "frame-ancestors", "form-action")

_SCRIPT_EXTERNO = re.compile(r"<script\b[^>]*\bsrc\s*=\s*[\"']([^\"']+)[\"'][^>]*>", re.I)
_LINK_ESTILO = re.compile(r"<link\b[^>]*rel\s*=\s*[\"']stylesheet[\"'][^>]*>", re.I)
_ATTR_INTEGRITY = re.compile(r"\bintegrity\s*=", re.I)
_RECURSO_HTTP = re.compile(r"(?:src|href)\s*=\s*[\"']http://[^\"']+", re.I)
_FORM_ACTION_HTTP = re.compile(r"<form\b[^>]*\baction\s*=\s*[\"']http://", re.I)
_INPUT_PASSWORD = re.compile(r"<input\b[^>]*type\s*=\s*[\"']password[\"'][^>]*>", re.I)
_FORM = re.compile(r"<form\b[^>]*>", re.I)


class SecurityHeadersAnalyzer:
    name = "security_headers"

    def analyze(self, fetched: FetchResult) -> AnalyzerResult:
        headers = fetched.headers
        html = fetched.text
        es_https = urlparse(fetched.url).scheme == "https"
        empezo_en_http = any(u.startswith("http://") for u in fetched.redirect_chain)

        hsts = headers.get("strict-transport-security")
        csp = headers.get("content-security-policy") or headers.get(
            "content-security-policy-report-only"
        )
        csp_lower = (csp or "").lower()
        frame_options = headers.get("x-frame-options")
        cors = headers.get("access-control-allow-origin")
        cookies = _cookies(headers)

        # -- Integridad de recursos externos (SRI) ---------------------------
        scripts_externos = [s for s in _SCRIPT_EXTERNO.findall(html) if _es_externo(s, fetched.url)]
        scripts_sin_sri = [
            m.group(0)
            for m in _SCRIPT_EXTERNO.finditer(html)
            if _es_externo(m.group(1), fetched.url) and not _ATTR_INTEGRITY.search(m.group(0))
        ]

        # -- Contenido mixto --------------------------------------------------
        recursos_http = _RECURSO_HTTP.findall(html) if es_https else []

        metrics = {
            "uses_https": es_https,
            "redirects_http_to_https": empezo_en_http and es_https,
            "has_hsts": bool(hsts),
            "hsts_max_age": _hsts_max_age(hsts),
            "hsts_includes_subdomains": bool(hsts and "includesubdomains" in hsts.lower()),
            "has_csp": bool(csp),
            "csp_is_report_only": bool(
                not headers.get("content-security-policy")
                and headers.get("content-security-policy-report-only")
            ),
            "csp_allows_unsafe_inline": "unsafe-inline" in csp_lower,
            "csp_allows_unsafe_eval": "unsafe-eval" in csp_lower,
            "csp_directives_present": [d for d in IMPORTANT_CSP_DIRECTIVES if d in csp_lower],
            "has_x_frame_options": bool(frame_options),
            "has_frame_ancestors": "frame-ancestors" in csp_lower,
            "has_x_content_type_options": bool(headers.get("x-content-type-options")),
            "has_referrer_policy": bool(headers.get("referrer-policy")),
            "has_permissions_policy": bool(headers.get("permissions-policy")),
            "has_coop": bool(headers.get("cross-origin-opener-policy")),
            "has_corp": bool(headers.get("cross-origin-resource-policy")),
            "cors_allows_any_origin": cors == "*",
            "cookie_count": len(cookies),
            "cookies_without_secure": sum(1 for c in cookies if "secure" not in c.lower()),
            "cookies_without_httponly": sum(1 for c in cookies if "httponly" not in c.lower()),
            "cookies_without_samesite": sum(1 for c in cookies if "samesite" not in c.lower()),
            "external_script_count": len(scripts_externos),
            "external_scripts_without_sri": len(scripts_sin_sri),
            "mixed_content_count": len(recursos_http),
            "form_posts_over_http": bool(_FORM_ACTION_HTTP.search(html)),
            "has_password_field": bool(_INPUT_PASSWORD.search(html)),
            "leaks_server_version": bool(
                headers.get("server") and any(c.isdigit() for c in headers["server"])
            ),
            "leaks_powered_by": bool(headers.get("x-powered-by")),
            "status_code": fetched.status_code,
        }

        findings = self._findings(fetched, metrics, headers)
        return AnalyzerResult(dimension="security", metrics=metrics, findings=findings)

    def _findings(self, fetched: FetchResult, m: dict, headers: dict) -> list[FindingData]:
        url = fetched.url
        findings: list[FindingData] = []

        if not m["uses_https"]:
            findings.append(
                FindingData(
                    type="security", severity="critical", url=url,
                    title="El sitio no usa HTTPS",
                    description=(
                        "El tráfico viaja sin cifrar. Cualquiera en la misma red (una wifi pública, "
                        "el proveedor de internet) puede leer y modificar lo que se envía, incluidas "
                        "contraseñas y sesiones."
                    ),
                    recommendation="Instala un certificado TLS y redirige todo el tráfico a HTTPS.",
                )
            )
        else:
            if not m["has_hsts"]:
                findings.append(
                    FindingData(
                        type="security", severity="medium", url=url,
                        title="Falta la cabecera HSTS",
                        description=(
                            "Sin HSTS, la primera visita puede interceptarse y degradarse a HTTP "
                            "antes de que el navegador sepa que el sitio exige cifrado."
                        ),
                        recommendation="Añade Strict-Transport-Security con un max-age de al menos seis meses.",
                    )
                )
            elif (m["hsts_max_age"] or 0) < MIN_HSTS_MAX_AGE:
                findings.append(
                    FindingData(
                        type="security", severity="low", url=url,
                        title="El HSTS tiene una duración corta",
                        description=(
                            f"max-age es {m['hsts_max_age']} segundos. Lo recomendado son al menos "
                            "seis meses para que la protección sea efectiva."
                        ),
                        recommendation="Sube max-age a 15768000 o más.",
                    )
                )

        if m["mixed_content_count"]:
            findings.append(
                FindingData(
                    type="security", severity="high", url=url,
                    title=f"Hay {m['mixed_content_count']} recursos cargados por HTTP en una página HTTPS",
                    description=(
                        "Contenido mixto: aunque la página va cifrada, esos recursos viajan en claro. "
                        "Un atacante en la red puede sustituirlos, y los navegadores modernos los "
                        "bloquean, así que además pueden no cargarse."
                    ),
                    recommendation="Cambia esas direcciones a https:// o usa rutas relativas.",
                )
            )

        if not m["has_csp"]:
            findings.append(
                FindingData(
                    type="security", severity="high", url=url,
                    title="Falta la política de seguridad de contenido (CSP)",
                    description=(
                        "Sin CSP, si alguien logra inyectar un script en la página el navegador lo "
                        "ejecutará sin objeción. Es la defensa principal contra el XSS."
                    ),
                    recommendation="Define un Content-Security-Policy que limite los orígenes permitidos.",
                )
            )
        else:
            if m["csp_is_report_only"]:
                findings.append(
                    FindingData(
                        type="security", severity="medium", url=url,
                        title="La CSP está en modo solo informe",
                        description=(
                            "Content-Security-Policy-Report-Only registra las violaciones pero no "
                            "bloquea nada. Sirve para probar la política, no para protegerse."
                        ),
                        recommendation="Cuando la política esté afinada, pásala a Content-Security-Policy.",
                    )
                )
            if m["csp_allows_unsafe_inline"]:
                findings.append(
                    FindingData(
                        type="security", severity="medium", url=url,
                        title="La CSP permite scripts en línea",
                        description=(
                            "La política incluye 'unsafe-inline', que reabre justo el agujero que la "
                            "CSP debería cerrar: un script inyectado en el HTML se ejecutaría igual."
                        ),
                        recommendation="Sustituye 'unsafe-inline' por nonces o hashes.",
                    )
                )
            if m["csp_allows_unsafe_eval"]:
                findings.append(
                    FindingData(
                        type="security", severity="medium", url=url,
                        title="La CSP permite evaluar código dinámico",
                        description=(
                            "'unsafe-eval' deja que el navegador ejecute cadenas de texto como código. "
                            "Si alguna llega desde el usuario, se convierte en ejecución arbitraria."
                        ),
                        recommendation="Elimina 'unsafe-eval' y sustituye eval por alternativas seguras.",
                    )
                )
            faltantes = [d for d in IMPORTANT_CSP_DIRECTIVES if d not in m["csp_directives_present"]]
            if len(faltantes) >= 3:
                findings.append(
                    FindingData(
                        type="security", severity="low", url=url,
                        title="La CSP deja fuera directivas importantes",
                        description=(
                            f"No define {', '.join(faltantes)}. Sin default-src, cualquier tipo de "
                            "recurso no cubierto queda sin restricción; sin base-uri, un atacante "
                            "puede reescribir las rutas relativas de la página."
                        ),
                        recommendation="Amplía la política con esas directivas.",
                    )
                )

        if not m["has_x_frame_options"] and not m["has_frame_ancestors"]:
            findings.append(
                FindingData(
                    type="security", severity="medium", url=url,
                    title="El sitio puede incrustarse en páginas ajenas",
                    description=(
                        "Sin X-Frame-Options ni frame-ancestors, un atacante puede cargar tu sitio "
                        "dentro de una página suya e inducir a tus usuarios a pulsar donde no "
                        "quieren (clickjacking)."
                    ),
                    recommendation="Añade X-Frame-Options: DENY o frame-ancestors 'none' en la CSP.",
                )
            )

        # -- Cookies ----------------------------------------------------------
        if m["cookie_count"]:
            if m["cookies_without_httponly"]:
                findings.append(
                    FindingData(
                        type="security", severity="high", url=url,
                        title=f"{m['cookies_without_httponly']} de {m['cookie_count']} cookies son accesibles desde JavaScript",
                        description=(
                            "Sin el atributo HttpOnly, cualquier script de la página puede leer la "
                            "cookie. Si alguien consigue inyectar código, se lleva la sesión."
                        ),
                        recommendation="Marca las cookies de sesión como HttpOnly.",
                    )
                )
            if m["uses_https"] and m["cookies_without_secure"]:
                findings.append(
                    FindingData(
                        type="security", severity="medium", url=url,
                        title=f"{m['cookies_without_secure']} cookies pueden enviarse sin cifrar",
                        description=(
                            "Sin el atributo Secure, el navegador enviaría la cookie también por HTTP, "
                            "donde puede interceptarse."
                        ),
                        recommendation="Marca todas las cookies como Secure.",
                    )
                )
            if m["cookies_without_samesite"]:
                findings.append(
                    FindingData(
                        type="security", severity="medium", url=url,
                        title=f"{m['cookies_without_samesite']} cookies sin política SameSite",
                        description=(
                            "SameSite impide que la cookie se envíe en peticiones originadas por otro "
                            "sitio, que es la base de los ataques CSRF."
                        ),
                        recommendation="Añade SameSite=Lax (o Strict) a las cookies.",
                    )
                )

        if m["external_scripts_without_sri"]:
            findings.append(
                FindingData(
                    type="security", severity="medium", url=url,
                    title=f"{m['external_scripts_without_sri']} scripts externos sin verificación de integridad",
                    description=(
                        "Se cargan scripts de otros dominios sin atributo integrity. Si ese servidor "
                        "es comprometido, el código alterado se ejecuta en tu sitio sin que nada lo "
                        "detecte."
                    ),
                    recommendation="Añade integrity y crossorigin a los scripts de terceros.",
                )
            )

        if m["cors_allows_any_origin"]:
            findings.append(
                FindingData(
                    type="security", severity="medium", url=url,
                    title="La respuesta permite peticiones desde cualquier origen",
                    description=(
                        "Access-Control-Allow-Origin es '*'. Cualquier web puede leer las respuestas "
                        "de este servidor desde el navegador de tus usuarios."
                    ),
                    recommendation="Restringe el origen permitido a los dominios que lo necesiten.",
                )
            )

        if m["form_posts_over_http"]:
            findings.append(
                FindingData(
                    type="security", severity="critical", url=url,
                    title="Hay un formulario que envía datos por HTTP",
                    description=(
                        "El formulario declara una acción sin cifrar. Todo lo que el usuario escriba "
                        "(incluidas contraseñas) viajará en claro."
                    ),
                    recommendation="Cambia la acción del formulario a https://.",
                )
            )

        if not m["has_x_content_type_options"]:
            findings.append(
                FindingData(
                    type="security", severity="low", url=url,
                    title="Falta X-Content-Type-Options",
                    description=(
                        "Sin esta cabecera el navegador puede intentar adivinar el tipo de un archivo "
                        "e interpretar como script algo que no lo era."
                    ),
                    recommendation="Añade X-Content-Type-Options: nosniff.",
                )
            )

        if m["leaks_server_version"] or m["leaks_powered_by"]:
            expuesto = ", ".join(
                v for v in (headers.get("server"), headers.get("x-powered-by")) if v
            )
            findings.append(
                FindingData(
                    type="security", severity="low", url=url,
                    title="El servidor revela su versión",
                    description=(
                        f"Las cabeceras anuncian: {expuesto}. Eso le indica a un atacante qué "
                        "vulnerabilidades conocidas probar primero."
                    ),
                    recommendation="Oculta las cabeceras Server y X-Powered-By.",
                )
            )

        return findings


def _cookies(headers: dict) -> list[str]:
    valor = headers.get("set-cookie")
    if not valor:
        return []
    # httpx colapsa varias Set-Cookie en una sola cadena separada por comas;
    # se separa por el patron "nombre=" que inicia cada cookie.
    return [c for c in re.split(r",(?=\s*[A-Za-z0-9_\-]+=)", valor) if c.strip()]


def _es_externo(src: str, pagina: str) -> bool:
    if src.startswith("//"):
        return True
    if not src.startswith("http"):
        return False
    return urlparse(src).netloc != urlparse(pagina).netloc


def _hsts_max_age(valor: str | None) -> int | None:
    if not valor:
        return None
    for parte in valor.split(";"):
        parte = parte.strip().lower()
        if parte.startswith("max-age="):
            try:
                return int(parte.split("=", 1)[1])
            except ValueError:
                return None
    return None
