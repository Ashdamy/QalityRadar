"""Validacion de URLs contra SSRF (Server-Side Request Forgery).

Analizar una URL que nos da un desconocido significa que nuestro servidor
hace peticiones a donde el usuario diga. Sin control, alguien puede pedirnos
que consultemos:

- `http://169.254.169.254/` — el servicio de metadatos de AWS, GCP y Azure,
  que devuelve credenciales de la maquina.
- `http://localhost:5433/` — nuestra propia base de datos.
- `http://10.0.0.5/` — cualquier maquina de la red interna.

Y le devolvemos el resultado. Por eso aqui NO basta con mirar el texto de la
URL: hay que resolver el DNS y comprobar la IP real, porque un dominio
publico puede apuntar a una direccion privada (ataque de "DNS rebinding"), y
hay que repetir la comprobacion en CADA redireccion, porque una URL publica
puede redirigir a una interna.
"""

import ipaddress
import socket
from dataclasses import dataclass
from urllib.parse import urlparse

ALLOWED_SCHEMES = {"http", "https"}

# Puertos que no tienen sentido para analizar una web y que suelen ser
# servicios internos.
BLOCKED_PORTS = {22, 23, 25, 445, 3306, 5432, 5433, 6379, 9200, 11211, 27017}

MAX_REDIRECTS = 5


class UnsafeUrlError(ValueError):
    """La URL apunta a un destino que no debemos consultar."""


@dataclass(frozen=True)
class ResolvedTarget:
    url: str
    hostname: str
    port: int
    ip_addresses: tuple[str, ...]


def _is_public_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """Solo las direcciones enrutables de internet son aceptables.

    `is_global` cubre de una vez privadas, loopback, link-local (incluido el
    169.254.169.254 de metadatos), multicast y reservadas.
    """
    return ip.is_global and not ip.is_multicast


def validate_public_url(url: str) -> ResolvedTarget:
    """Comprueba que la URL es publica y segura de consultar.

    Lanza UnsafeUrlError con un motivo concreto si no lo es.
    """
    parsed = urlparse(url.strip())

    if parsed.scheme.lower() not in ALLOWED_SCHEMES:
        raise UnsafeUrlError(
            f"solo se admiten direcciones http o https, no {parsed.scheme or 'una direccion sin esquema'}"
        )
    if not parsed.hostname:
        raise UnsafeUrlError("la direccion no tiene un nombre de host valido")

    hostname = parsed.hostname
    port = parsed.port or (443 if parsed.scheme.lower() == "https" else 80)
    if port in BLOCKED_PORTS:
        raise UnsafeUrlError(f"el puerto {port} corresponde a un servicio interno y no se analiza")

    # Un literal IP se comprueba directamente; un nombre se resuelve primero.
    try:
        literal = ipaddress.ip_address(hostname)
    except ValueError:
        literal = None

    if literal is not None:
        addresses = [literal]
    else:
        try:
            infos = socket.getaddrinfo(hostname, port, proto=socket.IPPROTO_TCP)
        except socket.gaierror as exc:
            raise UnsafeUrlError(f"no se pudo resolver el dominio {hostname}") from exc
        addresses = []
        for info in infos:
            try:
                addresses.append(ipaddress.ip_address(info[4][0]))
            except ValueError:
                continue
        if not addresses:
            raise UnsafeUrlError(f"no se pudo resolver el dominio {hostname}")

    # TODAS las direcciones deben ser publicas: si el dominio resuelve a varias
    # y una es interna, un reintento podria acabar en la interna.
    for ip in addresses:
        if not _is_public_ip(ip):
            raise UnsafeUrlError(
                f"la direccion apunta a {ip}, que es una IP interna o reservada y no se analiza"
            )

    return ResolvedTarget(
        url=url.strip(),
        hostname=hostname,
        port=port,
        ip_addresses=tuple(str(ip) for ip in addresses),
    )


def validate_redirect_chain(urls: list[str]) -> None:
    """Valida cada salto de una cadena de redirecciones.

    Una URL publica puede redirigir a una interna; comprobar solo la primera
    dejaria abierta justo la via que esto pretende cerrar.
    """
    if len(urls) > MAX_REDIRECTS + 1:
        raise UnsafeUrlError(f"la direccion encadena mas de {MAX_REDIRECTS} redirecciones")
    for url in urls:
        validate_public_url(url)
