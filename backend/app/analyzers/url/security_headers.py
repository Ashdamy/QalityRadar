"""Seguridad de una aplicacion desplegada: HTTPS y cabeceras de proteccion.

Cada cabecera que falta corresponde a un ataque concreto que deja de estar
mitigado, y asi se explica en el hallazgo: decir "falta X-Frame-Options" no
significa nada para quien no conoce la cabecera; decir que su sitio puede
incrustarse en una pagina ajena para enganar a sus usuarios, si.
"""

from urllib.parse import urlparse

from app.analyzers.base import AnalyzerResult, FindingData
from app.utils.safe_http import FetchResult


class SecurityHeadersAnalyzer:
    name = "security_headers"

    def analyze(self, fetched: FetchResult) -> AnalyzerResult:
        headers = fetched.headers
        es_https = urlparse(fetched.url).scheme == "https"
        # Si la cadena empezo en http y acabo en https, el sitio redirige bien.
        empezo_en_http = any(u.startswith("http://") for u in fetched.redirect_chain)
        redirige_a_https = empezo_en_http and es_https

        hsts = headers.get("strict-transport-security")
        csp = headers.get("content-security-policy")
        frame_options = headers.get("x-frame-options")
        content_type_options = headers.get("x-content-type-options")
        referrer = headers.get("referrer-policy")
        permissions = headers.get("permissions-policy")
        server = headers.get("server")
        powered_by = headers.get("x-powered-by")

        metrics = {
            "uses_https": es_https,
            "redirects_http_to_https": redirige_a_https,
            "has_hsts": bool(hsts),
            "hsts_max_age": _hsts_max_age(hsts),
            "has_csp": bool(csp),
            "csp_allows_unsafe_inline": bool(csp and "unsafe-inline" in csp.lower()),
            "has_x_frame_options": bool(frame_options),
            "has_x_content_type_options": bool(content_type_options),
            "has_referrer_policy": bool(referrer),
            "has_permissions_policy": bool(permissions),
            "leaks_server_version": bool(server and any(c.isdigit() for c in server)),
            "leaks_powered_by": bool(powered_by),
            "status_code": fetched.status_code,
        }

        findings: list[FindingData] = []

        if not es_https:
            findings.append(
                FindingData(
                    type="security",
                    severity="critical",
                    title="El sitio no usa HTTPS",
                    description=(
                        "El trafico viaja sin cifrar. Cualquiera en la misma red (una wifi "
                        "publica, el proveedor de internet) puede leer y modificar lo que se "
                        "envia, incluidas contrasenas y sesiones."
                    ),
                    url=fetched.url,
                    recommendation="Instala un certificado TLS y redirige todo el trafico a HTTPS.",
                )
            )
        else:
            if not hsts:
                findings.append(
                    FindingData(
                        type="security",
                        severity="medium",
                        title="Falta la cabecera HSTS",
                        description=(
                            "Sin HSTS, la primera visita puede interceptarse y degradarse a HTTP "
                            "antes de que el navegador sepa que el sitio exige cifrado."
                        ),
                        url=fetched.url,
                        recommendation="Anade Strict-Transport-Security con un max-age de al menos 6 meses.",
                    )
                )
            elif (metrics["hsts_max_age"] or 0) < 15768000:
                findings.append(
                    FindingData(
                        type="security",
                        severity="low",
                        title="El HSTS tiene una duracion corta",
                        description=(
                            f"max-age es {metrics['hsts_max_age']} segundos. Lo recomendado son al "
                            "menos seis meses para que la proteccion sea efectiva."
                        ),
                        url=fetched.url,
                        recommendation="Sube max-age a 15768000 o mas.",
                    )
                )

        if not csp:
            findings.append(
                FindingData(
                    type="security",
                    severity="high",
                    title="Falta la politica de seguridad de contenido (CSP)",
                    description=(
                        "Sin CSP, si alguien logra inyectar un script en la pagina el navegador lo "
                        "ejecutara sin objecion. Es la defensa principal contra el XSS."
                    ),
                    url=fetched.url,
                    recommendation="Define un Content-Security-Policy que limite los origenes permitidos.",
                )
            )
        elif metrics["csp_allows_unsafe_inline"]:
            findings.append(
                FindingData(
                    type="security",
                    severity="medium",
                    title="La CSP permite scripts en linea",
                    description=(
                        "La politica incluye 'unsafe-inline', que reabre justo el agujero que la "
                        "CSP deberia cerrar: un script inyectado en el HTML se ejecutaria igual."
                    ),
                    url=fetched.url,
                    recommendation="Sustituye 'unsafe-inline' por nonces o hashes.",
                )
            )

        if not frame_options and not (csp and "frame-ancestors" in csp.lower()):
            findings.append(
                FindingData(
                    type="security",
                    severity="medium",
                    title="El sitio puede incrustarse en paginas ajenas",
                    description=(
                        "Sin X-Frame-Options ni frame-ancestors, un atacante puede cargar tu sitio "
                        "dentro de una pagina suya e inducir a tus usuarios a pulsar donde no "
                        "quieren (clickjacking)."
                    ),
                    url=fetched.url,
                    recommendation="Anade X-Frame-Options: DENY o frame-ancestors 'none' en la CSP.",
                )
            )

        if not content_type_options:
            findings.append(
                FindingData(
                    type="security",
                    severity="low",
                    title="Falta X-Content-Type-Options",
                    description=(
                        "Sin esta cabecera el navegador puede intentar adivinar el tipo de un "
                        "archivo e interpretar como script algo que no lo era."
                    ),
                    url=fetched.url,
                    recommendation="Anade X-Content-Type-Options: nosniff.",
                )
            )

        if metrics["leaks_server_version"] or metrics["leaks_powered_by"]:
            expuesto = ", ".join(v for v in (server, powered_by) if v)
            findings.append(
                FindingData(
                    type="security",
                    severity="low",
                    title="El servidor revela su version",
                    description=(
                        f"Las cabeceras anuncian: {expuesto}. Eso le indica a un atacante que "
                        "vulnerabilidades conocidas probar primero."
                    ),
                    url=fetched.url,
                    recommendation="Oculta las cabeceras Server y X-Powered-By.",
                )
            )

        return AnalyzerResult(dimension="security", metrics=metrics, findings=findings)


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
