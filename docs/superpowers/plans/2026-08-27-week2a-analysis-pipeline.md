# Semana 2A — Motor de análisis: sandbox y primer resultado real

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Que un usuario pueda pulsar "Analizar" sobre uno de sus repositorios públicos y obtener, de punta a punta, un resultado real persistido: hallazgos concretos y una puntuación por dimensión.

**Architecture:** El worker Celery corre en el host y orquesta cada análisis: clona el repositorio de forma superficial en un directorio temporal, lanza un contenedor Docker efímero y sin red que ejecuta analizadores puramente estáticos sobre ese directorio en solo-lectura, recoge su salida JSON, la convierte en `Finding`/`Dimension` y calcula la puntuación ISO 25010. El código del usuario nunca se ejecuta: solo se lee.

**Tech Stack:** Python 3.11+, Celery 5.4, Redis, SQLAlchemy 2.0 (sync), FastAPI, Docker SDK vía `subprocess` con listas de argumentos.

**Spec:** [`../../../context/claude.md`](../../../context/claude.md) §4 y §6, [`../../ARCHITECTURE.md`](../../ARCHITECTURE.md) §3.1 y §4.1, [`../../DATA_MODEL.md`](../../DATA_MODEL.md) §3.4-§3.6

## Global Constraints

- **El código analizado NUNCA se ejecuta.** Nada de `npm install`, `pip install`, build ni tests del repositorio del usuario. Todos los analizadores son estáticos: leen archivos. Esta es una decisión de diseño, no solo de aislamiento.
- **El worker corre en el host**, no dentro de un contenedor, para hablar con el demonio Docker sin montar `/var/run/docker.sock` en ningún contenedor.
- **Ningún comando se construye por interpolación de texto.** Siempre `subprocess.run([...], shell=False)` con lista de argumentos. Toda entrada que llegue a un comando (rama, URL de clonado) se valida antes contra una expresión regular estricta.
- Flags obligatorios e inmutables del contenedor de análisis: `--rm --network=none --read-only --cap-drop=ALL --security-opt=no-new-privileges --memory=512m --memory-swap=512m --cpus=0.5 --pids-limit=100 --user 65534:65534`. El directorio del repositorio se monta **solo lectura** (`:ro`).
- Timeout duro de 10 minutos por análisis (`task_time_limit=600`, `task_soft_time_limit=570`).
- El clon temporal se borra **siempre**, con éxito o con error. Nunca se persiste código fuente: en base de datos solo van métricas y hallazgos.
- Solo repositorios **públicos** (constraint del MVP). Se rechaza cualquier repo con `is_private = true`.
- Todas las funciones son **síncronas** (`def`, nunca `async def`).

---

### Task 1: Ejecutor de sandbox

**Files:**
- Create: `backend/app/utils/sandbox.py`
- Test: `backend/tests/test_sandbox.py`

**Interfaces:**
- Produces: `run_in_sandbox(image: str, command: list[str], repo_dir: Path, timeout_seconds: int = 600) -> SandboxResult`, donde `SandboxResult` es un dataclass con `stdout: str`, `stderr: str`, `exit_code: int`, `timed_out: bool`. Lo consumen las Tasks 3-5.
- Produces: `SANDBOX_FLAGS: tuple[str, ...]` — la lista fija de flags de seguridad, expuesta para que los tests la comprueben.

- [ ] **Step 1: Escribir los tests (fallan porque el módulo no existe)**

```python
# backend/tests/test_sandbox.py
from pathlib import Path

import pytest

from app.utils.sandbox import SANDBOX_FLAGS, build_docker_command, run_in_sandbox


def test_security_flags_are_all_present():
    flags = " ".join(SANDBOX_FLAGS)
    for required in [
        "--rm", "--network=none", "--read-only", "--cap-drop=ALL",
        "--security-opt=no-new-privileges", "--memory=512m", "--memory-swap=512m",
        "--cpus=0.5", "--pids-limit=100", "--user", "65534:65534",
    ]:
        assert required in flags


def test_repo_directory_is_mounted_read_only(tmp_path):
    command = build_docker_command("qaliti/analyzer:latest", ["echo", "hola"], tmp_path)
    mount = next(arg for arg in command if arg.startswith(f"{tmp_path}:"))
    assert mount.endswith(":ro")


def test_command_is_a_list_never_a_string(tmp_path):
    command = build_docker_command("qaliti/analyzer:latest", ["echo", "hola"], tmp_path)
    assert isinstance(command, list)
    assert all(isinstance(part, str) for part in command)
    assert command[0] == "docker"


def test_rejects_image_name_with_shell_metacharacters(tmp_path):
    with pytest.raises(ValueError, match="imagen"):
        build_docker_command("qaliti/analyzer; rm -rf /", ["echo"], tmp_path)


def test_rejects_nonexistent_repo_directory():
    with pytest.raises(ValueError, match="directorio"):
        build_docker_command("qaliti/analyzer:latest", ["echo"], Path("/no/existe/jamas"))
```

- [ ] **Step 2: Ejecutar y verificar que falla**

Run: `cd backend && python -m pytest tests/test_sandbox.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.utils.sandbox'`

- [ ] **Step 3: Implementar `backend/app/utils/sandbox.py`**

```python
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
```

- [ ] **Step 4: Ejecutar y verificar que pasa**

Run: `cd backend && python -m pytest tests/test_sandbox.py -q`
Expected: PASS (5 tests)

- [ ] **Step 5: Verificación real contra Docker**

Escribir un test marcado que solo corra si Docker está disponible, comprobando que el aislamiento es real y no solo declarado:

```python
# añadir a backend/tests/test_sandbox.py
import shutil

docker_available = pytest.mark.skipif(
    shutil.which("docker") is None, reason="Docker no disponible"
)


@docker_available
def test_sandbox_has_no_network_access(tmp_path):
    result = run_in_sandbox(
        "alpine:3.20",
        ["sh", "-c", "wget -q -T 3 -O- https://example.com || echo SIN_RED"],
        tmp_path,
        timeout_seconds=60,
    )
    assert "SIN_RED" in result.stdout


@docker_available
def test_sandbox_cannot_write_to_mounted_repo(tmp_path):
    (tmp_path / "existente.txt").write_text("original")
    result = run_in_sandbox(
        "alpine:3.20",
        ["sh", "-c", "echo modificado > /repo/existente.txt || echo SOLO_LECTURA"],
        tmp_path,
        timeout_seconds=60,
    )
    assert "SOLO_LECTURA" in result.stdout
    assert (tmp_path / "existente.txt").read_text() == "original"
```

Run: `cd backend && python -m pytest tests/test_sandbox.py -q`
Expected: PASS — y estos dos tests son la prueba de que el aislamiento funciona de verdad.

- [ ] **Step 6: Commit**

```bash
git add backend/app/utils/sandbox.py backend/tests/test_sandbox.py
git commit -m "feat: ejecutor de sandbox con aislamiento verificado"
```

---

### Task 2: Clonado seguro del repositorio

**Files:**
- Create: `backend/app/services/repo_service.py`
- Test: `backend/tests/test_repo_service.py`

**Interfaces:**
- Consumes: nada de tasks anteriores.
- Produces: `clone_repository(clone_url: str, branch: str) -> Iterator[Path]` — un context manager que clona de forma superficial en un directorio temporal, lo cede, y **siempre** lo borra al salir. Lo consume la Task 6.
- Produces: `read_head_commit(repo_dir: Path) -> tuple[str, str]` → `(commit_hash, commit_message)`.
- Produces: `validate_branch(branch: str) -> str` y `validate_clone_url(url: str) -> str`, que lanzan `ValueError` ante entradas peligrosas.

- [ ] **Step 1: Escribir los tests (fallan)**

```python
# backend/tests/test_repo_service.py
import pytest

from app.services.repo_service import validate_branch, validate_clone_url


@pytest.mark.parametrize("branch", ["main", "develop", "feature/algo-nuevo", "release-1.2.3"])
def test_accepts_normal_branch_names(branch):
    assert validate_branch(branch) == branch


@pytest.mark.parametrize(
    "branch",
    ["main; rm -rf /", "--upload-pack=malicioso", "-oProxyCommand=x", "rama con espacios", ""],
)
def test_rejects_dangerous_branch_names(branch):
    with pytest.raises(ValueError):
        validate_branch(branch)


@pytest.mark.parametrize(
    "url",
    ["https://github.com/usuario/repo.git", "https://github.com/usuario/repo"],
)
def test_accepts_github_https_urls(url):
    assert validate_clone_url(url) == url


@pytest.mark.parametrize(
    "url",
    [
        "git@github.com:usuario/repo.git",       # ssh: usaria claves del host
        "file:///etc/passwd",                    # lectura del sistema de archivos local
        "ext::sh -c whoami",                     # transporte ext = ejecucion de comandos
        "http://github.com/usuario/repo",        # sin cifrar
        "https://gitlab.com/usuario/repo",       # fuera del MVP
    ],
)
def test_rejects_dangerous_clone_urls(url):
    with pytest.raises(ValueError):
        validate_clone_url(url)
```

- [ ] **Step 2: Ejecutar y verificar que falla**

Run: `cd backend && python -m pytest tests/test_repo_service.py -q`
Expected: FAIL — módulo inexistente.

- [ ] **Step 3: Implementar `backend/app/services/repo_service.py`**

```python
"""Clonado superficial y efimero de repositorios publicos.

El repositorio del usuario es entrada no confiable: la rama y la URL se
validan contra patrones estrictos antes de llegar a `git`, porque git acepta
argumentos como `--upload-pack=` y transportes como `ext::` que ejecutan
comandos arbitrarios.
"""

import re
import shutil
import subprocess
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


@contextmanager
def clone_repository(clone_url: str, branch: str) -> Iterator[Path]:
    """Clona de forma superficial en un directorio temporal y lo borra siempre."""

    safe_url = validate_clone_url(clone_url)
    safe_branch = validate_branch(branch)

    temp_dir = Path(tempfile.mkdtemp(prefix="qaliti-clone-"))
    try:
        completed = subprocess.run(
            [
                "git", "clone",
                "--depth", "1",
                "--single-branch",
                "--branch", safe_branch,
                "--config", "core.askPass=true",   # nunca pedir credenciales
                safe_url,
                str(temp_dir / "repo"),
            ],
            capture_output=True,
            text=True,
            timeout=CLONE_TIMEOUT_SECONDS,
            shell=False,
            check=False,
            env={"GIT_TERMINAL_PROMPT": "0", "PATH": "/usr/bin:/bin"},
        )
        if completed.returncode != 0:
            raise RuntimeError(f"no se pudo clonar el repositorio: {completed.stderr[:300]}")
        yield temp_dir / "repo"
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


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
```

- [ ] **Step 4: Ejecutar y verificar que pasa**

Run: `cd backend && python -m pytest tests/test_repo_service.py -q`
Expected: PASS

- [ ] **Step 5: Añadir un test de integración real y de limpieza**

```python
# añadir a backend/tests/test_repo_service.py
import shutil as _shutil
from pathlib import Path

from app.services.repo_service import clone_repository, read_head_commit

git_available = pytest.mark.skipif(_shutil.which("git") is None, reason="git no disponible")


@git_available
def test_clones_a_real_public_repo_and_cleans_up():
    captured: Path | None = None
    with clone_repository("https://github.com/octocat/Hello-World", "master") as repo_dir:
        captured = repo_dir
        assert (repo_dir / "README").exists() or (repo_dir / "README.md").exists()
        commit_hash, _ = read_head_commit(repo_dir)
        assert len(commit_hash) == 40
    # El directorio temporal debe desaparecer al salir del context manager.
    assert captured is not None and not captured.exists()


@git_available
def test_temp_directory_is_removed_even_when_body_raises():
    captured: Path | None = None
    with pytest.raises(RuntimeError, match="fallo de prueba"):
        with clone_repository("https://github.com/octocat/Hello-World", "master") as repo_dir:
            captured = repo_dir
            raise RuntimeError("fallo de prueba")
    assert captured is not None and not captured.exists()
```

Run: `cd backend && python -m pytest tests/test_repo_service.py -q`
Expected: PASS — el segundo test es el que garantiza que no dejamos código ajeno en disco cuando algo falla.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/repo_service.py backend/tests/test_repo_service.py
git commit -m "feat: clonado seguro y efimero de repositorios"
```

---

### Task 3: Imagen del analizador y contrato de analizadores

**Files:**
- Create: `analyzer/Dockerfile`
- Create: `backend/app/analyzers/__init__.py`
- Create: `backend/app/analyzers/base.py`
- Test: `backend/tests/test_analyzer_base.py`

**Interfaces:**
- Produces: `AnalyzerResult` (dataclass) con `dimension: str`, `metrics: dict`, `findings: list[FindingData]`.
- Produces: `FindingData` (dataclass) con `type: str`, `severity: str`, `title: str`, `description: str`, `file_path: str | None`, `recommendation: str | None`.
- Produces: `Analyzer` (Protocol) con `name: str` y `analyze(repo_dir: Path) -> AnalyzerResult`.
- Produces: imagen Docker `qaliti/analyzer:latest` con Python 3.11, `gitleaks` y `semgrep` preinstalados (Semgrep lo usa la Semana 2B, pero la imagen se construye ya para no rehacerla).

- [ ] **Step 1: Escribir `analyzer/Dockerfile`**

```dockerfile
FROM python:3.11-slim

# Gitleaks: deteccion de secretos. Version fijada para que el analisis sea
# reproducible entre ejecuciones.
ARG GITLEAKS_VERSION=8.21.2
RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates curl \
 && curl -sSL "https://github.com/gitleaks/gitleaks/releases/download/v${GITLEAKS_VERSION}/gitleaks_${GITLEAKS_VERSION}_linux_x64.tar.gz" \
    | tar -xz -C /usr/local/bin gitleaks \
 && apt-get purge -y curl \
 && apt-get autoremove -y \
 && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir semgrep==1.95.0

# Se ejecuta como nobody; el sandbox tambien lo fuerza con --user.
USER 65534:65534
WORKDIR /repo
```

- [ ] **Step 2: Construir la imagen y verificar las herramientas**

Run:
```bash
docker build -t qaliti/analyzer:latest ./analyzer
docker run --rm qaliti/analyzer:latest gitleaks version
docker run --rm qaliti/analyzer:latest semgrep --version
```
Expected: ambas imprimen su versión sin error.

- [ ] **Step 3: Escribir el test del contrato (falla)**

```python
# backend/tests/test_analyzer_base.py
from app.analyzers.base import AnalyzerResult, FindingData


def test_finding_data_carries_the_evidence_fields():
    finding = FindingData(
        type="documentation",
        severity="medium",
        title="Falta README",
        description="El repositorio no tiene README.md",
        file_path=None,
        recommendation="Agrega un README con instalacion y uso",
    )
    assert finding.severity == "medium"
    assert finding.recommendation


def test_analyzer_result_defaults_to_no_findings():
    result = AnalyzerResult(dimension="maintainability", metrics={"archivos": 10})
    assert result.findings == []
    assert result.metrics["archivos"] == 10
```

Run: `cd backend && python -m pytest tests/test_analyzer_base.py -q`
Expected: FAIL — módulo inexistente.

- [ ] **Step 4: Implementar `backend/app/analyzers/base.py`**

```python
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
    recommendation: str | None = None


@dataclass
class AnalyzerResult:
    dimension: str
    metrics: dict
    findings: list[FindingData] = field(default_factory=list)


class Analyzer(Protocol):
    name: str

    def analyze(self, repo_dir: Path) -> AnalyzerResult: ...
```

- [ ] **Step 5: Crear `backend/app/analyzers/__init__.py`**

```python
from app.analyzers.base import Analyzer, AnalyzerResult, FindingData

__all__ = ["Analyzer", "AnalyzerResult", "FindingData"]
```

- [ ] **Step 6: Ejecutar y verificar que pasa**

Run: `cd backend && python -m pytest tests/test_analyzer_base.py -q`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add analyzer/Dockerfile backend/app/analyzers backend/tests/test_analyzer_base.py
git commit -m "feat: imagen del analizador y contrato comun"
```

---

### Task 4: Analizadores de estructura y documentación

**Files:**
- Create: `backend/app/analyzers/repository/__init__.py`
- Create: `backend/app/analyzers/repository/structure.py`
- Create: `backend/app/analyzers/repository/documentation.py`
- Test: `backend/tests/test_structure_analyzer.py`
- Test: `backend/tests/test_documentation_analyzer.py`

**Interfaces:**
- Consumes: `AnalyzerResult`, `FindingData` (Task 3).
- Produces: `StructureAnalyzer` (dimensión `maintainability`) — detecta lenguajes por extensión, cuenta archivos por tipo, e identifica si el proyecto es frontend, backend o fullstack.
- Produces: `DocumentationAnalyzer` (dimensión `functional_suitability`) — comprueba README (y su longitud), LICENSE, CONTRIBUTING, CHANGELOG y documentación de arquitectura.

Ambos leen el árbol de archivos directamente desde el worker (no necesitan el sandbox: solo listan nombres y leen texto, sin ejecutar nada). El sandbox se reserva para Gitleaks y Semgrep en la Semana 2B.

- [ ] **Step 1: Escribir los tests de estructura (fallan)**

```python
# backend/tests/test_structure_analyzer.py
from app.analyzers.repository.structure import StructureAnalyzer


def test_detects_languages_and_counts_files(tmp_path):
    (tmp_path / "app.py").write_text("print('hola')")
    (tmp_path / "util.py").write_text("x = 1")
    (tmp_path / "index.ts").write_text("export const a = 1")

    result = StructureAnalyzer().analyze(tmp_path)

    assert result.dimension == "maintainability"
    assert result.metrics["languages"]["Python"] == 2
    assert result.metrics["languages"]["TypeScript"] == 1
    assert result.metrics["total_files"] == 3


def test_ignores_dependency_and_vcs_directories(tmp_path):
    (tmp_path / "app.py").write_text("x = 1")
    noise = tmp_path / "node_modules" / "paquete"
    noise.mkdir(parents=True)
    (noise / "index.js").write_text("module.exports = {}")
    git_dir = tmp_path / ".git"
    git_dir.mkdir()
    (git_dir / "config").write_text("[core]")

    result = StructureAnalyzer().analyze(tmp_path)

    assert result.metrics["total_files"] == 1
    assert "JavaScript" not in result.metrics["languages"]


def test_flags_an_empty_repository(tmp_path):
    result = StructureAnalyzer().analyze(tmp_path)
    assert any(f.severity == "high" for f in result.findings)


def test_identifies_project_shape(tmp_path):
    (tmp_path / "frontend").mkdir()
    (tmp_path / "frontend" / "App.tsx").write_text("export default () => null")
    (tmp_path / "backend").mkdir()
    (tmp_path / "backend" / "main.py").write_text("x = 1")

    result = StructureAnalyzer().analyze(tmp_path)

    assert result.metrics["project_shape"] == "fullstack"
```

- [ ] **Step 2: Ejecutar y verificar que falla**

Run: `cd backend && python -m pytest tests/test_structure_analyzer.py -q`
Expected: FAIL — módulo inexistente.

- [ ] **Step 3: Implementar `backend/app/analyzers/repository/structure.py`**

```python
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
```

- [ ] **Step 4: Ejecutar y verificar que pasa**

Run: `cd backend && python -m pytest tests/test_structure_analyzer.py -q`
Expected: PASS

- [ ] **Step 5: Escribir los tests de documentación (fallan)**

```python
# backend/tests/test_documentation_analyzer.py
from app.analyzers.repository.documentation import DocumentationAnalyzer


def test_flags_missing_readme(tmp_path):
    result = DocumentationAnalyzer().analyze(tmp_path)
    titles = [f.title for f in result.findings]
    assert any("README" in title for title in titles)
    assert result.metrics["has_readme"] is False


def test_flags_a_readme_that_is_too_short(tmp_path):
    (tmp_path / "README.md").write_text("# Proyecto\n")
    result = DocumentationAnalyzer().analyze(tmp_path)
    assert result.metrics["has_readme"] is True
    assert any("breve" in f.title.lower() or "breve" in f.description.lower() for f in result.findings)


def test_recognises_a_complete_documentation_set(tmp_path):
    (tmp_path / "README.md").write_text("# Proyecto\n\n" + ("Contenido util. " * 80))
    (tmp_path / "LICENSE").write_text("MIT")
    (tmp_path / "CONTRIBUTING.md").write_text("Como contribuir")
    (tmp_path / "CHANGELOG.md").write_text("## 1.0.0")

    result = DocumentationAnalyzer().analyze(tmp_path)

    assert result.metrics["has_license"] is True
    assert result.metrics["has_contributing"] is True
    assert result.metrics["has_changelog"] is True
    assert result.findings == []


def test_detects_architecture_docs_in_a_docs_directory(tmp_path):
    (tmp_path / "README.md").write_text("# P\n\n" + ("texto " * 200))
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "ARCHITECTURE.md").write_text("# Arquitectura")

    result = DocumentationAnalyzer().analyze(tmp_path)

    assert result.metrics["has_architecture_docs"] is True
```

- [ ] **Step 6: Ejecutar y verificar que falla**

Run: `cd backend && python -m pytest tests/test_documentation_analyzer.py -q`
Expected: FAIL — módulo inexistente.

- [ ] **Step 7: Implementar `backend/app/analyzers/repository/documentation.py`**

```python
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


class DocumentationAnalyzer:
    name = "documentation"

    def analyze(self, repo_dir: Path) -> AnalyzerResult:
        readme_path = self._first_existing(repo_dir, README_NAMES)
        readme_length = len(readme_path.read_text(encoding="utf-8", errors="replace")) if readme_path else 0

        has_architecture = any((repo_dir / name).exists() for name in ARCHITECTURE_NAMES) or (
            (repo_dir / "docs").is_dir() and any((repo_dir / "docs").glob("*.md"))
        )

        metrics = {
            "has_readme": readme_path is not None,
            "readme_length": readme_length,
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
```

- [ ] **Step 8: Ejecutar ambos tests y verificar que pasan**

Run: `cd backend && python -m pytest tests/test_structure_analyzer.py tests/test_documentation_analyzer.py -q`
Expected: PASS

- [ ] **Step 9: Commit**

```bash
git add backend/app/analyzers/repository backend/tests/test_structure_analyzer.py backend/tests/test_documentation_analyzer.py
git commit -m "feat: analizadores de estructura y documentacion"
```

---

### Task 5: Analizador de tests

**Files:**
- Create: `backend/app/analyzers/repository/tests_analyzer.py`
- Test: `backend/tests/test_tests_analyzer.py`

**Interfaces:**
- Consumes: `AnalyzerResult`, `FindingData` (Task 3).
- Produces: `TestsAnalyzer` (dimensión `reliability`) — localiza directorios y archivos de test, los clasifica en unitarios/integración/E2E, y estima la proporción de archivos de test frente a archivos de código. **No ejecuta los tests**, solo los detecta.

- [ ] **Step 1: Escribir los tests (fallan)**

```python
# backend/tests/test_tests_analyzer.py
from app.analyzers.repository.tests_analyzer import TestsAnalyzer


def test_flags_a_repository_with_no_tests(tmp_path):
    (tmp_path / "app.py").write_text("x = 1")
    result = TestsAnalyzer().analyze(tmp_path)
    assert result.metrics["test_file_count"] == 0
    assert any(f.severity in {"high", "critical"} for f in result.findings)


def test_detects_python_and_javascript_test_files(tmp_path):
    (tmp_path / "app.py").write_text("x = 1")
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_app.py").write_text("def test_x(): pass")
    (tmp_path / "app.test.ts").write_text("it('funciona', () => {})")

    result = TestsAnalyzer().analyze(tmp_path)

    assert result.metrics["test_file_count"] == 2


def test_classifies_test_types(tmp_path):
    (tmp_path / "app.py").write_text("x = 1")
    for directory, filename in [
        ("tests", "test_unidad.py"),
        ("tests/integration", "test_integracion.py"),
        ("e2e", "flujo.spec.ts"),
    ]:
        d = tmp_path / directory
        d.mkdir(parents=True, exist_ok=True)
        (d / filename).write_text("test")

    result = TestsAnalyzer().analyze(tmp_path)

    assert result.metrics["has_integration_tests"] is True
    assert result.metrics["has_e2e_tests"] is True


def test_reports_the_ratio_of_test_to_source_files(tmp_path):
    for i in range(4):
        (tmp_path / f"modulo{i}.py").write_text("x = 1")
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_uno.py").write_text("def test(): pass")

    result = TestsAnalyzer().analyze(tmp_path)

    assert result.metrics["test_file_count"] == 1
    assert result.metrics["source_file_count"] == 4
    assert 0.2 <= result.metrics["test_ratio"] <= 0.3
```

- [ ] **Step 2: Ejecutar y verificar que falla**

Run: `cd backend && python -m pytest tests/test_tests_analyzer.py -q`
Expected: FAIL — módulo inexistente.

- [ ] **Step 3: Implementar `backend/app/analyzers/repository/tests_analyzer.py`**

```python
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
```

- [ ] **Step 4: Ejecutar y verificar que pasa**

Run: `cd backend && python -m pytest tests/test_tests_analyzer.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/analyzers/repository/tests_analyzer.py backend/tests/test_tests_analyzer.py
git commit -m "feat: analizador de tests"
```

---

### Task 6: Motor de puntuación ISO 25010

**Files:**
- Create: `backend/app/services/scoring_service.py`
- Test: `backend/tests/test_scoring_service.py`

**Interfaces:**
- Consumes: `AnalyzerResult` (Task 3).
- Produces: `REPOSITORY_WEIGHTS: dict[str, float]` — los pesos de `context/claude.md` §6.
- Produces: `score_dimension(dimension: str, metrics: dict, findings: list[FindingData]) -> float` (0-100).
- Produces: `calculate_overall_score(dimension_scores: dict[str, float]) -> float` — media ponderada normalizada por la suma de pesos presentes.
- Produces: `calculate_confidence(results: list[AnalyzerResult]) -> float` — confianza según cuánta evidencia se recogió.

- [ ] **Step 1: Escribir los tests (fallan)**

```python
# backend/tests/test_scoring_service.py
import pytest

from app.analyzers.base import FindingData
from app.services.scoring_service import (
    REPOSITORY_WEIGHTS,
    calculate_confidence,
    calculate_overall_score,
    score_dimension,
)


def test_weights_match_the_spec():
    assert REPOSITORY_WEIGHTS["functional_suitability"] == 0.15
    assert REPOSITORY_WEIGHTS["reliability"] == 0.20
    assert REPOSITORY_WEIGHTS["security"] == 0.20
    assert REPOSITORY_WEIGHTS["maintainability"] == 0.20
    assert REPOSITORY_WEIGHTS["portability"] == 0.10
    assert REPOSITORY_WEIGHTS["project_activity"] == 0.15
    assert sum(REPOSITORY_WEIGHTS.values()) == pytest.approx(1.0)


def test_a_dimension_with_no_findings_scores_full_marks():
    assert score_dimension("reliability", {"test_ratio": 0.5}, []) == 100.0


def test_findings_reduce_the_score_by_severity():
    critical = score_dimension("security", {}, [_finding("critical")])
    low = score_dimension("security", {}, [_finding("low")])
    assert critical < low < 100.0


def test_score_never_goes_below_zero():
    findings = [_finding("critical") for _ in range(20)]
    assert score_dimension("security", {}, findings) == 0.0


def test_overall_score_normalises_over_the_weights_present():
    # Solo dos dimensiones medidas: el resultado se normaliza sobre sus pesos,
    # no sobre 1.0, para no penalizar lo que aun no se ha medido.
    score = calculate_overall_score({"reliability": 80.0, "security": 60.0})
    assert score == pytest.approx(70.0)


def test_overall_score_is_weighted_not_a_plain_average():
    score = calculate_overall_score({"portability": 100.0, "security": 0.0})
    # portabilidad pesa 0.10 y seguridad 0.20 -> 100*0.1 / 0.3 = 33.3
    assert score == pytest.approx(33.3, abs=0.1)


def test_confidence_grows_with_the_amount_of_evidence():
    from app.analyzers.base import AnalyzerResult

    poca = calculate_confidence([AnalyzerResult(dimension="reliability", metrics={})])
    mucha = calculate_confidence(
        [
            AnalyzerResult(dimension="reliability", metrics={"a": 1, "b": 2}),
            AnalyzerResult(dimension="security", metrics={"c": 3}),
            AnalyzerResult(dimension="maintainability", metrics={"d": 4}),
        ]
    )
    assert mucha > poca


def _finding(severity: str) -> FindingData:
    return FindingData(
        type="security", severity=severity, title="t", description="d"
    )
```

- [ ] **Step 2: Ejecutar y verificar que falla**

Run: `cd backend && python -m pytest tests/test_scoring_service.py -q`
Expected: FAIL — módulo inexistente.

- [ ] **Step 3: Implementar `backend/app/services/scoring_service.py`**

```python
"""Convierte hallazgos en puntuaciones ISO/IEC 25010.

La formula es la del spec: puntuacion = sum(peso_i * metrica_i) / sum(pesos).
Se normaliza sobre los pesos de las dimensiones realmente medidas, para no
penalizar a un proyecto por dimensiones que este analisis todavia no cubre.
"""

from app.analyzers.base import AnalyzerResult, FindingData

# Pesos de context/claude.md seccion 6, tabla "Para analisis de repositorio".
REPOSITORY_WEIGHTS: dict[str, float] = {
    "functional_suitability": 0.15,
    "reliability": 0.20,
    "security": 0.20,
    "maintainability": 0.20,
    "portability": 0.10,
    "project_activity": 0.15,
}

# Cuanto resta cada hallazgo segun su gravedad.
SEVERITY_PENALTY: dict[str, float] = {
    "critical": 40.0,
    "high": 20.0,
    "medium": 10.0,
    "low": 4.0,
    "info": 0.0,
}

# A partir de esta cantidad de metricas recogidas se considera evidencia plena.
EVIDENCE_FOR_FULL_CONFIDENCE = 12


def score_dimension(dimension: str, metrics: dict, findings: list[FindingData]) -> float:
    penalty = sum(SEVERITY_PENALTY.get(f.severity, 0.0) for f in findings)
    return round(max(0.0, 100.0 - penalty), 2)


def calculate_overall_score(dimension_scores: dict[str, float]) -> float:
    present = {d: s for d, s in dimension_scores.items() if d in REPOSITORY_WEIGHTS}
    if not present:
        return 0.0
    total_weight = sum(REPOSITORY_WEIGHTS[d] for d in present)
    weighted = sum(REPOSITORY_WEIGHTS[d] * score for d, score in present.items())
    return round(weighted / total_weight, 2)


def calculate_confidence(results: list[AnalyzerResult]) -> float:
    evidence = sum(len(r.metrics) for r in results)
    return round(min(100.0, 100.0 * evidence / EVIDENCE_FOR_FULL_CONFIDENCE), 2)
```

- [ ] **Step 4: Ejecutar y verificar que pasa**

Run: `cd backend && python -m pytest tests/test_scoring_service.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/scoring_service.py backend/tests/test_scoring_service.py
git commit -m "feat: motor de puntuacion ISO 25010"
```

---

### Task 7: Tarea Celery y endpoints de análisis

**Files:**
- Modify: `backend/app/worker.py`
- Create: `backend/app/services/analysis_service.py`
- Create: `backend/app/tasks/__init__.py`
- Create: `backend/app/tasks/analyze_repository.py`
- Create: `backend/app/schemas/analysis.py`
- Modify: `backend/app/api/repositories.py`
- Create: `backend/app/api/analyses.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_analysis_flow.py`

**Interfaces:**
- Consumes: `clone_repository`, `read_head_commit` (Task 2); los tres analizadores (Tasks 4-5); `score_dimension`, `calculate_overall_score`, `calculate_confidence` (Task 6); modelos `Analysis`, `Dimension`, `Finding`, `Repository` (Semana 1).
- Produces: `POST /api/repositories/{repository_id}/analyze` → `202 {"analysis_id": str}`.
- Produces: `GET /api/analyses/{analysis_id}` → `200` con estado, puntuación, dimensiones y hallazgos.
- Produces: `run_repository_analysis(analysis_id: str) -> None` — la función que ejecuta el pipeline completo, invocable directamente en tests sin Celery.

- [ ] **Step 1: Escribir los tests (fallan)**

```python
# backend/tests/test_analysis_flow.py
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from app.core.database import SessionLocal
from app.core.security import create_access_token
from app.main import app
from app.models.analysis import Analysis, Dimension, Finding
from app.models.repository import Repository
from app.models.user import User

client = TestClient(app)

TEST_EMAIL = "analisis@example.com"
TEST_GITHUB_ID = 910000042


@pytest.fixture(autouse=True)
def _clean():
    def _delete():
        db = SessionLocal()
        try:
            db.execute(delete(User).where(User.email == TEST_EMAIL))
            db.commit()
        finally:
            db.close()

    _delete()
    yield
    _delete()


@pytest.fixture
def user_with_repo():
    db = SessionLocal()
    try:
        user = User(id=uuid.uuid4(), email=TEST_EMAIL, github_id=TEST_GITHUB_ID)
        db.add(user)
        db.flush()
        repo = Repository(
            id=uuid.uuid4(),
            user_id=user.id,
            github_id=1296269,
            name="Hello-World",
            full_name="octocat/Hello-World",
            default_branch="master",
            is_private=False,
        )
        db.add(repo)
        db.commit()
        db.refresh(user)
        db.refresh(repo)
        return user.id, repo.id
    finally:
        db.close()


def test_analyze_endpoint_queues_an_analysis(user_with_repo, monkeypatch):
    user_id, repo_id = user_with_repo
    queued = {}
    from app.api import repositories as repositories_module

    monkeypatch.setattr(
        repositories_module, "queue_repository_analysis",
        lambda analysis_id: queued.setdefault("id", analysis_id),
    )

    response = client.post(
        f"/api/repositories/{repo_id}/analyze",
        headers={"Authorization": f"Bearer {create_access_token(user_id)}"},
    )

    assert response.status_code == 202
    analysis_id = response.json()["analysis_id"]
    assert queued["id"] == analysis_id

    db = SessionLocal()
    try:
        analysis = db.get(Analysis, uuid.UUID(analysis_id))
        assert analysis.status == "pending"
        assert analysis.analysis_type == "repository"
    finally:
        db.close()


def test_analyze_rejects_a_repository_of_another_user(user_with_repo):
    _, repo_id = user_with_repo
    other_token = create_access_token(uuid.uuid4())
    response = client.post(
        f"/api/repositories/{repo_id}/analyze",
        headers={"Authorization": f"Bearer {other_token}"},
    )
    assert response.status_code in (401, 404)


def test_full_pipeline_produces_a_real_score(user_with_repo):
    """Corre el pipeline completo contra un repositorio publico real."""
    from app.services.analysis_service import run_repository_analysis

    user_id, repo_id = user_with_repo
    db = SessionLocal()
    try:
        analysis = Analysis(
            id=uuid.uuid4(), user_id=user_id, repository_id=repo_id,
            analysis_type="repository", status="pending",
        )
        db.add(analysis)
        db.commit()
        analysis_id = analysis.id
    finally:
        db.close()

    run_repository_analysis(str(analysis_id))

    db = SessionLocal()
    try:
        analysis = db.get(Analysis, analysis_id)
        assert analysis.status == "completed"
        assert analysis.overall_score is not None
        assert 0 <= float(analysis.overall_score) <= 100
        assert len(analysis.commit_hash) == 40

        dimensions = db.scalars(select(Dimension).where(Dimension.analysis_id == analysis_id)).all()
        assert {d.name for d in dimensions} >= {"maintainability", "functional_suitability", "reliability"}

        findings = db.scalars(select(Finding).where(Finding.analysis_id == analysis_id)).all()
        # Hello-World no tiene tests ni licencia: debe haber hallazgos reales.
        assert len(findings) > 0
    finally:
        db.close()


def test_failed_analysis_is_marked_failed_not_left_pending(user_with_repo, monkeypatch):
    from app.services import analysis_service

    user_id, repo_id = user_with_repo

    def _explode(*args, **kwargs):
        raise RuntimeError("fallo simulado de clonado")

    monkeypatch.setattr(analysis_service, "clone_repository", _explode)

    db = SessionLocal()
    try:
        analysis = Analysis(
            id=uuid.uuid4(), user_id=user_id, repository_id=repo_id,
            analysis_type="repository", status="pending",
        )
        db.add(analysis)
        db.commit()
        analysis_id = analysis.id
    finally:
        db.close()

    analysis_service.run_repository_analysis(str(analysis_id))

    db = SessionLocal()
    try:
        analysis = db.get(Analysis, analysis_id)
        assert analysis.status == "failed"
        assert analysis.error_message
        # El mensaje no debe filtrar rutas internas del servidor.
        assert "/tmp/" not in analysis.error_message
    finally:
        db.close()
```

- [ ] **Step 2: Ejecutar y verificar que falla**

Run: `cd backend && python -m pytest tests/test_analysis_flow.py -q`
Expected: FAIL — módulos y endpoints inexistentes.

- [ ] **Step 3: Implementar `backend/app/services/analysis_service.py`**

```python
"""Orquesta el ciclo de vida completo de un analisis de repositorio."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import select

from app.analyzers.repository.documentation import DocumentationAnalyzer
from app.analyzers.repository.structure import StructureAnalyzer
from app.analyzers.repository.tests_analyzer import TestsAnalyzer
from app.core.database import SessionLocal
from app.models.analysis import Analysis, Dimension, Finding
from app.models.repository import Repository
from app.services.repo_service import clone_repository, read_head_commit
from app.services.scoring_service import (
    REPOSITORY_WEIGHTS,
    calculate_confidence,
    calculate_overall_score,
    score_dimension,
)

ANALYZERS = (StructureAnalyzer(), DocumentationAnalyzer(), TestsAnalyzer())


def run_repository_analysis(analysis_id: str) -> None:
    db = SessionLocal()
    try:
        analysis = db.get(Analysis, uuid.UUID(analysis_id))
        if analysis is None:
            return
        repository = db.get(Repository, analysis.repository_id)
        if repository is None:
            _mark_failed(db, analysis, "el repositorio ya no existe")
            return

        analysis.status = "cloning"
        analysis.started_at = datetime.now(timezone.utc)
        db.commit()

        clone_url = f"https://github.com/{repository.full_name}"
        try:
            with clone_repository(clone_url, repository.default_branch) as repo_dir:
                analysis.status = "running"
                db.commit()

                commit_hash, commit_message = read_head_commit(repo_dir)
                results = [analyzer.analyze(repo_dir) for analyzer in ANALYZERS]
        except Exception as exc:  # noqa: BLE001 - se registra un mensaje seguro
            _mark_failed(db, analysis, _safe_error_message(exc))
            return

        analysis.status = "scoring"
        db.commit()

        dimension_scores: dict[str, float] = {}
        for result in results:
            score = score_dimension(result.dimension, result.metrics, result.findings)
            dimension_scores[result.dimension] = score
            db.add(
                Dimension(
                    id=uuid.uuid4(),
                    analysis_id=analysis.id,
                    name=result.dimension,
                    score=score,
                    weight=REPOSITORY_WEIGHTS[result.dimension],
                    raw_metrics=result.metrics,
                )
            )
            for finding in result.findings:
                db.add(
                    Finding(
                        id=uuid.uuid4(),
                        analysis_id=analysis.id,
                        type=finding.type,
                        severity=finding.severity,
                        title=finding.title,
                        description=finding.description,
                        file_path=finding.file_path,
                        recommendation=finding.recommendation,
                    )
                )

        analysis.overall_score = calculate_overall_score(dimension_scores)
        analysis.confidence_level = calculate_confidence(results)
        analysis.commit_hash = commit_hash
        analysis.commit_message = commit_message
        analysis.branch = repository.default_branch
        analysis.raw_data = {r.dimension: r.metrics for r in results}
        analysis.status = "completed"
        analysis.completed_at = datetime.now(timezone.utc)

        repository.last_analyzed_at = analysis.completed_at
        db.commit()
    finally:
        db.close()


def _mark_failed(db, analysis: Analysis, message: str) -> None:
    analysis.status = "failed"
    analysis.error_message = message
    analysis.completed_at = datetime.now(timezone.utc)
    db.commit()


def _safe_error_message(exc: Exception) -> str:
    """Mensaje apto para mostrar al usuario: sin rutas internas ni tokens."""
    text = str(exc)
    if "/tmp/" in text or "\\Temp\\" in text:
        return "el analisis fallo al preparar el repositorio"
    return text[:300] or "el analisis fallo por un error inesperado"
```

- [ ] **Step 4: Implementar la tarea Celery en `backend/app/tasks/analyze_repository.py`**

```python
from app.services.analysis_service import run_repository_analysis
from app.worker import celery_app


@celery_app.task(
    name="qalitiradar.analyze_repository",
    time_limit=600,        # 10 minutos duros, como exige el spec
    soft_time_limit=570,   # margen para limpiar antes del corte
)
def analyze_repository_task(analysis_id: str) -> None:
    run_repository_analysis(analysis_id)


def queue_repository_analysis(analysis_id: str) -> None:
    analyze_repository_task.delay(analysis_id)
```

Crear `backend/app/tasks/__init__.py`:

```python
from app.tasks.analyze_repository import analyze_repository_task, queue_repository_analysis

__all__ = ["analyze_repository_task", "queue_repository_analysis"]
```

- [ ] **Step 5: Añadir el endpoint de disparo en `backend/app/api/repositories.py`**

```python
# añadir a los imports existentes
import uuid
from fastapi import status
from app.models.analysis import Analysis
from app.models.repository import Repository
from app.tasks import queue_repository_analysis


@router.post("/{repository_id}/analyze", status_code=status.HTTP_202_ACCEPTED)
def analyze_repository(
    repository_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    repository = db.get(Repository, repository_id)
    # Se responde 404 tanto si no existe como si es de otro usuario, para no
    # revelar que repositorios existen en cuentas ajenas.
    if repository is None or repository.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="repositorio no encontrado")
    if repository.is_private:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="solo se analizan repositorios publicos")

    analysis = Analysis(
        id=uuid.uuid4(),
        user_id=current_user.id,
        repository_id=repository.id,
        analysis_type="repository",
        status="pending",
    )
    db.add(analysis)
    db.commit()

    queue_repository_analysis(str(analysis.id))
    return {"analysis_id": str(analysis.id)}
```

- [ ] **Step 6: Crear `backend/app/api/analyses.py` y `backend/app/schemas/analysis.py`**

```python
# backend/app/schemas/analysis.py
from pydantic import BaseModel


class FindingOut(BaseModel):
    type: str
    severity: str
    title: str
    description: str
    file_path: str | None = None
    recommendation: str | None = None


class DimensionOut(BaseModel):
    name: str
    score: float
    weight: float


class AnalysisOut(BaseModel):
    id: str
    status: str
    overall_score: float | None = None
    confidence_level: float | None = None
    commit_hash: str | None = None
    commit_message: str | None = None
    error_message: str | None = None
    dimensions: list[DimensionOut] = []
    findings: list[FindingOut] = []
```

```python
# backend/app/api/analyses.py
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.models.analysis import Analysis, Dimension, Finding
from app.models.user import User
from app.schemas.analysis import AnalysisOut, DimensionOut, FindingOut

router = APIRouter(prefix="/api/analyses", tags=["analyses"])


@router.get("/{analysis_id}", response_model=AnalysisOut)
def get_analysis(
    analysis_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AnalysisOut:
    analysis = db.get(Analysis, analysis_id)
    if analysis is None or analysis.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="analisis no encontrado")

    dimensions = db.scalars(select(Dimension).where(Dimension.analysis_id == analysis.id)).all()
    findings = db.scalars(select(Finding).where(Finding.analysis_id == analysis.id)).all()

    return AnalysisOut(
        id=str(analysis.id),
        status=analysis.status,
        overall_score=float(analysis.overall_score) if analysis.overall_score is not None else None,
        confidence_level=float(analysis.confidence_level) if analysis.confidence_level is not None else None,
        commit_hash=analysis.commit_hash,
        commit_message=analysis.commit_message,
        error_message=analysis.error_message,
        dimensions=[DimensionOut(name=d.name, score=float(d.score), weight=float(d.weight)) for d in dimensions],
        findings=[
            FindingOut(
                type=f.type, severity=f.severity, title=f.title,
                description=f.description, file_path=f.file_path,
                recommendation=f.recommendation,
            )
            for f in findings
        ],
    )
```

Registrar el router en `backend/app/main.py`:

```python
from app.api.analyses import router as analyses_router
app.include_router(analyses_router)
```

- [ ] **Step 7: Ejecutar los tests y verificar que pasan**

Run: `cd backend && python -m pytest tests/test_analysis_flow.py -q`
Expected: PASS — incluido `test_full_pipeline_produces_a_real_score`, que analiza un repositorio real de GitHub de punta a punta.

- [ ] **Step 8: Ejecutar la suite completa**

Run: `cd backend && python -m pytest -q`
Expected: todos los tests previos siguen pasando.

- [ ] **Step 9: Verificación manual con el worker real**

```bash
# terminal 1 — worker en el host (nunca en contenedor)
cd backend && celery -A app.worker worker --loglevel=info

# terminal 2
curl -X POST http://localhost:8000/api/repositories/<ID>/analyze -H "Authorization: Bearer <TOKEN>"
curl http://localhost:8000/api/analyses/<ANALYSIS_ID> -H "Authorization: Bearer <TOKEN>"
```
Expected: el estado progresa `pending → cloning → running → scoring → completed` y el resultado trae puntuación, dimensiones y hallazgos.

- [ ] **Step 10: Commit**

```bash
git add backend/app/services/analysis_service.py backend/app/tasks backend/app/api/analyses.py backend/app/api/repositories.py backend/app/schemas/analysis.py backend/app/main.py backend/tests/test_analysis_flow.py
git commit -m "feat: pipeline de analisis con endpoints de disparo y consulta"
```

---

## Cierre de la Semana 2A — criterios de salida

- [ ] Suite completa en verde, sin warnings.
- [ ] `test_sandbox_has_no_network_access` y `test_sandbox_cannot_write_to_mounted_repo` pasan: el aislamiento está verificado, no solo declarado.
- [ ] Un análisis real de un repositorio público de GitHub completa de punta a punta y produce hallazgos ciertos (no inventados) y una puntuación entre 0 y 100.
- [ ] El directorio temporal del clon no sobrevive al análisis, ni cuando falla.
- [ ] Un análisis fallido queda en estado `failed` con un mensaje útil, nunca colgado en `pending`.
- [ ] Ningún mensaje de error expone rutas internas del servidor.

## Qué NO entra en la Semana 2A

Queda para la **Semana 2B**: analizadores de dependencias (`npm audit`/`pip-audit`), CI/CD, seguridad (Gitleaks + Semgrep, que sí usan el sandbox de la Task 1) y actividad del proyecto (API de GitHub). Con ellos se completan las 6 dimensiones y la puntuación deja de normalizarse sobre un subconjunto.

Para la **Semana 3**: analizadores de URL y modo combinado.
