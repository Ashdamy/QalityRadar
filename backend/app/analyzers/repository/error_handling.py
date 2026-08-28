"""Fiabilidad: tolerancia a fallos y recuperabilidad.

Sub-caracteristicas de "Reliability" en ISO/IEC 25010 que se pueden observar
leyendo el codigo:

- Tolerancia a fallos: el codigo contempla que las cosas fallen (manejo de
  errores, timeouts, reintentos) en vez de asumir el camino feliz.
- Recuperabilidad: deja rastro para diagnosticar (logging) y sus cambios de
  estado son reversibles (migraciones, transacciones).
- Madurez: se detectan anti-patrones que degradan la fiabilidad, sobre todo
  los bloques que capturan un error y lo descartan en silencio.
"""

import re
from pathlib import Path

from app.analyzers.base import AnalyzerResult, FindingData
from app.analyzers.repository.structure import IGNORED_DIRECTORIES

CODE_EXTENSIONS = {".py", ".js", ".jsx", ".ts", ".tsx"}
MAX_FILES_TO_READ = 1500

# Manejo de errores explicito.
_TRY = re.compile(r"^\s*(try\s*[:{]|catch\s*\()", re.MULTILINE)
# Capturas que se tragan el error sin hacer nada: el fallo desaparece sin
# rastro, que es peor que no capturarlo.
_SILENT_PYTHON = re.compile(r"except[^\n:]*:\s*\n\s*(pass|\.\.\.)\s*(\n|$)")
_SILENT_JS = re.compile(r"catch\s*\([^)]*\)\s*\{\s*\}")
_BARE_EXCEPT = re.compile(r"^\s*except\s*:", re.MULTILINE)

_LOGGING = re.compile(r"\b(logging\.|logger\.|winston|pino|structlog|log\.(info|warn|error))")
_TIMEOUT = re.compile(r"\btimeout\b", re.IGNORECASE)
_RETRY = re.compile(r"\b(retry|retries|backoff|tenacity)\b", re.IGNORECASE)


class ErrorHandlingAnalyzer:
    name = "error_handling"

    def analyze(self, repo_dir: Path) -> AnalyzerResult:
        files_with_error_handling = 0
        code_files = 0
        silent_catches: list[str] = []
        bare_excepts: list[str] = []
        files_with_logging = 0
        files_with_timeout = 0
        files_with_retry = 0

        for path in sorted(repo_dir.rglob("*")):
            if code_files >= MAX_FILES_TO_READ:
                break
            if not path.is_file() or path.suffix.lower() not in CODE_EXTENSIONS:
                continue
            relative = path.relative_to(repo_dir)
            if any(part in IGNORED_DIRECTORIES for part in relative.parts):
                continue

            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            if not text.strip():
                continue

            code_files += 1
            display = str(relative).replace("\\", "/")

            if _TRY.search(text):
                files_with_error_handling += 1
            if _SILENT_PYTHON.search(text) or _SILENT_JS.search(text):
                silent_catches.append(display)
            if _BARE_EXCEPT.search(text):
                bare_excepts.append(display)
            if _LOGGING.search(text):
                files_with_logging += 1
            if _TIMEOUT.search(text):
                files_with_timeout += 1
            if _RETRY.search(text):
                files_with_retry += 1

        has_migrations = any(
            (repo_dir / name).is_dir()
            for name in ("migrations", "alembic", "db/migrate", "prisma")
        )

        metrics = {
            "code_files_scanned": code_files,
            "error_handling_ratio": round(files_with_error_handling / code_files, 3) if code_files else 0.0,
            "logging_ratio": round(files_with_logging / code_files, 3) if code_files else 0.0,
            "silent_catch_count": len(silent_catches),
            "bare_except_count": len(bare_excepts),
            "uses_timeouts": files_with_timeout > 0,
            "uses_retries": files_with_retry > 0,
            "has_migrations": has_migrations,
        }

        findings: list[FindingData] = []
        if silent_catches:
            findings.append(
                FindingData(
                    type="security",
                    severity="high",
                    title=f"Hay {len(silent_catches)} bloques que descartan errores en silencio",
                    description=(
                        "Se capturan excepciones sin hacer nada con ellas. El fallo desaparece sin "
                        "dejar rastro, el programa sigue con datos posiblemente invalidos y "
                        "diagnosticar el problema despues se vuelve casi imposible."
                    ),
                    file_path=silent_catches[0],
                    recommendation="Registra el error o vuelve a lanzarlo; nunca lo descartes en silencio.",
                )
            )
        if bare_excepts:
            findings.append(
                FindingData(
                    type="security",
                    severity="medium",
                    title=f"Hay {len(bare_excepts)} capturas de excepcion sin tipo",
                    description=(
                        "Un `except:` sin tipo atrapa tambien interrupciones del sistema y errores "
                        "de programacion, ocultando fallos que deberian detener el proceso."
                    ),
                    file_path=bare_excepts[0],
                    recommendation="Captura los tipos de excepcion concretos que sabes manejar.",
                )
            )
        if code_files >= 5 and metrics["error_handling_ratio"] < 0.1:
            findings.append(
                FindingData(
                    type="security",
                    severity="medium",
                    title="Practicamente no hay manejo de errores",
                    description=(
                        f"Solo el {metrics['error_handling_ratio']:.0%} de los archivos contempla que "
                        "algo pueda fallar. El codigo asume el camino feliz y cualquier imprevisto "
                        "termina en una caida."
                    ),
                    recommendation="Maneja los fallos en los limites del sistema: red, disco y entrada del usuario.",
                )
            )
        if code_files >= 5 and files_with_logging == 0:
            findings.append(
                FindingData(
                    type="security",
                    severity="medium",
                    title="El proyecto no registra nada",
                    description=(
                        "No se encontro ninguna llamada a un sistema de logging. Sin registros, "
                        "diagnosticar un fallo en produccion depende de reproducirlo a ciegas."
                    ),
                    recommendation="Incorpora logging estructurado en las operaciones importantes.",
                )
            )

        return AnalyzerResult(dimension="reliability", metrics=metrics, findings=findings)
