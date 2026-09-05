"""El repositorio analizado lo escribe un desconocido, incluidos sus enlaces.

Estos analizadores corren **en el worker, no en el contenedor aislado**, asi
que lo que alcanzan es la maquina de verdad: el `.env` con el JWT_SECRET, la
clave de cifrado y las credenciales de la base de datos.

La regla del proyecto es que el codigo analizado nunca se ejecuta. Pero si se
lee, y leer el archivo equivocado basta para filtrarlo.
"""

import tempfile
from pathlib import Path

import pytest

from app.services.analysis_service import _safe_error_message
from app.services.repo_service import ErrorDeClonado
from app.analyzers.base import (
    MAX_BYTES_POR_ARCHIVO,
    archivos_del_repositorio,
    esta_dentro,
    leer_texto,
)


def _se_pueden_crear_enlaces() -> bool:
    """Windows exige privilegios para crear enlaces simbolicos.

    La comprobacion se hace de verdad, creando uno: preguntar por el sistema
    operativo daria una respuesta equivocada en un Windows con el modo
    desarrollador activado.
    """
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        (base / "objetivo").write_text("x")
        try:
            (base / "enlace").symlink_to(base / "objetivo")
        except OSError:
            return False
    return True


sin_enlaces = pytest.mark.skipif(
    not _se_pueden_crear_enlaces(),
    reason="este sistema no permite crear enlaces simbolicos sin privilegios",
)


# --------------------------------------------------------------------------
# La comprobacion de contencion, que no necesita enlaces
# --------------------------------------------------------------------------


def test_un_archivo_del_repositorio_esta_dentro(tmp_path):
    (tmp_path / "codigo.py").write_text("print(1)")
    assert esta_dentro(tmp_path / "codigo.py", tmp_path)


def test_un_archivo_de_fuera_no_esta_dentro(tmp_path):
    fuera = tmp_path.parent / "fuera.env"
    fuera.write_text("JWT_SECRET=no")
    try:
        assert not esta_dentro(fuera, tmp_path)
    finally:
        fuera.unlink()


def test_subir_por_puntos_no_cuenta_como_dentro(tmp_path):
    assert not esta_dentro(tmp_path / ".." / "vecino.env", tmp_path)


# --------------------------------------------------------------------------
# El ataque real
# --------------------------------------------------------------------------


@sin_enlaces
def test_un_enlace_a_un_archivo_de_fuera_no_se_recorre(tmp_path):
    """`config.py -> /app/.env` hacia que el analizador leyera los secretos del
    worker y despues informara de lo que encontro dentro."""
    secreto = tmp_path / "secreto.env"
    secreto.write_text("JWT_SECRET=el-secreto-del-worker")
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "config.py").symlink_to(secreto)
    (repo / "legitimo.py").write_text("print('hola')")

    recorridos = list(archivos_del_repositorio(repo))

    assert [p.name for p in recorridos] == ["legitimo.py"]


@sin_enlaces
def test_un_directorio_enlazado_tampoco_se_recorre(tmp_path):
    fuera = tmp_path / "fuera"
    fuera.mkdir()
    (fuera / "secreto.env").write_text("ENCRYPTION_KEY=clave")
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "vendor").symlink_to(fuera, target_is_directory=True)

    recorridos = list(archivos_del_repositorio(repo))

    assert recorridos == []


@sin_enlaces
def test_un_enlace_roto_no_hace_fallar_el_analisis(tmp_path):
    """Un repositorio con un enlace a un archivo que no existe es corriente:
    no debe tumbar el analisis entero."""
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "roto.py").symlink_to(tmp_path / "no-existe")
    (repo / "bueno.py").write_text("print('hola')")

    assert [p.name for p in archivos_del_repositorio(repo)] == ["bueno.py"]


def test_los_archivos_normales_si_se_recorren(tmp_path):
    """El arreglo no puede dejar al analizador sin nada que leer."""
    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    (repo / "README.md").write_text("# hola")
    (repo / "src" / "app.py").write_text("print(1)")

    nombres = sorted(p.name for p in archivos_del_repositorio(repo))

    assert nombres == ["README.md", "app.py", "src"]


# --------------------------------------------------------------------------
# Tamano de lo que se lee
# --------------------------------------------------------------------------


def test_un_archivo_enorme_no_entra_entero_en_memoria(tmp_path):
    """Los analizadores limitan cuantos archivos leen, pero no cuanto pesa
    cada uno: un repositorio con un solo archivo gigante tumbaba el worker, y
    con el todos los analisis en curso."""
    gordo = tmp_path / "datos.py"
    gordo.write_bytes(b"a" * (MAX_BYTES_POR_ARCHIVO + 500_000))

    texto = leer_texto(gordo)

    assert len(texto) == MAX_BYTES_POR_ARCHIVO


def test_una_sola_linea_gigante_tampoco(tmp_path):
    """El caso que se colaba: recorrer linea a linea acota la memoria salvo
    cuando el archivo entero es una unica linea."""
    gordo = tmp_path / "minificado.js"
    gordo.write_bytes(b"x" * (MAX_BYTES_POR_ARCHIVO * 2))

    assert len(leer_texto(gordo)) == MAX_BYTES_POR_ARCHIVO


def test_un_archivo_normal_se_lee_entero(tmp_path):
    codigo = tmp_path / "app.py"
    codigo.write_text("print('hola')")

    assert leer_texto(codigo) == "print('hola')"


def test_un_archivo_ilegible_no_aborta_el_analisis(tmp_path):
    assert leer_texto(tmp_path / "no-existe.py") == ""


def test_un_caracter_partido_por_el_corte_no_revienta(tmp_path):
    """El tope cae a mitad de un caracter multibyte mas veces de las que
    parece: si eso lanzara, un repositorio con acentos tumbaria el analisis."""
    archivo = tmp_path / "acentos.py"
    archivo.write_bytes(b"a" * (MAX_BYTES_POR_ARCHIVO - 1) + "ñ".encode())

    texto = leer_texto(archivo)

    assert len(texto) == MAX_BYTES_POR_ARCHIVO
    assert texto.endswith("�")


# --------------------------------------------------------------------------
# Lo que se le cuenta al usuario cuando un analisis falla
# --------------------------------------------------------------------------


def test_el_fallo_de_una_libreria_no_se_le_ensena_a_nadie():
    """El criterio era al reves: se mostraba `str(exc)` salvo que trajera una
    ruta temporal. Un fallo de la base de datos llega con el host, el usuario y
    a veces la contrasena dentro del mensaje."""
    escapado = Exception(
        "connection to server at 10.0.0.5, port 5432 failed: "
        "password authentication failed for user qalitiradar"
    )

    mensaje = _safe_error_message(escapado)

    assert "10.0.0.5" not in mensaje
    assert "qalitiradar" not in mensaje
    assert mensaje == "el analisis fallo por un error inesperado"


def test_un_error_propio_si_explica_lo_que_paso():
    """Si no, el usuario no sabe que su repositorio no existe o que la rama
    cambio de nombre, y no puede hacer nada al respecto."""
    mensaje = _safe_error_message(ErrorDeClonado("no se pudo clonar el repositorio: not found"))

    assert "no se pudo clonar el repositorio" in mensaje


def test_ni_los_propios_ensenan_la_ruta_del_clon():
    mensaje = _safe_error_message(
        ErrorDeClonado("no se pudo clonar: /tmp/qaliti-clone-abc123/repo")
    )

    assert "qaliti-clone-" not in mensaje
    assert "/tmp/" not in mensaje
