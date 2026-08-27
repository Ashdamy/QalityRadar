"""Detecta la presencia y el tipo de tests. Nunca los ejecuta."""

from pathlib import Path

from app.analyzers.base import AnalyzerResult, FindingData
from app.analyzers.repository.structure import EXTENSION_TO_LANGUAGE, IGNORED_DIRECTORIES

TEST_DIRECTORY_NAMES = {"test", "tests", "__tests__", "spec", "e2e", "cypress"}
INTEGRATION_MARKERS = {"integration", "integracion"}
E2E_MARKERS = {"e2e", "cypress", "playwright"}

# Umbral por debajo del cual la cobertura declarada es simbolica.
LOW_TEST_RATIO = 0.1


def _is_test_file(relative: Path) -> bool:
    name = relative.name.lower()
    if any(part.lower() in TEST_DIRECTORY_NAMES for part in relative.parts[:-1]):
        return True
    return (
        name.startswith("test_")
        or name.endswith(("_test.py", ".test.ts", ".test.tsx", ".test.js", ".test.jsx"))
        or ".spec." in name
    )


class TestsAnalyzer:
    name = "tests"

    def analyze(self, repo_dir: Path) -> AnalyzerResult:
        test_files: list[Path] = []
        source_files: list[Path] = []

        for path in repo_dir.rglob("*"):
            if not path.is_file():
                continue
            relative = path.relative_to(repo_dir)
            if any(part in IGNORED_DIRECTORIES for part in relative.parts):
                continue
            if path.suffix.lower() not in EXTENSION_TO_LANGUAGE:
                continue
            (test_files if _is_test_file(relative) else source_files).append(relative)

        lowered = [str(p).lower() for p in test_files]
        metrics = {
            "test_file_count": len(test_files),
            "source_file_count": len(source_files),
            "test_ratio": round(len(test_files) / len(source_files), 3) if source_files else 0.0,
            "has_integration_tests": any(m in path for path in lowered for m in INTEGRATION_MARKERS),
            "has_e2e_tests": any(m in path for path in lowered for m in E2E_MARKERS),
        }

        findings: list[FindingData] = []
        if not test_files:
            findings.append(
                FindingData(
                    type="test_coverage",
                    severity="high",
                    title="El proyecto no tiene tests",
                    description="No se encontro ningun archivo de test, asi que no hay forma automatica de detectar regresiones.",
                    recommendation="Empieza por tests unitarios de la logica de negocio mas critica.",
                )
            )
        elif metrics["test_ratio"] < LOW_TEST_RATIO:
            findings.append(
                FindingData(
                    type="test_coverage",
                    severity="medium",
                    title="Muy pocos tests para el tamano del proyecto",
                    description=(
                        f"Hay {len(test_files)} archivos de test frente a {len(source_files)} de codigo "
                        f"(proporcion {metrics['test_ratio']})."
                    ),
                    recommendation="Amplia la cobertura sobre los modulos que cambian con mas frecuencia.",
                )
            )

        return AnalyzerResult(dimension="reliability", metrics=metrics, findings=findings)
