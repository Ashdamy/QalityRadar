"""Actividad del proyecto: senales de que esta vivo y mantenido.

Aviso importante: **"actividad del proyecto" NO es una caracteristica de
ISO/IEC 25010**. Es una dimension propia del spec de QalitiRadar, util para
juzgar si merece la pena depender de un proyecto, pero no forma parte de la
norma. Se documenta asi en docs/ISO_25010_MAPPING.md para no dar a entender
lo contrario.

A diferencia del resto de analizadores, este no lee el repositorio clonado:
consulta la API de GitHub, porque los commits recientes, las incidencias y
las publicaciones no estan en un clon superficial.
"""

from datetime import datetime, timedelta, timezone

import httpx

from app.analyzers.base import AnalyzerResult, FindingData

GITHUB_API_BASE = "https://api.github.com"
REQUEST_TIMEOUT_SECONDS = 15

# Umbrales de abandono. Un proyecto sin un solo commit en medio ano rara vez
# recibira una correccion de seguridad a tiempo.
STALE_DAYS = 180
DORMANT_DAYS = 365


class ActivityAnalyzer:
    """Se construye con el nombre del repositorio porque no analiza ficheros."""

    name = "activity"

    def __init__(self, full_name: str, token: str | None = None) -> None:
        self._full_name = full_name
        self._token = token

    def analyze(self, repo_dir=None) -> AnalyzerResult:  # noqa: ARG002 - firma comun
        datos, estado = self._fetch()
        if datos is None:
            return AnalyzerResult(
                dimension="project_activity",
                metrics={"activity_scan_status": estado},
                findings=[],
            )

        ahora = datetime.now(timezone.utc)
        ultimo_push = _parse_date(datos.get("pushed_at"))
        dias_sin_cambios = (ahora - ultimo_push).days if ultimo_push else None

        metrics = {
            "activity_scan_status": "ok",
            "days_since_last_push": dias_sin_cambios,
            "open_issues": datos.get("open_issues_count", 0),
            "stars": datos.get("stargazers_count", 0),
            "forks": datos.get("forks_count", 0),
            "is_archived": bool(datos.get("archived")),
            "has_description": bool(datos.get("description")),
            "has_topics": bool(datos.get("topics")),
        }

        findings: list[FindingData] = []
        if datos.get("archived"):
            findings.append(
                FindingData(
                    type="activity",
                    severity="high",
                    title="El repositorio esta archivado",
                    description=(
                        "GitHub lo marca como archivado: es de solo lectura y no recibira mas "
                        "cambios, incluidas correcciones de seguridad."
                    ),
                    recommendation="No lo uses como dependencia activa; busca una alternativa mantenida.",
                )
            )
        elif dias_sin_cambios is not None and dias_sin_cambios > DORMANT_DAYS:
            findings.append(
                FindingData(
                    type="activity",
                    severity="high",
                    title=f"Sin cambios desde hace {dias_sin_cambios} dias",
                    description=(
                        "Ha pasado mas de un ano sin un solo commit. Un proyecto asi rara vez "
                        "recibe correcciones de seguridad a tiempo."
                    ),
                    recommendation="Comprueba si el proyecto sigue mantenido antes de depender de el.",
                )
            )
        elif dias_sin_cambios is not None and dias_sin_cambios > STALE_DAYS:
            findings.append(
                FindingData(
                    type="activity",
                    severity="medium",
                    title=f"Sin cambios desde hace {dias_sin_cambios} dias",
                    description="Han pasado mas de seis meses sin actividad en el repositorio.",
                    recommendation="Retoma el mantenimiento o indica su estado en el README.",
                )
            )

        if not metrics["has_description"]:
            findings.append(
                FindingData(
                    type="activity",
                    severity="low",
                    title="El repositorio no tiene descripcion",
                    description=(
                        "Sin descripcion en GitHub, quien lo encuentre no sabe que hace sin abrir "
                        "el codigo."
                    ),
                    recommendation="Anade una descripcion breve en los ajustes del repositorio.",
                )
            )

        return AnalyzerResult(dimension="project_activity", metrics=metrics, findings=findings)

    def _fetch(self) -> tuple[dict | None, str]:
        headers = {"Accept": "application/vnd.github+json"}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        try:
            respuesta = httpx.get(
                f"{GITHUB_API_BASE}/repos/{self._full_name}",
                headers=headers,
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
        except httpx.RequestError:
            return None, "no se pudo contactar con GitHub"
        if respuesta.status_code == 404:
            return None, "el repositorio no existe o no es publico"
        if respuesta.status_code == 403:
            return None, "limite de peticiones de GitHub alcanzado"
        if respuesta.status_code != 200:
            return None, f"GitHub respondio {respuesta.status_code}"
        try:
            return respuesta.json(), "ok"
        except ValueError:
            return None, "respuesta de GitHub ilegible"


def _parse_date(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
