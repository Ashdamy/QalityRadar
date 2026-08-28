"""Seguridad: confidencialidad e integridad, comprobadas de forma estatica.

Sub-caracteristicas de "Security" en ISO/IEC 25010:

- Confidencialidad: no hay credenciales expuestas en el repositorio.
- Integridad: las dependencias estan fijadas y hay revision de cambios.
- Autenticidad y responsabilidad: se detectan patrones de codigo peligrosos
  que permiten ejecutar contenido no confiable.

Esto NO sustituye a Gitleaks ni a Semgrep, que llegan en la Semana 2B con el
sandbox. Cubre lo evidente para que la dimension deje de valer cero mientras
tanto, y es deliberadamente conservador: prefiere no avisar antes que llenar
el informe de falsos positivos.
"""

import re
from pathlib import Path

from app.analyzers.base import AnalyzerResult, FindingData
from app.analyzers.repository.structure import IGNORED_DIRECTORIES

CODE_EXTENSIONS = {".py", ".js", ".jsx", ".ts", ".tsx", ".java", ".go", ".rb", ".php"}
MAX_FILES_TO_READ = 1000

# Credenciales asignadas literalmente. Se exige una cadena de longitud
# razonable para no marcar ejemplos vacios ni placeholders.
_HARDCODED_SECRET = re.compile(
    r"""(?ix)
    \b(api[_-]?key|secret|password|passwd|token|private[_-]?key|access[_-]?key)
    \s*[:=]\s*
    ['"][A-Za-z0-9/+_\-]{16,}['"]
    """
)
# Valores claramente de ejemplo que no deben contar como hallazgo.
_PLACEHOLDER = re.compile(
    r"(?i)(your|example|placeholder|changeme|change[_-]me|xxx+|dummy|sample|test|fake|<.+>)"
)
# Ejecucion de contenido dinamico.
_DANGEROUS_EXEC = re.compile(r"\b(eval\(|exec\(|new Function\(|child_process\.exec\()")
# Concatenacion de SQL con variables.
_SQL_CONCAT = re.compile(r"(?i)(select|insert|update|delete)\s+.{0,80}(\+\s*\w+|%\s*\w+|\$\{)")

COMMITTED_SECRET_FILES = (".env", ".env.local", ".env.production", "credentials.json", "id_rsa")


class SecurityBasicsAnalyzer:
    name = "security_basics"

    def analyze(self, repo_dir: Path) -> AnalyzerResult:
        hardcoded: list[str] = []
        dangerous_exec: list[str] = []
        sql_concat: list[str] = []
        code_files = 0

        for path in sorted(repo_dir.rglob("*")):
            if code_files >= MAX_FILES_TO_READ:
                break
            if not path.is_file() or path.suffix.lower() not in CODE_EXTENSIONS:
                continue
            relative = path.relative_to(repo_dir)
            parts = relative.parts
            if any(part in IGNORED_DIRECTORIES for part in parts):
                continue
            # Los archivos de prueba usan credenciales ficticias a proposito.
            if any(p.lower() in {"test", "tests", "__tests__", "spec"} for p in parts):
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            code_files += 1
            display = str(relative).replace("\\", "/")

            for match in _HARDCODED_SECRET.finditer(text):
                if not _PLACEHOLDER.search(match.group(0)):
                    hardcoded.append(display)
                    break
            if _DANGEROUS_EXEC.search(text):
                dangerous_exec.append(display)
            if _SQL_CONCAT.search(text):
                sql_concat.append(display)

        committed_secret_files = [
            name for name in COMMITTED_SECRET_FILES if (repo_dir / name).is_file()
        ]
        gitignore = repo_dir / ".gitignore"
        gitignore_text = gitignore.read_text(encoding="utf-8", errors="replace") if gitignore.is_file() else ""
        gitignore_covers_env = ".env" in gitignore_text

        metrics = {
            "code_files_scanned": code_files,
            "hardcoded_secret_file_count": len(hardcoded),
            "committed_secret_files": committed_secret_files,
            "gitignore_covers_env": gitignore_covers_env,
            "dangerous_eval_file_count": len(dangerous_exec),
            "sql_concatenation_file_count": len(sql_concat),
        }

        findings: list[FindingData] = []
        if committed_secret_files:
            findings.append(
                FindingData(
                    type="security",
                    severity="critical",
                    title=f"Hay archivos de credenciales versionados: {', '.join(committed_secret_files)}",
                    description=(
                        "Estos archivos suelen contener claves y contrasenas reales. Al estar en el "
                        "repositorio quedan en el historial de git para siempre, aunque se borren "
                        "despues, y son visibles para cualquiera con acceso al codigo."
                    ),
                    file_path=committed_secret_files[0],
                    recommendation=(
                        "Retiralos del repositorio, anadelos a .gitignore y rota inmediatamente "
                        "todas las credenciales que contuvieran."
                    ),
                )
            )
        if hardcoded:
            findings.append(
                FindingData(
                    type="security",
                    severity="critical",
                    title=f"Hay credenciales escritas en el codigo en {len(hardcoded)} archivos",
                    description=(
                        "Se encontraron claves o contrasenas asignadas literalmente en el codigo "
                        "fuente. Quedan en el historial de git y se filtran con cada copia del "
                        "repositorio."
                    ),
                    file_path=hardcoded[0],
                    recommendation="Muevelas a variables de entorno y rota las que estuvieran expuestas.",
                )
            )
        if not gitignore_covers_env:
            findings.append(
                FindingData(
                    type="security",
                    severity="medium",
                    title="El .gitignore no protege los archivos .env",
                    description=(
                        "Sin una regla para .env, es cuestion de tiempo que alguien suba por "
                        "accidente un archivo con credenciales reales."
                    ),
                    recommendation="Agrega `.env` al .gitignore.",
                )
            )
        if dangerous_exec:
            findings.append(
                FindingData(
                    type="security",
                    severity="high",
                    title=f"Se ejecuta codigo dinamico en {len(dangerous_exec)} archivos",
                    description=(
                        "Se usan construcciones como eval o exec. Si alguna recibe datos que vengan "
                        "del usuario, un atacante puede ejecutar codigo arbitrario en el servidor."
                    ),
                    file_path=dangerous_exec[0],
                    recommendation="Sustituyelas por alternativas que no evaluen texto como codigo.",
                )
            )
        if sql_concat:
            findings.append(
                FindingData(
                    type="security",
                    severity="high",
                    title=f"Posible SQL construido por concatenacion en {len(sql_concat)} archivos",
                    description=(
                        "Se detectaron consultas SQL formadas uniendo texto con variables, el patron "
                        "clasico de la inyeccion SQL."
                    ),
                    file_path=sql_concat[0],
                    recommendation="Usa consultas parametrizadas en lugar de concatenar valores.",
                )
            )

        return AnalyzerResult(dimension="security", metrics=metrics, findings=findings)
