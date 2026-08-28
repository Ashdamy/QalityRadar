"""Detecta lenguajes, mide el tamano del codigo e infiere la forma del proyecto.

Ademas de contar archivos, recoge senales reales de mantenibilidad: tamano de
los archivos, presencia de .gitignore, de un manifiesto de dependencias y de
configuracion de linter o formateador. Sin estas senales la dimension de
mantenibilidad no se puede puntuar de forma honesta.
"""

from collections import Counter
from pathlib import Path

from app.analyzers.base import AnalyzerResult, FindingData

# Directorios que no son codigo del proyecto y distorsionarian el conteo.
IGNORED_DIRECTORIES = {
    ".git", "node_modules", ".venv", "venv", "__pycache__", "dist", "build",
    ".next", "out", "target", "vendor", ".mypy_cache", ".pytest_cache",
}

EXTENSION_TO_LANGUAGE = {
    ".py": "Python", ".js": "JavaScript", ".jsx": "JavaScript",
    ".ts": "TypeScript", ".tsx": "TypeScript", ".java": "Java",
    ".rb": "Ruby", ".go": "Go", ".rs": "Rust", ".php": "PHP",
    ".cs": "C#", ".c": "C", ".cpp": "C++", ".kt": "Kotlin", ".swift": "Swift",
}

FRONTEND_MARKERS = {"frontend", "client", "web", "ui"}
BACKEND_MARKERS = {"backend", "server", "api"}

DEPENDENCY_MANIFESTS = (
    "package.json", "requirements.txt", "pyproject.toml", "Pipfile", "Gemfile",
    "go.mod", "Cargo.toml", "pom.xml", "build.gradle", "composer.json",
)

# Nombres exactos y prefijos de configuracion de linters/formateadores.
LINTER_CONFIG_NAMES = {
    ".eslintrc", ".eslintrc.json", ".eslintrc.js", "eslint.config.js",
    "eslint.config.mjs", ".prettierrc", ".prettierrc.json", "prettier.config.js",
    ".flake8", "setup.cfg", "tox.ini", ".pylintrc", "ruff.toml", ".ruff.toml",
    ".rubocop.yml", ".golangci.yml", ".golangci.yaml", ".editorconfig",
}

# Un archivo por encima de esto es dificil de mantener y de revisar.
LARGE_FILE_LINES = 1000
# Media por encima de la cual el codigo tiende a estar poco descompuesto.
HIGH_AVERAGE_FILE_LINES = 400


class StructureAnalyzer:
    name = "structure"

    def analyze(self, repo_dir: Path) -> AnalyzerResult:
        languages: Counter[str] = Counter()
        extensions: Counter[str] = Counter()
        total_files = 0
        top_level_dirs: set[str] = set()
        code_line_counts: list[int] = []
        largest_file: tuple[str, int] = ("", 0)
        max_depth = 0

        for path in repo_dir.rglob("*"):
            relative = path.relative_to(repo_dir)
            if any(part in IGNORED_DIRECTORIES for part in relative.parts):
                continue
            if path.is_dir():
                if len(relative.parts) == 1:
                    top_level_dirs.add(relative.parts[0].lower())
                max_depth = max(max_depth, len(relative.parts))
                continue

            total_files += 1
            extensions[path.suffix.lower()] += 1
            language = EXTENSION_TO_LANGUAGE.get(path.suffix.lower())
            if language:
                languages[language] += 1
                lines = _count_lines(path)
                code_line_counts.append(lines)
                if lines > largest_file[1]:
                    largest_file = (str(relative).replace("\\", "/"), lines)

        average_lines = round(sum(code_line_counts) / len(code_line_counts), 1) if code_line_counts else 0.0
        has_gitignore = (repo_dir / ".gitignore").is_file()
        has_manifest = any((repo_dir / name).is_file() for name in DEPENDENCY_MANIFESTS)
        has_linter_config = any(
            (repo_dir / name).is_file() for name in LINTER_CONFIG_NAMES
        ) or _pyproject_declares_tooling(repo_dir)

        metrics = {
            "total_files": total_files,
            "code_file_count": len(code_line_counts),
            "languages": dict(languages),
            "extensions": dict(extensions),
            "primary_language": languages.most_common(1)[0][0] if languages else None,
            "project_shape": self._infer_shape(top_level_dirs),
            "average_file_lines": average_lines,
            "largest_file_lines": largest_file[1],
            "largest_file_path": largest_file[0] or None,
            "files_over_1000_lines": sum(1 for n in code_line_counts if n > LARGE_FILE_LINES),
            "max_directory_depth": max_depth,
            "top_level_directory_count": len(top_level_dirs),
            "has_gitignore": has_gitignore,
            "has_dependency_manifest": has_manifest,
            "has_linter_config": has_linter_config,
        }

        findings: list[FindingData] = []
        if total_files == 0:
            findings.append(
                FindingData(
                    type="structure",
                    severity="high",
                    title="Repositorio vacio",
                    description="No se encontro ningun archivo analizable en el repositorio.",
                    recommendation="Verifica que la rama analizada sea la correcta.",
                )
            )
        if not has_gitignore and total_files > 0:
            findings.append(
                FindingData(
                    type="structure",
                    severity="medium",
                    title="Falta .gitignore",
                    description=(
                        "Sin .gitignore es facil acabar subiendo dependencias, artefactos de "
                        "compilacion o archivos con credenciales al repositorio."
                    ),
                    recommendation="Agrega un .gitignore adecuado al lenguaje del proyecto.",
                )
            )
        if not has_linter_config and len(code_line_counts) >= 5:
            findings.append(
                FindingData(
                    type="structure",
                    severity="low",
                    title="Sin configuracion de linter o formateador",
                    description=(
                        "No se encontro configuracion de linter ni de formateador, asi que el "
                        "estilo del codigo no esta verificado de forma automatica."
                    ),
                    recommendation="Anade un linter (ESLint, Ruff, RuboCop...) y su configuracion.",
                )
            )
        if largest_file[1] > LARGE_FILE_LINES:
            findings.append(
                FindingData(
                    type="structure",
                    severity="medium",
                    title="Hay archivos demasiado grandes",
                    description=(
                        f"El archivo mas grande tiene {largest_file[1]} lineas. Los archivos muy "
                        "extensos son dificiles de entender, revisar y probar."
                    ),
                    file_path=largest_file[0],
                    recommendation="Divide el archivo en modulos con una responsabilidad clara cada uno.",
                )
            )
        if average_lines > HIGH_AVERAGE_FILE_LINES:
            findings.append(
                FindingData(
                    type="structure",
                    severity="medium",
                    title="Los archivos son grandes de media",
                    description=(
                        f"La media es de {average_lines} lineas por archivo, senal de que el codigo "
                        "esta poco descompuesto."
                    ),
                    recommendation="Extrae responsabilidades a modulos mas pequenos.",
                )
            )

        return AnalyzerResult(dimension="maintainability", metrics=metrics, findings=findings)

    def _infer_shape(self, top_level_dirs: set[str]) -> str:
        has_frontend = bool(top_level_dirs & FRONTEND_MARKERS)
        has_backend = bool(top_level_dirs & BACKEND_MARKERS)
        if has_frontend and has_backend:
            return "fullstack"
        if has_frontend:
            return "frontend"
        if has_backend:
            return "backend"
        return "unknown"


def _count_lines(path: Path) -> int:
    try:
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            return sum(1 for _ in handle)
    except OSError:
        return 0


def _pyproject_declares_tooling(repo_dir: Path) -> bool:
    """pyproject.toml suele contener la config de ruff/black en vez de un archivo aparte."""
    pyproject = repo_dir / "pyproject.toml"
    if not pyproject.is_file():
        return False
    content = pyproject.read_text(encoding="utf-8", errors="replace").lower()
    return any(tool in content for tool in ("[tool.ruff", "[tool.black", "[tool.flake8", "[tool.pylint"))
