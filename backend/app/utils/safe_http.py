"""Cliente HTTP con proteccion contra SSRF en cada salto.

Validar solo la URL inicial no sirve: un dominio publico puede responder con
una redireccion a `http://169.254.169.254/` y obtendriamos las credenciales
de la maquina. Por eso aqui las redirecciones se siguen a mano, validando
cada destino antes de conectar.

Tambien se acota lo que se descarga: un servidor hostil puede responder con
un flujo infinito y agotar la memoria del worker.
"""

from dataclasses import dataclass, field

import httpx

from app.utils.url_validation import MAX_REDIRECTS, UnsafeUrlError, validate_public_url

REQUEST_TIMEOUT_SECONDS = 30
# Suficiente para cualquier documento HTML razonable. Mas alla, se corta.
MAX_RESPONSE_BYTES = 3_000_000

USER_AGENT = "QalitiRadar/1.0 (+https://github.com/Ashdamy/QalitiRadar)"


@dataclass
class FetchResult:
    url: str
    status_code: int
    headers: dict[str, str]
    text: str
    elapsed_seconds: float
    content_bytes: int
    redirect_chain: list[str] = field(default_factory=list)
    truncated: bool = False


def fetch_public_page(url: str) -> FetchResult:
    """Descarga una pagina publica validando cada redireccion.

    Lanza UnsafeUrlError si algun salto apunta a una direccion interna, y
    httpx.RequestError si el servidor no responde.
    """
    cadena: list[str] = []
    actual = url

    # `follow_redirects=False` es deliberado: httpx seguiria las redirecciones
    # por su cuenta, sin darnos ocasion de validar cada destino.
    with httpx.Client(follow_redirects=False, timeout=REQUEST_TIMEOUT_SECONDS) as client:
        for _ in range(MAX_REDIRECTS + 1):
            validate_public_url(actual)  # antes de cada conexion, sin excepcion
            cadena.append(actual)

            respuesta = client.get(actual, headers={"User-Agent": USER_AGENT})

            if respuesta.is_redirect:
                destino = respuesta.headers.get("location")
                if not destino:
                    break
                actual = str(httpx.URL(actual).join(destino))
                continue

            cuerpo, truncado = _read_capped(respuesta)
            return FetchResult(
                url=actual,
                status_code=respuesta.status_code,
                headers={k.lower(): v for k, v in respuesta.headers.items()},
                text=cuerpo,
                elapsed_seconds=respuesta.elapsed.total_seconds(),
                content_bytes=len(respuesta.content),
                redirect_chain=cadena,
                truncated=truncado,
            )

    raise UnsafeUrlError(f"la direccion encadena mas de {MAX_REDIRECTS} redirecciones")


def _read_capped(respuesta: httpx.Response) -> tuple[str, bool]:
    contenido = respuesta.content
    truncado = len(contenido) > MAX_RESPONSE_BYTES
    if truncado:
        contenido = contenido[:MAX_RESPONSE_BYTES]
    codificacion = respuesta.encoding or "utf-8"
    return contenido.decode(codificacion, errors="replace"), truncado
