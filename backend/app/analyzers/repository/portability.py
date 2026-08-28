"""Portabilidad: adaptabilidad, instalabilidad y reemplazabilidad.

Sub-caracteristicas de "Portability" en ISO/IEC 25010:

- Adaptabilidad: el proyecto se adapta a otro entorno sin tocar el codigo
  (configuracion por variables de entorno, sin rutas absolutas del autor).
- Instalabilidad: se puede poner en marcha en otra maquina (contenedor,
  fichero de dependencias con versiones fijadas, instrucciones).
- Reemplazabilidad: usa interfaces estandar en vez de acoplarse a un unico
  proveedor.
"""

import re
from pathlib import Path

from app.analyzers.base import AnalyzerResult, FindingData
from app.analyzers.repository.structure import IGNORED_DIRECTORIES

CODE_EXTENSIONS = {".py", ".js", ".jsx", ".ts", ".tsx", ".java", ".go", ".rb"}
MAX_FILES_TO_READ = 1000

# Configuracion leida del entorno: senal de adaptabilidad.
_ENV_ACCESS = re.compile(r"(os\.environ|os\.getenv|process\.env|ENV\[|System\.getenv)")
# Rutas absolutas de la maquina del autor: rompen la portabilidad.
_ABSOLUTE_PATH = re.compile(r"['\"](?:[A-Za-z]:\\\\?Users\\\\|/home/|/Users/)[^'\"]{3,}['\"]")

LOCKFILES = (
    "package-lock.json", "yarn.lock", "pnpm-lock.yaml", "poetry.lock",
    "Pipfile.lock", "Gemfile.lock", "go.sum", "Cargo.lock", "composer.lock",
)
CONTAINER_FILES = ("Dockerfile", "docker-compose.yml", "docker-compose.yaml", "Containerfile")
IAC_FILES = ("terraform", "ansible", "helm", "k8s", "kubernetes", ".github/workflows")


class PortabilityAnalyzer:
    name = "portability"

    def analyze(self, repo_dir: Path) -> AnalyzerResult:
        files_with_env_config = 0
        hardcoded_paths: list[str] = []
        code_files = 0

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
            code_files += 1

            if _ENV_ACCESS.search(text):
                files_with_env_config += 1
            if _ABSOLUTE_PATH.search(text):
                hardcoded_paths.append(str(relative).replace("\\", "/"))

        has_container = any((repo_dir / name).is_file() for name in CONTAINER_FILES)
        has_lockfile = any((repo_dir / name).is_file() for name in LOCKFILES)
        has_env_example = any(
            (repo_dir / name).is_file() for name in (".env.example", ".env.sample", ".env.template")
        )
        has_iac = any((repo_dir / name).exists() for name in IAC_FILES)

        metrics = {
            "has_container_definition": has_container,
            "has_dependency_lockfile": has_lockfile,
            "has_env_example": has_env_example,
            "has_infrastructure_as_code": has_iac,
            "uses_environment_config": files_with_env_config > 0,
            "hardcoded_absolute_path_count": len(hardcoded_paths),
        }

        findings: list[FindingData] = []
        if hardcoded_paths:
            findings.append(
                FindingData(
                    type="cicd",
                    severity="high",
                    title=f"Hay {len(hardcoded_paths)} rutas absolutas escritas en el codigo",
                    description=(
                        "El codigo contiene rutas del sistema de archivos de una maquina concreta. "
                        "En cualquier otro equipo o servidor esas rutas no existen y el proyecto falla."
                    ),
                    file_path=hardcoded_paths[0],
                    recommendation="Sustituyelas por rutas relativas o valores de configuracion.",
                )
            )
        if not has_lockfile:
            findings.append(
                FindingData(
                    type="dependency",
                    severity="medium",
                    title="No hay fichero de bloqueo de dependencias",
                    description=(
                        "Sin lockfile, cada instalacion puede traer versiones distintas de las "
                        "dependencias: el proyecto funciona en una maquina y falla en otra, y una "
                        "version nueva con un fallo entra sin que nadie lo decida."
                    ),
                    recommendation="Genera y versiona el lockfile de tu gestor de paquetes.",
                )
            )
        if not has_container:
            findings.append(
                FindingData(
                    type="cicd",
                    severity="low",
                    title="No hay definicion de contenedor",
                    description=(
                        "Sin Dockerfile ni equivalente, poner el proyecto en marcha depende de "
                        "reproducir a mano el entorno de quien lo escribio."
                    ),
                    recommendation="Anade un Dockerfile que deje el entorno reproducible.",
                )
            )

        return AnalyzerResult(dimension="portability", metrics=metrics, findings=findings)
