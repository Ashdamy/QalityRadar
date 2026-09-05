"""Tests de la defensa contra SSRF.

Cada caso bloqueado aqui corresponde a un ataque real: si alguno pasara,
nuestro servidor consultaria recursos internos por orden de un desconocido y
le devolveria el resultado.
"""

import ipaddress

import pytest

from app.utils.safe_http import MAX_RESPONSE_BYTES, _leer_con_tope, _peticion_fijada
from app.utils.url_validation import (
    ResolvedTarget,
    UnsafeUrlError,
    validate_public_url,
    validate_redirect_chain,
)


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com",
        "https://example.com/ruta?x=1",
        "http://example.com:8080/",
    ],
)
def test_accepts_ordinary_public_urls(url):
    resultado = validate_public_url(url)
    assert resultado.hostname == "example.com"
    assert resultado.ip_addresses


@pytest.mark.parametrize(
    ("url", "motivo"),
    [
        ("http://169.254.169.254/latest/meta-data/", "metadatos de la nube"),
        ("http://127.0.0.1:8000/", "loopback"),
        ("http://localhost:8000/", "loopback por nombre"),
        ("http://10.0.0.5/", "red privada clase A"),
        ("http://192.168.1.1/", "red privada domestica"),
        ("http://172.16.0.1/", "red privada clase B"),
        ("http://[::1]/", "loopback IPv6"),
        ("http://0.0.0.0/", "direccion sin especificar"),
    ],
)
def test_blocks_internal_addresses(url, motivo):
    with pytest.raises(UnsafeUrlError):
        validate_public_url(url)


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "gopher://example.com/",
        "ftp://example.com/",
        "javascript:alert(1)",
        "example.com",  # sin esquema
    ],
)
def test_blocks_non_http_schemes(url):
    with pytest.raises(UnsafeUrlError):
        validate_public_url(url)


@pytest.mark.parametrize("puerto", [22, 3306, 5432, 6379, 27017])
def test_blocks_internal_service_ports(puerto):
    with pytest.raises(UnsafeUrlError, match="servicio interno"):
        validate_public_url(f"http://example.com:{puerto}/")


def test_blocks_a_domain_that_resolves_to_a_private_address(monkeypatch):
    """El caso mas sutil: dominio publico que apunta a una IP interna.

    Mirar solo el texto de la URL no lo detecta; hay que resolver el DNS.
    """
    import app.utils.url_validation as modulo

    def fake_getaddrinfo(host, port, **kwargs):
        return [(2, 1, 6, "", ("10.0.0.99", port))]

    monkeypatch.setattr(modulo.socket, "getaddrinfo", fake_getaddrinfo)

    with pytest.raises(UnsafeUrlError, match="interna o reservada"):
        validate_public_url("https://parece-publico.example.com/")


def test_blocks_when_any_resolved_address_is_private(monkeypatch):
    """Si un dominio resuelve a varias IPs y una es interna, se rechaza.

    Aceptarlo dejaria que un reintento acabase en la direccion interna.
    """
    import app.utils.url_validation as modulo

    def fake_getaddrinfo(host, port, **kwargs):
        return [
            (2, 1, 6, "", ("93.184.216.34", port)),  # publica
            (2, 1, 6, "", ("127.0.0.1", port)),      # interna
        ]

    monkeypatch.setattr(modulo.socket, "getaddrinfo", fake_getaddrinfo)

    with pytest.raises(UnsafeUrlError):
        validate_public_url("https://mixto.example.com/")


def test_reports_an_unresolvable_domain_clearly(monkeypatch):
    import socket as socket_module

    import app.utils.url_validation as modulo

    def fake_getaddrinfo(host, port, **kwargs):
        raise socket_module.gaierror("sin resolucion")

    monkeypatch.setattr(modulo.socket, "getaddrinfo", fake_getaddrinfo)

    with pytest.raises(UnsafeUrlError, match="no se pudo resolver"):
        validate_public_url("https://no-existe-jamas.example/")


def test_every_hop_of_a_redirect_chain_is_validated():
    """Una URL publica puede redirigir a una interna."""
    with pytest.raises(UnsafeUrlError):
        validate_redirect_chain(["https://example.com/", "http://169.254.169.254/"])


def test_a_clean_redirect_chain_is_accepted():
    validate_redirect_chain(["https://example.com/", "https://example.com/final"])


def test_too_many_redirects_are_rejected():
    cadena = [f"https://example.com/{i}" for i in range(10)]
    with pytest.raises(UnsafeUrlError, match="redirecciones"):
        validate_redirect_chain(cadena)


def test_the_metadata_address_is_recognised_as_non_global():
    # Comprobacion directa de la propiedad en la que se apoya la defensa.
    assert not ipaddress.ip_address("169.254.169.254").is_global


# --------------------------------------------------------------------------
# Descarga acotada y conexion contra la IP validada
# --------------------------------------------------------------------------


class _RespuestaSinFin:
    """Un servidor hostil que responde un flujo que no termina."""

    encoding = "utf-8"

    def __init__(self) -> None:
        self.trozos_servidos = 0

    def iter_bytes(self):
        while True:
            self.trozos_servidos += 1
            yield b"x" * 65536


def test_un_flujo_infinito_se_corta_en_el_tope():
    """El tope existia, pero se aplicaba tras leer `respuesta.content`: la
    memoria ya se habia gastado antes de recortar."""
    respuesta = _RespuestaSinFin()
    texto, leidos, truncado = _leer_con_tope(respuesta)

    assert truncado
    assert leidos == MAX_RESPONSE_BYTES
    assert len(texto) == MAX_RESPONSE_BYTES
    # Y se dejo de leer: no se descargo el flujo entero para luego recortarlo.
    assert respuesta.trozos_servidos < MAX_RESPONSE_BYTES // 65536 + 2


class _RespuestaCorta:
    encoding = "utf-8"

    def iter_bytes(self):
        yield b"<html>ok</html>"


def test_una_pagina_normal_no_se_marca_truncada():
    texto, leidos, truncado = _leer_con_tope(_RespuestaCorta())
    assert (texto, leidos, truncado) == ("<html>ok</html>", 15, False)


def test_se_conecta_a_la_ip_validada_y_no_al_nombre():
    """Entre validar el nombre y conectar, el atacante puede hacer que su
    dominio resuelva a una IP interna (ataque de "DNS rebinding"). Fijando la
    IP, la conexion va justo a donde se comprobo."""
    objetivo = ResolvedTarget(
        url="https://ejemplo.test/pagina",
        hostname="ejemplo.test",
        port=443,
        ip_addresses=("93.184.215.14",),
    )

    url, extras = _peticion_fijada("https://ejemplo.test/pagina", objetivo)

    assert url.host == "93.184.215.14"
    assert url.path == "/pagina"
    # El servidor sigue viendo el dominio, y TLS valida el certificado contra
    # el dominio y no contra la IP.
    assert extras["headers"]["Host"] == "ejemplo.test"
    assert extras["extensions"]["sni_hostname"] == "ejemplo.test"


def test_un_puerto_no_estandar_viaja_en_la_cabecera_host():
    objetivo = ResolvedTarget(
        url="http://ejemplo.test:8080/",
        hostname="ejemplo.test",
        port=8080,
        ip_addresses=("93.184.215.14",),
    )

    _, extras = _peticion_fijada("http://ejemplo.test:8080/", objetivo)
    assert extras["headers"]["Host"] == "ejemplo.test:8080"
