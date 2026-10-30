"""Proxy de salida del navegador aislado: la defensa principal contra SSRF.

Corre DENTRO del contenedor del navegador (se copia tal cual a la imagen, por
eso solo usa la libreria estandar). Chromium sale obligatoriamente por aqui
(`--proxy-server`, sin excepciones para localhost), asi que cada conexion
que abra la pagina —el documento, sus imagenes, scripts, iframes,
redirecciones— pasa por `abrir_destino`:

1. Se resuelve el DNS **una sola vez**.
2. Se comprueban **todas** las IP devueltas: publicas y enrutables, y el
   puerto no es de un servicio interno.
3. Se conecta **a esa misma IP**, sin volver a resolver. Un dominio que
   responda una IP publica a la comprobacion y una privada a la conexion (DNS
   rebinding) no tiene segunda resolucion que aprovechar.

Lo bloqueado recibe un 403 y queda en el registro (stderr).

Los rangos y puertos son los mismos que `app/utils/url_validation.py`; una
prueba comprueba que no se separen.
"""

import asyncio
import ipaddress
import socket
import sys
from collections.abc import Awaitable, Callable

# Copia de url_validation.BLOCKED_PORTS (este archivo no puede importar `app`).
PUERTOS_BLOQUEADOS = {22, 23, 25, 445, 3306, 5432, 5433, 6379, 9200, 11211, 27017}
TIEMPO_DE_CONEXION = 10
MAX_CABECERAS = 64 * 1024


class Bloqueado(Exception):
    """El destino no es publico o no se pudo comprobar."""


def ip_publica(ip: str) -> bool:
    """Misma regla que url_validation: `is_global` excluye privadas, loopback,
    enlace local (169.254.169.254 de metadatos incluida), reservadas y la
    fd00::/8 de metadatos IPv6 de AWS."""
    try:
        direccion = ipaddress.ip_address(ip)
    except ValueError:
        return False
    if isinstance(direccion, ipaddress.IPv6Address) and direccion.ipv4_mapped:
        direccion = direccion.ipv4_mapped
    return direccion.is_global and not direccion.is_multicast


def resolver_sistema(host: str, puerto: int) -> list[str]:
    infos = socket.getaddrinfo(host, puerto, proto=socket.IPPROTO_TCP)
    return [info[4][0] for info in infos]


Conectar = Callable[[str, int], Awaitable[tuple[asyncio.StreamReader, asyncio.StreamWriter]]]


async def _conectar_tcp(ip: str, puerto: int):
    return await asyncio.wait_for(asyncio.open_connection(ip, puerto), TIEMPO_DE_CONEXION)


def elegir_ip(host: str, puerto: int, resolver=resolver_sistema) -> str:
    """Resuelve una vez y devuelve la IP a la que conectar, o lanza Bloqueado."""
    if puerto in PUERTOS_BLOQUEADOS or not 0 < puerto < 65536:
        raise Bloqueado(f"puerto {puerto} bloqueado")
    host = host.strip("[]")
    try:
        ipaddress.ip_address(host)
        candidatas = [host]  # Un literal no se resuelve.
    except ValueError:
        try:
            candidatas = resolver(host, puerto)
        except OSError as exc:
            raise Bloqueado(f"no se pudo resolver {host}") from exc
    if not candidatas:
        raise Bloqueado(f"{host} no resuelve a ninguna IP")
    # Todas, no solo la primera: si una es interna, el dominio no es de fiar.
    for ip in candidatas:
        if not ip_publica(ip):
            raise Bloqueado(f"{host} apunta a {ip}, que no es una IP publica")
    return candidatas[0]


async def abrir_destino(host: str, puerto: int, *, resolver=resolver_sistema, conectar: Conectar = _conectar_tcp):
    ip = elegir_ip(host, puerto, resolver)
    # La IP que se acaba de comprobar, nunca el nombre: sin segunda resolucion.
    return await conectar(ip, puerto)


def _separar_destino(destino: str, puerto_por_defecto: int) -> tuple[str, int]:
    if destino.startswith("["):  # IPv6 literal: [::1]:443
        host, _, resto = destino[1:].partition("]")
        return host, int(resto[1:]) if resto.startswith(":") else puerto_por_defecto
    host, sep, puerto = destino.rpartition(":")
    if sep and puerto.isdigit():
        return host, int(puerto)
    return destino, puerto_por_defecto


async def _tubo(origen: asyncio.StreamReader, destino: asyncio.StreamWriter) -> None:
    try:
        while datos := await origen.read(65536):
            destino.write(datos)
            await destino.drain()
    except (ConnectionError, asyncio.CancelledError):
        pass
    finally:
        destino.close()


class Proxy:
    def __init__(self, *, resolver=resolver_sistema, conectar: Conectar = _conectar_tcp):
        self.resolver = resolver
        self.conectar = conectar
        self.bloqueados: list[str] = []

    async def atender(self, lector: asyncio.StreamReader, escritor: asyncio.StreamWriter) -> None:
        try:
            cabecera = await asyncio.wait_for(lector.readuntil(b"\r\n\r\n"), TIEMPO_DE_CONEXION)
        except (asyncio.IncompleteReadError, asyncio.LimitOverrunError, asyncio.TimeoutError):
            escritor.close()
            return
        lineas = cabecera.decode("latin-1").split("\r\n")
        try:
            metodo, objetivo, version = lineas[0].split(" ", 2)
        except ValueError:
            return await self._responder(escritor, 400)

        try:
            if metodo.upper() == "CONNECT":
                host, puerto = _separar_destino(objetivo, 443)
                remoto_l, remoto_e = await abrir_destino(host, puerto, resolver=self.resolver, conectar=self.conectar)
                escritor.write(b"HTTP/1.1 200 Connection established\r\n\r\n")
                await escritor.drain()
            elif objetivo.lower().startswith("http://"):
                resto = objetivo[7:]
                destino, _, ruta = resto.partition("/")
                host, puerto = _separar_destino(destino, 80)
                remoto_l, remoto_e = await abrir_destino(host, puerto, resolver=self.resolver, conectar=self.conectar)
                # Peticion reenviada en forma de origen y sin cabeceras de proxy.
                otras = [linea for linea in lineas[1:] if linea and not linea.lower().startswith("proxy-")]
                remoto_e.write(("\r\n".join([f"{metodo} /{ruta} {version}", *otras]) + "\r\n\r\n").encode("latin-1"))
                await remoto_e.drain()
            else:
                return await self._responder(escritor, 400)
        except Bloqueado as exc:
            self.bloqueados.append(str(exc))
            print(f"bloqueado: {exc}", file=sys.stderr, flush=True)
            return await self._responder(escritor, 403)
        except (OSError, asyncio.TimeoutError):
            return await self._responder(escritor, 502)

        await asyncio.gather(_tubo(lector, remoto_e), _tubo(remoto_l, escritor))

    @staticmethod
    async def _responder(escritor: asyncio.StreamWriter, codigo: int) -> None:
        texto = {400: "Bad Request", 403: "Forbidden", 502: "Bad Gateway"}[codigo]
        escritor.write(f"HTTP/1.1 {codigo} {texto}\r\nContent-Length: 0\r\nConnection: close\r\n\r\n".encode())
        try:
            await escritor.drain()
        finally:
            escritor.close()


async def servir(host: str = "127.0.0.1", puerto: int = 3128, proxy: Proxy | None = None) -> asyncio.Server:
    proxy = proxy or Proxy()
    return await asyncio.start_server(proxy.atender, host, puerto, limit=MAX_CABECERAS)


if __name__ == "__main__":
    async def _main() -> None:
        servidor = await servir()
        async with servidor:
            await servidor.serve_forever()

    asyncio.run(_main())
