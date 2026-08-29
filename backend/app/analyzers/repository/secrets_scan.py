"""Deteccion de secretos con Gitleaks, ejecutado dentro del sandbox.

A diferencia del analizador de seguridad basica, que solo mira el arbol de
archivos actual con expresiones regulares propias, Gitleaks aplica cientos de
reglas mantenidas por la comunidad. Se ejecuta en el contenedor aislado
porque analiza codigo ajeno, aunque no lo ejecute.

Nota sobre el alcance: el clon es superficial (--depth 1), asi que se analiza
el estado actual del repositorio, no todo su historial. Un secreto borrado en
un commit anterior sigue estando en el historial de GitHub y este analisis no
lo vera; se advierte en el propio hallazgo para no dar una falsa tranquilidad.
"""

import json
from pathlib import Path

from app.analyzers.base import AnalyzerResult, FindingData
from app.utils.sandbox import WORKDIR_IN_CONTAINER, run_in_sandbox

ANALYZER_IMAGE = "qaliti/analyzer:latest"
GITLEAKS_TIMEOUT_SECONDS = 240
REPORT_PATH = "/tmp/gitleaks.json"

# Se limita cuantos hallazgos distintos se reportan: un repositorio con cientos
# de coincidencias no necesita cientos de tarjetas para entender el problema.
MAX_REPORTED_SECRETS = 10

# Rutas donde una credencial es casi siempre material de prueba, no un secreto
# real: proyectos serios incluyen certificados y claves ficticias para probar
# TLS o firmas. Marcarlas como criticas hunde la nota de un proyecto correcto
# y erosiona la confianza en la herramienta, asi que se informan con gravedad
# baja en vez de ignorarse: una credencial real ahi seguiria siendo visible.
TEST_FIXTURE_MARKERS = (
    "test/", "tests/", "__tests__/", "spec/", "specs/", "fixtures/", "fixture/",
    "testdata/", "test-data/", "mocks/", "__mocks__/", "examples/", "example/",
    "e2e/", "cypress/", "sample/", "samples/", "benchmark/", "benchmarks/",
)

# La documentacion es el otro sitio donde una credencial casi nunca es real:
# los tutoriales ENSENAN a configurar claves, asi que las escriben. Flask
# recibia cinco criticos por los ejemplos de SECRET_KEY de su propio manual, y
# como un critico limita la nota a 40, ese era su resultado final. Medir eso
# como una fuga es sencillamente falso.
DOCUMENTATION_MARKERS = (
    "docs/", "doc/", "documentation/", "website/", "site/", "guide/", "guides/",
    "tutorial/", "tutorials/", "changelog", "readme", "contributing",
)
DOCUMENTATION_SUFFIXES = (".md", ".rst", ".txt", ".adoc", ".mdx", ".ipynb")


class SecretsScanAnalyzer:
    name = "secrets_scan"

    def analyze(self, repo_dir: Path) -> AnalyzerResult:
        result = run_in_sandbox(
            ANALYZER_IMAGE,
            [
                "sh",
                "-c",
                # Gitleaks devuelve codigo 1 cuando encuentra secretos, que no
                # es un error: se ignora el codigo y se lee el informe.
                f"gitleaks detect --source /repo --no-git --report-format json "
                f"--report-path {REPORT_PATH} --exit-code 0 >/dev/null 2>&1; "
                f"cat {REPORT_PATH} 2>/dev/null || echo '[]'",
            ],
            repo_dir,
            timeout_seconds=GITLEAKS_TIMEOUT_SECONDS,
        )

        if result.timed_out:
            return AnalyzerResult(
                dimension="security",
                metrics={"secret_scan_status": "timeout", "secret_scan_available": False},
                findings=[],
            )
        if result.exit_code != 0:
            return AnalyzerResult(
                dimension="security",
                metrics={"secret_scan_status": "error", "secret_scan_available": False},
                findings=[],
            )

        leaks = _parse_report(result.stdout)
        if leaks is None:
            return AnalyzerResult(
                dimension="security",
                metrics={"secret_scan_status": "unreadable", "secret_scan_available": False},
                findings=[],
            )

        reales = [l for l in leaks if not _is_test_fixture(_strip_container_prefix(l.get("File")))]
        de_prueba = [l for l in leaks if _is_test_fixture(_strip_container_prefix(l.get("File")))]

        metrics = {
            "secret_scan_status": "ok",
            "secret_scan_available": True,
            # El recuento que puntua excluye el material de prueba.
            "leaked_secret_count": len(reales),
            "test_fixture_secret_count": len(de_prueba),
            "leaked_secret_rules": sorted({leak.get("RuleID", "desconocida") for leak in reales}),
        }

        findings: list[FindingData] = []
        for leak in reales[:MAX_REPORTED_SECRETS]:
            rule = leak.get("Description") or leak.get("RuleID") or "secreto"
            # Gitleaks informa la ruta dentro del contenedor (/repo/...); al
            # usuario le sirve la ruta relativa a su propio repositorio.
            file_path = _strip_container_prefix(leak.get("File"))
            line = leak.get("StartLine")
            ubicacion = f"{file_path}:{line}" if file_path and line else file_path
            findings.append(
                FindingData(
                    type="security",
                    severity="critical",
                    title=f"Secreto expuesto: {rule}",
                    description=(
                        "Gitleaks detecto una credencial en el codigo. Cualquiera con acceso al "
                        "repositorio puede usarla. Ademas, este analisis solo revisa el estado "
                        "actual: si la credencial estuvo antes en otro archivo, sigue en el "
                        "historial de git aunque hoy no aparezca."
                    ),
                    file_path=ubicacion,
                    recommendation=(
                        "Rota la credencial de inmediato, retirala del codigo y muevela a una "
                        "variable de entorno. Rotarla es lo primero: borrarla del archivo no la "
                        "invalida."
                    ),
                )
            )

        if len(reales) > MAX_REPORTED_SECRETS:
            findings.append(
                FindingData(
                    type="security",
                    severity="critical",
                    title=f"Hay {len(reales) - MAX_REPORTED_SECRETS} secretos expuestos mas",
                    description=(
                        f"Se detectaron {len(reales)} credenciales en total. Se listan las primeras "
                        f"{MAX_REPORTED_SECRETS}; el resto sigue el mismo patron."
                    ),
                    recommendation="Revisa el repositorio completo con Gitleaks en local.",
                )
            )

        if de_prueba:
            ubicaciones = sorted({_strip_container_prefix(l.get("File")) or "?" for l in de_prueba})
            findings.append(
                FindingData(
                    type="security",
                    severity="low",
                    title=f"Hay {len(de_prueba)} credenciales en archivos de prueba",
                    description=(
                        "Se detectaron credenciales en rutas de tests o material de ejemplo, donde "
                        "casi siempre son ficticias y estan puestas a proposito. No penalizan la "
                        "puntuacion, pero conviene confirmar que ninguna es real."
                    ),
                    file_path=ubicaciones[0],
                    recommendation="Verifica que sean ficticias; si alguna es real, rotala y retirala.",
                )
            )

        return AnalyzerResult(dimension="security", metrics=metrics, findings=findings)


def _is_test_fixture(file_path: str | None) -> bool:
    """Rutas donde una credencial es casi siempre ficticia: pruebas o manual.

    En ambos casos el hallazgo se informa con gravedad baja en vez de
    ignorarse: si de verdad hubiera una credencial real ahi, sigue viendose.
    Lo que no puede es hundir la nota de un proyecto correcto.
    """
    if not file_path:
        return False
    ruta = file_path.replace("\\", "/").lower()

    if any(marker in ruta or ruta.startswith(marker) for marker in TEST_FIXTURE_MARKERS):
        return True

    if ruta.endswith(DOCUMENTATION_SUFFIXES):
        return True

    return any(marker in ruta for marker in DOCUMENTATION_MARKERS)


def _strip_container_prefix(file_path: str | None) -> str | None:
    """Convierte /repo/src/config.py en src/config.py."""
    if not file_path:
        return None
    normalizado = file_path.replace("\\", "/")
    prefijo = f"{WORKDIR_IN_CONTAINER}/"
    if normalizado.startswith(prefijo):
        return normalizado[len(prefijo):]
    return normalizado


def _parse_report(stdout: str) -> list[dict] | None:
    """Gitleaks escribe JSON; devuelve None si la salida no es interpretable."""
    text = stdout.strip()
    if not text:
        return []
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None
    if data is None:
        return []
    if not isinstance(data, list):
        return None
    return data
