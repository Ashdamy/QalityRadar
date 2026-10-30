"""Medicion en un navegador real (Lighthouse + axe-core), en un contenedor aislado.

Quien lanza el contenedor es el worker de Celery, que corre en el host (ver
docs/ARCHITECTURE.md §4.1), con `docker run` igual que el sandbox de
repositorios. No se monta `/var/run/docker.sock` en ningun contenedor.

El comando se arma solo con constantes: la imagen, la red y los limites
estan fijos aqui, y lo unico que viene del usuario es la URL, ya validada
contra SSRF, que va como argumento despues de `--`. Dentro del contenedor
Chromium sale por `proxy_navegador.py`, que vuelve a validar cada conexion.

La salida del contenedor es un JSON que se trata como dato hostil: solo se
aceptan los campos esperados, con el tipo esperado y acotados.
"""

import json
import subprocess
import uuid
from dataclasses import dataclass

from app.utils.url_validation import validate_public_url

# Limites del contenedor. Un navegador necesita bastante mas que el sandbox
# de repositorios (512 MB, media CPU).
FLAGS_NAVEGADOR: tuple[str, ...] = (
    "--rm",
    "--read-only",
    "--cap-drop=ALL",
    "--security-opt=no-new-privileges",
    "--memory=1g",
    "--memory-swap=1g",
    "--cpus=1",
    "--pids-limit=256",
    "--user", "65534:65534",
    "--tmpfs", "/tmp:rw,nosuid,nodev,size=256m",
)
TIEMPO_MAXIMO = 90
IMPACTOS = ("critical", "serious", "moderate", "minor")
MAX_VIOLACIONES = 100


class MedicionFallida(Exception):
    """No se pudo medir. El mensaje se le puede ensenar al usuario."""


@dataclass(frozen=True)
class Contenedor:
    imagen: str
    red: str


def comando(url: str, contenedor: Contenedor, nombre: str) -> list[str]:
    return [
        "docker", "run",
        *FLAGS_NAVEGADOR,
        "--name", nombre,
        # Red propia, sin nada nuestro dentro: ni base de datos ni Redis.
        "--network", contenedor.red,
        "--",
        contenedor.imagen,
        url,
    ]


def medir(url: str, contenedor: Contenedor, ejecutar=subprocess.run) -> dict:
    """Mide la URL y devuelve el resultado ya interpretado. Lanza MedicionFallida."""
    # Se revalida aqui aunque el analisis ya lo hizo: entre medio pudo
    # cambiar el DNS, y este es el ultimo punto antes de lanzar nada.
    validate_public_url(url)
    nombre = f"qr-navegador-{uuid.uuid4().hex[:12]}"
    try:
        resultado = ejecutar(
            comando(url, contenedor, nombre),
            capture_output=True, text=True, timeout=TIEMPO_MAXIMO, shell=False, check=False,
        )
    except subprocess.TimeoutExpired as exc:
        # `--rm` no basta si el proceso de docker muere por el timeout: el
        # contenedor seguiria vivo. Se mata por su nombre.
        ejecutar(["docker", "rm", "-f", nombre], capture_output=True, timeout=30, check=False)
        raise MedicionFallida("La medición en navegador tardó demasiado.") from exc
    except OSError as exc:
        raise MedicionFallida("El navegador aislado no está disponible en este servidor.") from exc

    if resultado.returncode != 0:
        raise MedicionFallida("El navegador aislado no pudo abrir la página.")
    return interpretar(resultado.stdout)


def _numero(valor, minimo: float = 0.0, maximo: float = 10**7) -> float | None:
    if isinstance(valor, bool) or not isinstance(valor, (int, float)):
        return None
    if valor != valor or not minimo <= valor <= maximo:  # NaN o fuera de rango
        return None
    return float(valor)


def interpretar(salida: str) -> dict:
    """Del JSON del contenedor, solo lo esperado. Lanza MedicionFallida si no vale."""
    lineas = [linea for linea in (salida or "").strip().splitlines() if linea.strip()]
    try:
        bruto = json.loads(lineas[-1]) if lineas else None
    except ValueError:
        bruto = None
    if not isinstance(bruto, dict):
        raise MedicionFallida("El navegador aislado devolvió una respuesta que no se entiende.")

    medicion: dict = {}
    for clave, maximo in (("lcp_ms", 600_000), ("tbt_ms", 600_000), ("cls", 100)):
        valor = _numero(bruto.get(clave), 0, maximo)
        if valor is not None:
            medicion[clave] = round(valor, 3)

    axe = bruto.get("axe")
    if isinstance(axe, dict) and isinstance(axe.get("violations"), list):
        violaciones = []
        for v in axe["violations"][:MAX_VIOLACIONES]:
            if not isinstance(v, dict) or v.get("impact") not in IMPACTOS:
                continue
            nodos = _numero(v.get("nodes"), 0, 100_000)
            violaciones.append({
                "id": str(v.get("id", ""))[:80],
                "impact": v["impact"],
                "nodes": int(nodos) if nodos is not None else 0,
                "help": str(v.get("help", ""))[:200],
            })
        pasadas = _numero(axe.get("passes"), 0, 10_000)
        medicion["axe"] = {"violations": violaciones, "passes": int(pasadas) if pasadas is not None else 0}

    if not medicion:
        raise MedicionFallida("El navegador aislado no devolvió ninguna medida.")
    return medicion


# Umbrales de Google para las Core Web Vitals (web.dev/vitals).
UMBRALES = {"lcp_ms": (2500, 4000), "tbt_ms": (200, 600), "cls": (0.1, 0.25)}


def calificar(clave: str, valor: float) -> str:
    bueno, mejorable = UMBRALES[clave]
    if valor <= bueno:
        return "bueno"
    return "mejorable" if valor <= mejorable else "malo"
