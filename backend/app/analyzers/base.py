"""Contrato comun de los analizadores.

Cada analizador recibe el directorio del repositorio ya clonado y devuelve
metricas crudas mas hallazgos concretos con evidencia. Ninguno ejecuta codigo
del repositorio: solo leen archivos.
"""

from collections.abc import Iterator
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


def esta_dentro(path: Path, repo_dir: Path) -> bool:
    """True si `path`, ya resuelto, sigue estando bajo el repositorio clonado."""
    try:
        return path.resolve().is_relative_to(repo_dir.resolve())
    except OSError:
        # Un enlace roto o una cadena de enlaces demasiado larga: si no se
        # puede comprobar, no se lee.
        return False


def es_archivo_del_repositorio(path: Path, repo_dir: Path) -> bool:
    """Para los archivos que se leen por nombre y no recorriendo.

    `package.json`, `requirements.txt`, `pyproject.toml`, el README y el
    `.gitignore` se abren por su ruta, sin pasar por el recorrido. Un enlace
    con cualquiera de esos nombres apuntando fuera del clon los llevaria a
    leer un archivo del worker igual que en el recorrido.
    """
    return path.is_file() and not path.is_symlink() and esta_dentro(path, repo_dir)


def archivos_del_repositorio(repo_dir: Path) -> Iterator[Path]:
    """Recorre los archivos del repositorio clonado sin salir de el.

    Aqui esta la unica trampa de leer codigo ajeno. El repositorio lo escribe
    un desconocido, y puede traer un enlace simbolico: `config.py -> /app/.env`
    hace que el analizador lea el fichero de secretos del propio worker, y
    despues informe de lo que encontro dentro. El codigo analizado nunca se
    ejecuta, pero si se lee, y leer el archivo equivocado basta.

    Importa que estos analizadores corren **en el worker, no en el contenedor
    aislado**: lo que alcanzan es la maquina de verdad.

    Dos comprobaciones y no una: se descartan los enlaces, y ademas se
    confirma que la ruta resuelta sigue dentro del clon. La segunda no depende
    de como recorra los enlaces la version de Python que toque.

    El orden es estable para que dos analisis del mismo repositorio recorran
    los archivos igual.
    """
    for path in sorted(repo_dir.rglob("*")):
        if path.is_symlink() or not esta_dentro(path, repo_dir):
            continue
        yield path
