"""Clonado superficial y efimero de repositorios publicos.

El repositorio del usuario es entrada no confiable: la rama y la URL se
validan contra patrones estrictos antes de llegar a `git`, porque git acepta
argumentos como `--upload-pack=` y transportes como `ext::` que ejecutan
comandos arbitrarios.
"""

import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

_BRANCH_PATTERN = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._/-]{0,254}$")
_CLONE_URL_PATTERN = re.compile(r"^https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+(\.git)?$")

CLONE_TIMEOUT_SECONDS = 120


def validate_branch(branch: str) -> str:
    # El patron ya excluye la cadena vacia y cualquier cosa que empiece por
    # "-", que es como git interpreta un argumento en vez de una rama.
    if not _BRANCH_PATTERN.match(branch or ""):
        raise ValueError(f"nombre de rama no valido: {branch!r}")
    if ".." in branch:
        raise ValueError(f"nombre de rama no valido: {branch!r}")
    return branch


def validate_clone_url(url: str) -> str:
    if not _CLONE_URL_PATTERN.match(url or ""):
        raise ValueError(f"URL de clonado no permitida: {url!r}")
    return url


def _restricted_git_env() -> dict[str, str]:
    """Entorno minimo para invocar git sin prompts de credenciales ni acceso
    a las claves SSH del host.

    El brief original usa `PATH=/usr/bin:/bin`, una lista de rutas POSIX que
    no existe en Windows y rompe la resolucion del ejecutable `git`. Aqui se
    conserva la intencion (deshabilitar prompts, no heredar variables como
    SSH_AUTH_SOCK) pero se reenvia el PATH real del host, mas SYSTEMROOT que
    Windows necesita para resolver DLLs del sistema durante la ejecucion de
    procesos hijos.
    """
    env = {
        "GIT_TERMINAL_PROMPT": "0",
        "PATH": os.environ.get("PATH", ""),
    }
    systemroot = os.environ.get("SYSTEMROOT")
    if systemroot:
        env["SYSTEMROOT"] = systemroot
    return env


def _force_remove_readonly(func, path, _err) -> None:
    """rmtree error handler.

    git marks files under `.git/objects/pack/` read-only on every platform.
    On POSIX, that doesn't block `shutil.rmtree`: unlinking a file is
    governed by the *directory's* write permission, not the file's own
    mode. On Windows the read-only attribute is enforced by the filesystem
    itself and blocks deletion outright, so plain `ignore_errors=True`
    silently leaves the whole clone on disk -- defeating the point of this
    module. Clear the attribute and retry once; if it still fails, give up
    silently so cleanup never masks the caller's real exception.
    """
    try:
        os.chmod(path, stat.S_IWRITE)
        func(path)
    except OSError:
        pass


def _cleanup_clone_dir(temp_dir: Path) -> None:
    if sys.version_info >= (3, 12):
        shutil.rmtree(temp_dir, onexc=_force_remove_readonly)
    else:
        shutil.rmtree(temp_dir, onerror=_force_remove_readonly)


@contextmanager
def clone_repository(clone_url: str, branch: str) -> Iterator[Path]:
    """Clona de forma superficial en un directorio temporal y lo borra siempre."""

    safe_url = validate_clone_url(clone_url)
    safe_branch = validate_branch(branch)

    temp_dir = Path(tempfile.mkdtemp(prefix="qaliti-clone-"))
    try:
        completed = _run_clone(safe_url, temp_dir, safe_branch)

        # Si la rama guardada ya no existe, se reintenta dejando que git use la
        # que el remoto declare por defecto. Pasa mas de lo que parece: el
        # nombre se guardo al listar el repositorio y desde entonces pudieron
        # renombrar master a main, o cambiar la rama principal. Fallar ahi
        # significaria negarse a analizar un repositorio perfectamente valido
        # por un dato caducado.
        if completed.returncode != 0 and _branch_not_found(completed.stderr):
            _cleanup_clone_dir(temp_dir)
            temp_dir = Path(tempfile.mkdtemp(prefix="qaliti-clone-"))
            completed = _run_clone(safe_url, temp_dir, None)

        if completed.returncode != 0:
            raise RuntimeError(f"no se pudo clonar el repositorio: {completed.stderr[:300]}")
        yield temp_dir / "repo"
    finally:
        _cleanup_clone_dir(temp_dir)


def _run_clone(safe_url: str, temp_dir: Path, safe_branch: str | None):
    """Clon superficial. Sin `branch`, git usa la rama por defecto del remoto."""
    orden = ["git", "clone", "--depth", "1", "--single-branch"]
    if safe_branch:
        orden += ["--branch", safe_branch]
    orden += [
        "--config", "core.askPass=true",   # nunca pedir credenciales
        safe_url,
        str(temp_dir / "repo"),
    ]
    return subprocess.run(
        orden,
        capture_output=True,
        text=True,
        timeout=CLONE_TIMEOUT_SECONDS,
        shell=False,
        check=False,
        env=_restricted_git_env(),
    )


def _branch_not_found(stderr: str) -> bool:
    """Distingue "esa rama no existe" de cualquier otro fallo del clon.

    Importa acertar: reintentar sin rama ante un error de red o de permisos
    solo duplicaria la espera para acabar fallando igual.
    """
    texto = (stderr or "").lower()
    return "remote branch" in texto and "not found" in texto


def read_head_commit(repo_dir: Path) -> tuple[str, str]:
    completed = subprocess.run(
        ["git", "-C", str(repo_dir), "log", "-1", "--format=%H%n%s"],
        capture_output=True,
        text=True,
        timeout=30,
        shell=False,
        check=False,
    )
    if completed.returncode != 0:
        return "", ""
    lines = completed.stdout.splitlines()
    return (lines[0] if lines else "", lines[1] if len(lines) > 1 else "")
