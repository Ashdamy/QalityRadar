"""Comprueba la presencia y calidad basica de la documentacion del proyecto."""

from pathlib import Path

from app.analyzers.base import AnalyzerResult, FindingData

README_NAMES = ("README.md", "README.rst", "README.txt", "README")
LICENSE_NAMES = ("LICENSE", "LICENSE.md", "LICENSE.txt", "LICENCE", "COPYING")
CONTRIBUTING_NAMES = ("CONTRIBUTING.md", "CONTRIBUTING.rst", "CONTRIBUTING")
CHANGELOG_NAMES = ("CHANGELOG.md", "CHANGELOG.rst", "CHANGELOG", "HISTORY.md")
ARCHITECTURE_NAMES = ("ARCHITECTURE.md", "DESIGN.md", "docs/ARCHITECTURE.md")

# Por debajo de esto un README no explica ni que hace el proyecto ni como usarlo.
MINIMUM_USEFUL_README_CHARS = 300

# Senales de que el README explica como usar el proyecto, no solo que es.
INSTALL_MARKERS = ("instal", "getting started", "setup", "requisitos", "requirements", "quick start")
USAGE_MARKERS = ("uso", "usage", "ejemplo", "example", "how to")


class DocumentationAnalyzer:
    name = "documentation"

    def analyze(self, repo_dir: Path) -> AnalyzerResult:
        readme_path = self._first_existing(repo_dir, README_NAMES)
        readme_length = len(readme_path.read_text(encoding="utf-8", errors="replace")) if readme_path else 0

        has_architecture = any((repo_dir / name).exists() for name in ARCHITECTURE_NAMES) or (
            (repo_dir / "docs").is_dir() and any((repo_dir / "docs").glob("*.md"))
        )

        readme_text = (
            readme_path.read_text(encoding="utf-8", errors="replace").lower() if readme_path else ""
        )
        metrics = {
            "has_readme": readme_path is not None,
            "readme_length": readme_length,
            "readme_has_install_instructions": any(m in readme_text for m in INSTALL_MARKERS),
            "readme_has_usage_section": any(m in readme_text for m in USAGE_MARKERS),
            "readme_has_code_examples": "```" in readme_text,
            "has_license": self._first_existing(repo_dir, LICENSE_NAMES) is not None,
            "has_contributing": self._first_existing(repo_dir, CONTRIBUTING_NAMES) is not None,
            "has_changelog": self._first_existing(repo_dir, CHANGELOG_NAMES) is not None,
            "has_architecture_docs": has_architecture,
        }

        findings: list[FindingData] = []
        if readme_path is None:
            findings.append(
                FindingData(
                    type="documentation",
                    severity="high",
                    title="Falta el README",
                    description="El repositorio no tiene un archivo README, asi que nadie puede saber que hace el proyecto ni como usarlo.",
                    recommendation="Agrega un README.md que explique el proposito, la instalacion y un ejemplo de uso.",
                )
            )
        elif readme_length < MINIMUM_USEFUL_README_CHARS:
            findings.append(
                FindingData(
                    type="documentation",
                    severity="medium",
                    title="El README es demasiado breve",
                    description=f"El README tiene {readme_length} caracteres, insuficiente para explicar el proyecto.",
                    file_path=readme_path.name,
                    recommendation="Amplia el README con proposito, instalacion, uso y ejemplos.",
                )
            )

        if not metrics["has_license"]:
            findings.append(
                FindingData(
                    type="documentation",
                    severity="medium",
                    title="Falta la licencia",
                    description="Sin un archivo LICENSE, legalmente nadie puede reutilizar el codigo.",
                    recommendation="Agrega un archivo LICENSE con la licencia que elijas.",
                )
            )

        return AnalyzerResult(dimension="functional_suitability", metrics=metrics, findings=findings)

    def _first_existing(self, repo_dir: Path, names: tuple[str, ...]) -> Path | None:
        for name in names:
            candidate = repo_dir / name
            if candidate.is_file():
                return candidate
        return None
