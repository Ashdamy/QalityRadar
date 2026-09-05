"""Cliente HTTP con proteccion contra SSRF en cada salto.

Validar solo la URL inicial no sirve: un dominio publico puede responder con
una redireccion a `http://169.254.169.254/` y obtendriamos las credenciales
de la maquina. Por eso aqui las redirecciones se siguen a mano, validando
cada destino antes de conectar.

Y validar el nombre tampoco basta: entre la comprobacion y la conexion, el
mismo dominio puede resolver a otra IP. Por eso se conecta contra la IP que se
acaba de validar, no contra el nombre.

Tambien se acota lo que se descarga, leyendo por trozos: un servidor hostil
puede responder con un flujo infinito y agotar la memoria del worker.
"""

import time
from dataclasses import dataclass, field

import httpx

from app.utils.url_validation import (
    MAX_REDIRECTS,
    ResolvedTarget,
    UnsafeUrlError,
    validate_public_url,
)

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


def _peticion_fijada(url: str, objetivo: ResolvedTarget) -> tuple[httpx.URL, dict]:
    """Devuelve la URL apuntando a la IP validada, y las cabeceras que hacen
    falta para que el servidor y el certificado sigan siendo los del dominio.

    Sin esto queda una ventana entre validar y conectar: el atacante controla
    su propio DNS, responde una IP publica a la comprobacion y una interna a la
    conexion (ataque de "DNS rebinding"). Fijando la IP, la conexion va justo a
    donde se comprobo.

    `Host` mantiene el enrutado por dominio en el servidor y `sni_hostname`
    hace que TLS negocie y valide el certificado contra el dominio, no contra
    la IP: si se omitiera, cualquier sitio con HTTPS fallaria la verificacion.

    ponytail: se usa la primera IP validada. Si un dominio publica varias y esa
    no responde, no se prueban las demas; para eso habria que reintentar con el
    resto de `objetivo.ip_addresses`.
    """
    original = httpx.URL(url)
    return original.copy_with(host=objetivo.ip_addresses[0]), {
        "headers": {
            "User-Agent": USER_AGENT,
            # netloc trae ya el puerto cuando no es el estandar del esquema.
            "Host": original.netloc.decode("ascii"),
        },
        "extensions": {"sni_hostname": objetivo.hostname},
    }


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
            objetivo = validate_public_url(actual)  # antes de cada conexion, sin excepcion
            cadena.append(actual)

            url_fijada, extras = _peticion_fijada(actual, objetivo)
            comenzo = time.monotonic()
            # En streaming: hasta aqui solo han llegado las cabeceras, asi que
            # un cuerpo enorme todavia no se ha descargado.
            with client.stream("GET", url_fijada, **extras) as respuesta:
                if respuesta.is_redirect:
                    destino = respuesta.headers.get("location")
                    if not destino:
                        break
                    # Se resuelve contra la URL original, no contra la de la IP:
                    # una redireccion relativa debe quedarse en el dominio.
                    actual = str(httpx.URL(actual).join(destino))
                    continue

                cuerpo, leidos, truncado = _leer_con_tope(respuesta)
                return FetchResult(
                    url=actual,
                    status_code=respuesta.status_code,
                    headers={k.lower(): v for k, v in respuesta.headers.items()},
                    text=cuerpo,
                    elapsed_seconds=time.monotonic() - comenzo,
                    content_bytes=leidos,
                    redirect_chain=cadena,
                    truncated=truncado,
                )

    raise UnsafeUrlError(f"la direccion encadena mas de {MAX_REDIRECTS} redirecciones")


def _leer_con_tope(respuesta: httpx.Response) -> tuple[str, int, bool]:
    """Lee por trozos y corta en el tope.

    Antes se leia `respuesta.content`, que descarga el cuerpo entero y solo
    despues recortaba: el tope existia, pero la memoria ya se habia gastado.
    Un servidor hostil respondiendo un flujo sin fin tumbaba el worker.
    """
    trozos: list[bytes] = []
    leidos = 0
    truncado = False

    for trozo in respuesta.iter_bytes():
        trozos.append(trozo)
        leidos += len(trozo)
        if leidos >= MAX_RESPONSE_BYTES:
            truncado = True
            break

    contenido = b"".join(trozos)[:MAX_RESPONSE_BYTES]
    codificacion = respuesta.encoding or "utf-8"
    return contenido.decode(codificacion, errors="replace"), min(leidos, MAX_RESPONSE_BYTES), truncado
