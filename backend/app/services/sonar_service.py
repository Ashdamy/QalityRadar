"""Lectura de metricas de un proyecto publico de SonarCloud.

QalitiRadar no ejecuta nada: solo pide a SonarCloud los resultados que ya
calculo. Por eso las reglas son estrechas:

- Siempre al mismo host, fijo en el codigo. El usuario solo aporta la clave
  del proyecto, nunca una URL: no hay forma de hacernos llamar a otro sitio.
- La clave se valida con una expresion estricta antes de salir de aqui, y
  viaja como parametro de consulta (httpx la codifica).
- Sin token: solo proyectos publicos. Un proyecto privado responde 401/403 y
  se le dice al usuario, en vez de pedirle credenciales.
- Tiempo maximo corto y sin seguir redirecciones.
- De la respuesta solo se guardan las metricas de la lista, y solo si son
  numeros.
"""

import re

import httpx

SONARCLOUD_URL = "https://sonarcloud.io/api/measures/component"
TIMEOUT_SEGUNDOS = 10

# `ncloc` (lineas de codigo) no se muestra: hace falta para pasar la
# complejidad cognitiva total a densidad, que es lo que se puede comparar
# entre proyectos de distinto tamano.
METRICAS = (
    "coverage",
    "duplicated_lines_density",
    "sqale_index",
    "sqale_rating",
    "cognitive_complexity",
    "ncloc",
)

# Letras, digitos, guion, guion bajo, punto y dos puntos, como las claves de
# SonarCloud ("organizacion_proyecto"). Empieza por letra o digito y no pasa
# de 400 caracteres, el limite de SonarCloud.
_CLAVE_VALIDA = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,399}")


class SonarError(Exception):
    """Fallo con un mensaje en espanol que se le puede ensenar al usuario."""

    def __init__(self, mensaje: str, status_code: int):
        super().__init__(mensaje)
        self.mensaje = mensaje
        self.status_code = status_code


def clave_valida(clave: str) -> bool:
    # Solo digitos no es una clave de SonarCloud (la exige con alguna letra).
    return bool(_CLAVE_VALIDA.fullmatch(clave)) and not clave.isdigit()


def obtener_metricas(clave: str) -> dict[str, float]:
    """Metricas numericas del proyecto, por nombre. Lanza SonarError si no se puede."""
    if not clave_valida(clave):
        raise SonarError(
            "La clave del proyecto no es válida. Cópiala tal cual de SonarCloud "
            "(por ejemplo, mi-organizacion_mi-proyecto).",
            422,
        )

    try:
        respuesta = httpx.get(
            SONARCLOUD_URL,
            params={"component": clave, "metricKeys": ",".join(METRICAS)},
            timeout=TIMEOUT_SEGUNDOS,
            follow_redirects=False,
        )
    except httpx.TimeoutException as exc:
        raise SonarError("SonarCloud tardó demasiado en responder. Prueba de nuevo en un rato.", 504) from exc
    except httpx.RequestError as exc:
        raise SonarError("No se pudo contactar con SonarCloud. Prueba de nuevo en un rato.", 502) from exc

    codigo = respuesta.status_code
    if codigo == 404:
        raise SonarError(
            "SonarCloud no encuentra ese proyecto. Revisa la clave: aparece en la "
            "página del proyecto en sonarcloud.io.",
            404,
        )
    if codigo in (401, 403):
        raise SonarError(
            "Ese proyecto es privado en SonarCloud. QalitiRadar solo puede leer "
            "proyectos públicos.",
            403,
        )
    if codigo == 429:
        raise SonarError(
            "SonarCloud está limitando las peticiones ahora mismo. Prueba de nuevo en unos minutos.",
            503,
        )
    if codigo != 200:
        raise SonarError("SonarCloud no está disponible ahora mismo. Prueba de nuevo en un rato.", 502)

    try:
        medidas = respuesta.json()["component"]["measures"]
    except (ValueError, KeyError, TypeError) as exc:
        raise SonarError("SonarCloud devolvió una respuesta inesperada.", 502) from exc

    metricas: dict[str, float] = {}
    for medida in medidas if isinstance(medidas, list) else []:
        nombre = medida.get("metric") if isinstance(medida, dict) else None
        if nombre not in METRICAS:
            continue
        try:
            metricas[nombre] = float(medida.get("value"))
        except (TypeError, ValueError):
            continue

    if not metricas.keys() - {"ncloc"}:
        raise SonarError(
            "El proyecto existe, pero SonarCloud todavía no tiene esas métricas. "
            "¿Ya terminó algún análisis en SonarCloud?",
            422,
        )
    return metricas
