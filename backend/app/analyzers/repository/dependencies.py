"""Dependencias: vulnerabilidades conocidas y salud del arbol de paquetes.

Diseno deliberado: `npm audit` y `pip-audit` necesitan consultar internet, y
el sandbox corre con la red cortada, que es justo lo que lo hace seguro. En
vez de abrir un resquicio en el aislamiento, se separan las dos tareas:

1. Leer el manifiesto es interpretar un JSON o un texto: no ejecuta nada del
   proyecto analizado, asi que se hace directamente en el worker.
2. La consulta de vulnerabilidades se hace desde el worker contra la API
   publica de OSV.dev, enviando **solo nombres y versiones de paquetes**.
   Nunca sale codigo del usuario hacia un tercero.

Asi el sandbox conserva `--network=none` intacto.
"""

import json
import re
from pathlib import Path

import httpx

from app.analyzers.base import AnalyzerResult, FindingData

OSV_BATCH_URL = "https://api.osv.dev/v1/querybatch"
OSV_TIMEOUT_SECONDS = 20
# Se consulta un maximo de paquetes para acotar el tiempo del analisis.
MAX_PACKAGES_TO_QUERY = 200

_PY_REQUIREMENT = re.compile(r"^\s*([A-Za-z0-9._-]+)\s*==\s*([0-9][A-Za-z0-9._-]*)")


class DependenciesAnalyzer:
    name = "dependencies"

    def analyze(self, repo_dir: Path) -> AnalyzerResult:
        packages = _collect_packages(repo_dir)
        pinned = [p for p in packages if p["version"]]

        metrics = {
            "declared_dependency_count": len(packages),
            "pinned_dependency_count": len(pinned),
            "dependency_ecosystems": sorted({p["ecosystem"] for p in packages}),
        }

        findings: list[FindingData] = []

        if not packages:
            metrics["vulnerability_scan_status"] = "sin dependencias declaradas"
            return AnalyzerResult(dimension="security", metrics=metrics, findings=findings)

        vulnerable, status = _query_osv(pinned[:MAX_PACKAGES_TO_QUERY])
        metrics["vulnerability_scan_status"] = status
        metrics["vulnerable_dependency_count"] = len(vulnerable)
        metrics["vulnerable_dependencies"] = [v["name"] for v in vulnerable][:20]

        for vuln in vulnerable[:10]:
            findings.append(
                FindingData(
                    type="dependency",
                    severity="high",
                    title=f"Dependencia vulnerable: {vuln['name']} {vuln['version']}",
                    description=(
                        f"La version usada tiene {vuln['count']} vulnerabilidad(es) conocida(s) "
                        f"registradas publicamente ({', '.join(vuln['ids'][:3])}). Un atacante puede "
                        "aprovecharlas sin necesidad de encontrar un fallo nuevo."
                    ),
                    recommendation=f"Actualiza {vuln['name']} a una version corregida.",
                )
            )
        if len(vulnerable) > 10:
            findings.append(
                FindingData(
                    type="dependency",
                    severity="high",
                    title=f"Hay {len(vulnerable) - 10} dependencias vulnerables mas",
                    description=f"En total {len(vulnerable)} dependencias tienen vulnerabilidades conocidas.",
                    recommendation="Revisa el informe completo con la herramienta de auditoria de tu gestor.",
                )
            )

        # Una dependencia sin version fijada puede traer cualquier cosa manana.
        sin_fijar = len(packages) - len(pinned)
        if sin_fijar and sin_fijar / len(packages) > 0.5:
            findings.append(
                FindingData(
                    type="dependency",
                    severity="medium",
                    title=f"{sin_fijar} dependencias sin version fijada",
                    description=(
                        "Mas de la mitad de las dependencias no fijan version. Cada instalacion "
                        "puede traer codigo distinto, y una version nueva con un fallo entra sin "
                        "que nadie lo decida."
                    ),
                    recommendation="Fija las versiones y versiona el lockfile.",
                )
            )

        return AnalyzerResult(dimension="security", metrics=metrics, findings=findings)


def _collect_packages(repo_dir: Path) -> list[dict]:
    packages: list[dict] = []

    package_json = repo_dir / "package.json"
    if package_json.is_file():
        try:
            data = json.loads(package_json.read_text(encoding="utf-8", errors="replace"))
        except (json.JSONDecodeError, OSError):
            data = {}
        for seccion in ("dependencies", "devDependencies"):
            for nombre, rango in (data.get(seccion) or {}).items():
                packages.append(
                    {"ecosystem": "npm", "name": nombre, "version": _exact_npm_version(rango)}
                )

    requirements = repo_dir / "requirements.txt"
    if requirements.is_file():
        for linea in requirements.read_text(encoding="utf-8", errors="replace").splitlines():
            if linea.strip().startswith("#"):
                continue
            match = _PY_REQUIREMENT.match(linea)
            if match:
                packages.append({"ecosystem": "PyPI", "name": match.group(1), "version": match.group(2)})
            elif linea.strip() and not linea.startswith("-"):
                nombre = re.split(r"[<>=!~\[ ]", linea.strip(), 1)[0]
                if nombre:
                    packages.append({"ecosystem": "PyPI", "name": nombre, "version": None})

    return packages


def _exact_npm_version(rango: str) -> str | None:
    """Solo se consulta cuando la version es exacta: `^1.2.3` puede resolver a
    cualquier 1.x, y preguntar por la 1.2.3 daria una respuesta enganosa."""
    if not isinstance(rango, str):
        return None
    limpio = rango.strip()
    return limpio if re.fullmatch(r"\d+\.\d+\.\d+", limpio) else None


def _query_osv(packages: list[dict]) -> tuple[list[dict], str]:
    """Consulta OSV.dev enviando solo nombres y versiones de paquetes."""
    if not packages:
        return [], "sin versiones exactas que consultar"

    consultas = [
        {"package": {"name": p["name"], "ecosystem": p["ecosystem"]}, "version": p["version"]}
        for p in packages
    ]
    try:
        respuesta = httpx.post(OSV_BATCH_URL, json={"queries": consultas}, timeout=OSV_TIMEOUT_SECONDS)
        respuesta.raise_for_status()
        resultados = respuesta.json().get("results", [])
    except (httpx.HTTPError, json.JSONDecodeError, KeyError):
        # Si la consulta falla se informa, en vez de fingir que no hay
        # vulnerabilidades: la ausencia de datos no es una buena noticia.
        return [], "no se pudo consultar la base de vulnerabilidades"

    vulnerables: list[dict] = []
    for paquete, resultado in zip(packages, resultados):
        vulns = (resultado or {}).get("vulns") or []
        if vulns:
            vulnerables.append(
                {
                    "name": paquete["name"],
                    "version": paquete["version"],
                    "count": len(vulns),
                    "ids": [v.get("id", "") for v in vulns],
                }
            )
    return vulnerables, "ok"
