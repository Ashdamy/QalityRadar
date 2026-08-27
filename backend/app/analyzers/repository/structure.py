"""Detecta lenguajes, cuenta archivos e infiere la forma del proyecto."""

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


class StructureAnalyzer:
    name = "structure"

    def analyze(self, repo_dir: Path) -> AnalyzerResult:
        languages: Counter[str] = Counter()
        extensions: Counter[str] = Counter()
        total_files = 0
        top_level_dirs: set[str] = set()

        for path in repo_dir.rglob("*"):
            if any(part in IGNORED_DIRECTORIES for part in path.relative_to(repo_dir).parts):
                continue
            if path.is_dir():
                relative = path.relative_to(repo_dir)
                if len(relative.parts) == 1:
                    top_level_dirs.add(relative.parts[0].lower())
                continue
            total_files += 1
            extensions[path.suffix.lower()] += 1
            language = EXTENSION_TO_LANGUAGE.get(path.suffix.lower())
            if language:
                languages[language] += 1

        shape = self._infer_shape(top_level_dirs)
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

        return AnalyzerResult(
            dimension="maintainability",
            metrics={
                "total_files": total_files,
                "languages": dict(languages),
                "extensions": dict(extensions),
                "primary_language": languages.most_common(1)[0][0] if languages else None,
                "project_shape": shape,
            },
            findings=findings,
        )

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
