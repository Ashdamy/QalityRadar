"""Contrato comun de los analizadores.

Cada analizador recibe el directorio del repositorio ya clonado y devuelve
metricas crudas mas hallazgos concretos con evidencia. Ninguno ejecuta codigo
del repositorio: solo leen archivos.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class FindingData:
    type: str
    severity: str
    title: str
    description: str
    file_path: str | None = None
    # Los analizadores de URL ubican el hallazgo por direccion, no por archivo.
    url: str | None = None
    recommendation: str | None = None


@dataclass
class AnalyzerResult:
    dimension: str
    metrics: dict
    findings: list[FindingData] = field(default_factory=list)


class Analyzer(Protocol):
    name: str

    def analyze(self, repo_dir: Path) -> AnalyzerResult: ...
