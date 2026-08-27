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


# --- Step 5: integration tests against a real public repo -----------------

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
