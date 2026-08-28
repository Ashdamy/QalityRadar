"""Adecuacion funcional: completitud y pertinencia funcional.

Sub-caracteristicas de "Functional Suitability" en ISO/IEC 25010 observables
de forma estatica:

- Completitud funcional: cuanto queda declaradamente sin terminar (marcas
  TODO/FIXME, funciones sin implementar).
- Pertinencia funcional: el proyecto se presenta y se puede evaluar (ejemplos,
  documentacion de API, plantillas de incidencias, versionado).
"""

import re
from pathlib import Path

from app.analyzers.base import AnalyzerResult, FindingData
from app.analyzers.repository.structure import IGNORED_DIRECTORIES

CODE_EXTENSIONS = {".py", ".js", ".jsx", ".ts", ".tsx", ".java", ".go", ".rb", ".rs"}
MAX_FILES_TO_READ = 1500

_PENDING_MARKER = re.compile(r"\b(TODO|FIXME|HACK|XXX)\b")
# Funciones declaradas pero sin implementar.
_STUB = re.compile(r"(raise\s+NotImplementedError|throw new Error\(['\"]not implemented)", re.IGNORECASE)

API_DOC_FILES = ("openapi.json", "openapi.yaml", "openapi.yml", "swagger.json", "swagger.yaml", "api.md")
EXAMPLE_DIRS = ("examples", "example", "samples", "demo", "demos")


class CompletenessAnalyzer:
    name = "completeness"

    def analyze(self, repo_dir: Path) -> AnalyzerResult:
        pending_markers = 0
        files_with_pending: list[str] = []
        stub_count = 0
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

            found = len(_PENDING_MARKER.findall(text))
            if found:
                pending_markers += found
                files_with_pending.append(str(relative).replace("\\", "/"))
            stub_count += len(_STUB.findall(text))

        has_api_docs = any((repo_dir / name).is_file() for name in API_DOC_FILES) or any(
            (repo_dir / "docs" / name).is_file() for name in API_DOC_FILES
        )
        has_examples = any((repo_dir / name).is_dir() for name in EXAMPLE_DIRS)
        has_issue_templates = (repo_dir / ".github" / "ISSUE_TEMPLATE").exists() or (
            repo_dir / ".github" / "ISSUE_TEMPLATE.md"
        ).is_file()
        has_pr_template = (repo_dir / ".github" / "PULL_REQUEST_TEMPLATE.md").is_file()

        markers_per_file = round(pending_markers / code_files, 2) if code_files else 0.0
        metrics = {
            "completeness_files_scanned": code_files,
            "pending_marker_count": pending_markers,
            "pending_markers_per_file": markers_per_file,
            "unimplemented_stub_count": stub_count,
            "has_api_docs": has_api_docs,
            "has_examples": has_examples,
            "has_issue_templates": has_issue_templates,
            "has_pr_template": has_pr_template,
        }

        findings: list[FindingData] = []
        if markers_per_file > 1.0 and pending_markers > 10:
            findings.append(
                FindingData(
                    type="documentation",
                    severity="medium",
                    title=f"Hay {pending_markers} marcas de trabajo pendiente",
                    description=(
                        f"Una media de {markers_per_file} marcas TODO/FIXME por archivo indica que "
                        "queda bastante funcionalidad declaradamente sin terminar."
                    ),
                    file_path=files_with_pending[0] if files_with_pending else None,
                    recommendation="Convierte las marcas en incidencias rastreables o resuelvelas.",
                )
            )
        if stub_count:
            findings.append(
                FindingData(
                    type="documentation",
                    severity="high",
                    title=f"Hay {stub_count} funciones sin implementar",
                    description=(
                        "Se encontraron funciones que lanzan un error de 'no implementado'. Quien "
                        "use el proyecto se topara con fallos en funcionalidad que parece existir."
                    ),
                    recommendation="Implementalas o retiralas de la interfaz publica.",
                )
            )

        return AnalyzerResult(dimension="functional_suitability", metrics=metrics, findings=findings)
