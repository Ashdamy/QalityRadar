"""Ejecuta herramientas de analisis sobre codigo ajeno dentro de un contenedor
efimero y sin red. El codigo analizado nunca se ejecuta: solo se lee, y el
directorio se monta en solo lectura.
"""

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

# Flags de seguridad no negociables. Se definen aqui como constante para que
# los tests puedan comprobarlas y para que ninguna ruta de codigo las arme
# dinamicamente a partir de entrada del usuario.
SANDBOX_FLAGS: tuple[str, ...] = (
    "--rm",
    "--network=none",
    "--read-only",
    "--cap-drop=ALL",
    "--security-opt=no-new-privileges",
    "--memory=512m",
    "--memory-swap=512m",
    "--cpus=0.5",
    "--pids-limit=100",
    "--user", "65534:65534",  # nobody:nogroup
)

_IMAGE_PATTERN = re.compile(r"^[a-zA-Z0-9._/-]+(:[a-zA-Z0-9._-]+)?$")

WORKDIR_IN_CONTAINER = "/repo"


@dataclass(frozen=True)
class SandboxResult:
    stdout: str
    stderr: str
    exit_code: int
    timed_out: bool


def build_docker_command(image: str, command: list[str], repo_dir: Path) -> list[str]:
    if not _IMAGE_PATTERN.match(image):
        raise ValueError(f"nombre de imagen no valido: {image!r}")
    repo_dir = Path(repo_dir)
    if not repo_dir.is_dir():
        raise ValueError(f"directorio de repositorio inexistente: {repo_dir}")

    return [
        "docker", "run",
        *SANDBOX_FLAGS,
        "--volume", f"{repo_dir.resolve()}:{WORKDIR_IN_CONTAINER}:ro",
        "--workdir", WORKDIR_IN_CONTAINER,
        # tmpfs para que las herramientas puedan escribir temporales pese al
        # sistema de archivos en solo lectura.
        "--tmpfs", "/tmp:rw,noexec,nosuid,size=64m",
        image,
        *command,
    ]


def run_in_sandbox(
    image: str,
    command: list[str],
    repo_dir: Path,
    timeout_seconds: int = 600,
) -> SandboxResult:
    docker_command = build_docker_command(image, command, repo_dir)
    try:
        completed = subprocess.run(
            docker_command,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            shell=False,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        return SandboxResult(
            stdout=exc.stdout or "",
            stderr=exc.stderr or "",
            exit_code=-1,
            timed_out=True,
        )
    return SandboxResult(
        stdout=completed.stdout,
        stderr=completed.stderr,
        exit_code=completed.returncode,
        timed_out=False,
    )
