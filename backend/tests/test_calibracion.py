"""Que la puntuacion no vuelva a descalibrarse sin que nadie se entere.

Un escaner de calidad se juega toda su credibilidad en una cosa: que la nota
se corresponda con la realidad. Y puede fallar en las dos direcciones —
demasiado blanda, y entonces no distingue nada; demasiado dura, y entonces
tampoco.

Estas pruebas fijan las causas concretas que provocaron el segundo caso:
Flask, una de las referencias de Python, sacaba exactamente 40/100 porque los
ejemplos de `SECRET_KEY` de su propio manual se contaban como cinco secretos
filtrados, y un hallazgo critico limita la nota a 40.

No analizan repositorios reales a proposito: eso tarda minutos y necesita red.
Se prueba la logica que produjo el error.
"""

import json
import tempfile
from pathlib import Path

import pytest

from app.analyzers.base import FindingData
from app.analyzers.repository.dependencies import _collect_packages
from app.analyzers.repository.secrets_scan import _is_test_fixture
from app.services.repo_service import _branch_not_found
from app.services.scoring_service import calculate_overall_score


# --------------------------------------------------------------------------
# Secretos: donde una credencial casi nunca es real
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "ruta",
    [
        # Los cinco que hundian a Flask.
        "docs/config.rst",
        "docs/tutorial/deploy.rst",
        # Otras formas de documentacion.
        "README.md",
        "CHANGELOG.md",
        "documentation/setup.txt",
        "website/docs/intro.mdx",
        "guides/quickstart.adoc",
        "notebooks/demo.ipynb",
    ],
)
def test_una_clave_en_la_documentacion_no_es_critica(ruta):
    """Los tutoriales ENSENAN a configurar claves, asi que las escriben."""
    assert _is_test_fixture(ruta) is True


@pytest.mark.parametrize(
    "ruta",
    ["tests/fixtures/key.pem", "spec/support/token.txt", "examples/config.js"],
)
def test_una_clave_en_material_de_prueba_tampoco(ruta):
    assert _is_test_fixture(ruta) is True


@pytest.mark.parametrize(
    "ruta",
    [
        "src/config.py",
        "app/settings.py",
        "backend/app/core/security.py",
        "lib/database.js",
        "config/production.yml",
    ],
)
def test_una_clave_en_codigo_de_verdad_si_es_critica(ruta):
    """Lo que no puede pasar es que el filtro se coma un secreto real."""
    assert _is_test_fixture(ruta) is False


def test_sin_ruta_no_se_rebaja_la_gravedad():
    """Ante la duda, se trata como real."""
    assert _is_test_fixture(None) is False
    assert _is_test_fixture("") is False


# --------------------------------------------------------------------------
# Dependencias: pyproject.toml es el estandar moderno de Python
# --------------------------------------------------------------------------


def _con_fichero(nombre: str, contenido: str) -> Path:
    carpeta = Path(tempfile.mkdtemp())
    (carpeta / nombre).write_text(contenido, encoding="utf-8")
    return carpeta


def test_se_leen_las_dependencias_de_pyproject():
    """Sin esto, Flask, FastAPI o Django reportaban cero dependencias y se
    quedaban sin analisis de vulnerabilidades."""
    carpeta = _con_fichero(
        "pyproject.toml",
        """
[project]
name = "demo"
dependencies = ["flask>=3.0", "werkzeug==3.0.1"]
""",
    )
    nombres = {p["name"] for p in _collect_packages(carpeta)}
    assert nombres == {"flask", "werkzeug"}


def test_las_dependencias_opcionales_tambien_cuentan():
    carpeta = _con_fichero(
        "pyproject.toml",
        """
[project]
dependencies = ["flask"]
[project.optional-dependencies]
dev = ["pytest==8.0.0"]
""",
    )
    assert "pytest" in {p["name"] for p in _collect_packages(carpeta)}


def test_solo_se_consulta_la_version_cuando_es_exacta():
    """Un rango como >=3.0 puede resolver a cualquier cosa; preguntar por una
    version concreta daria una respuesta que no corresponde a lo instalado."""
    carpeta = _con_fichero(
        "pyproject.toml",
        """
[project]
dependencies = ["flask>=3.0", "werkzeug==3.0.1"]
""",
    )
    porNombre = {p["name"]: p["version"] for p in _collect_packages(carpeta)}
    assert porNombre["werkzeug"] == "3.0.1"
    assert porNombre["flask"] is None


def test_se_entiende_el_formato_de_poetry():
    """Poetry no sigue PEP 621: declara las suyas como tabla."""
    carpeta = _con_fichero(
        "pyproject.toml",
        """
[tool.poetry.dependencies]
python = "^3.11"
requests = "==2.31.0"
""",
    )
    paquetes = {p["name"]: p["version"] for p in _collect_packages(carpeta)}
    assert paquetes["requests"] == "2.31.0"
    # El interprete no es un paquete instalable.
    assert "python" not in paquetes


def test_un_marcador_de_entorno_no_estropea_el_nombre():
    carpeta = _con_fichero(
        "pyproject.toml",
        """
[project]
dependencies = ['click; python_version>="3.8"']
""",
    )
    assert {p["name"] for p in _collect_packages(carpeta)} == {"click"}


def test_un_pyproject_ilegible_no_tumba_el_analisis():
    carpeta = _con_fichero("pyproject.toml", "esto no es TOML valido [[[")
    assert _collect_packages(carpeta) == []


def test_sin_pyproject_no_pasa_nada():
    assert _collect_packages(Path(tempfile.mkdtemp())) == []


# --------------------------------------------------------------------------
# Clonado: la rama guardada puede haber quedado obsoleta
# --------------------------------------------------------------------------


def test_se_reconoce_que_la_rama_ya_no_existe():
    """Renombrar master a main es habitual, y el nombre guardado se queda
    viejo. Negarse a analizar por eso seria absurdo."""
    assert _branch_not_found("fatal: Remote branch main not found in upstream origin") is True


@pytest.mark.parametrize(
    "error",
    [
        "fatal: could not resolve host: github.com",
        "fatal: Authentication failed",
        "fatal: repository not found",
        "",
    ],
)
def test_otros_fallos_de_clon_no_se_confunden(error):
    """Reintentar sin rama ante un fallo de red solo duplicaria la espera para
    acabar fallando igual."""
    assert _branch_not_found(error) is False

# --------------------------------------------------------------------------
# Notas de referencia con analisis reales
# --------------------------------------------------------------------------
#
# La instantanea son analisis reales de los tres proyectos de referencia,
# hechos el 2026-10-29: sus metricas, la nota de cada dimension y la gravedad
# de los hallazgos. Asi la escala se comprueba con datos medidos sin clonar
# nada en cada ejecucion.
#
# Recalibracion de octubre de 2026: la actividad del proyecto salio de la
# nota (no es ISO/IEC 25010; puntuaba estrellas y forks). Las tres bajan,
# porque las tres tenian la actividad por encima de su media. Ver
# docs/ISO_25010_MAPPING.md.

CALIBRACION = json.loads(
    (Path(__file__).parent / "fixtures" / "calibracion_2026_10.json").read_text(encoding="utf-8")
)

# Pesos de antes, con la actividad dentro: comprueban que la instantanea
# reproduce las notas que se publicaron y que el cambio es solo ese.
PESOS_CON_ACTIVIDAD = {
    "functional_suitability": 0.15, "reliability": 0.20, "security": 0.20,
    "maintainability": 0.20, "portability": 0.10, "project_activity": 0.15,
}


def _hallazgos(repo):
    return [
        FindingData(type="security", severity=s, title="", description="")
        for s in CALIBRACION[repo]["severities"]
    ]


@pytest.mark.parametrize(
    "repo, antes, ahora",
    [
        # Antes: las notas publicadas en el README. Ahora: sin la actividad.
        ("pallets/flask", 64.0, 57.65),
        ("axios/axios", 68.8, 63.29),
        ("octocat/Hello-World", 7.35, 2.12),
    ],
)
def test_recalibracion_con_los_analisis_reales(repo, antes, ahora):
    dims = CALIBRACION[repo]["dimensions"]
    hallazgos = _hallazgos(repo)

    con_actividad = sum(PESOS_CON_ACTIVIDAD[d] * s for d, s in dims.items()) / sum(PESOS_CON_ACTIVIDAD[d] for d in dims)
    assert round(con_actividad, 2) == antes
    assert calculate_overall_score(dims, hallazgos) == ahora


def test_la_escala_sigue_discriminando():
    """Las referencias siguen lejos del repositorio vacio."""
    nota = {
        r: calculate_overall_score(CALIBRACION[r]["dimensions"], _hallazgos(r))
        for r in CALIBRACION
        if not r.startswith("_")
    }
    assert nota["axios/axios"] > nota["pallets/flask"] > 50 > 10 > nota["octocat/Hello-World"]
