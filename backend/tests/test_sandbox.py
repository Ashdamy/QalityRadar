import shutil
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


def test_rejects_image_name_starting_with_dash(tmp_path):
    with pytest.raises(ValueError, match="imagen"):
        build_docker_command("--privileged", ["echo"], tmp_path)


def test_rejects_image_name_that_looks_like_short_flag(tmp_path):
    with pytest.raises(ValueError, match="imagen"):
        build_docker_command("-v", ["echo"], tmp_path)


def test_double_dash_separator_precedes_image_name(tmp_path):
    command = build_docker_command("qaliti/analyzer:latest", ["echo", "hola"], tmp_path)
    index_double_dash = command.index("--")
    index_image = command.index("qaliti/analyzer:latest")
    assert index_image == index_double_dash + 1


def test_command_element_starting_with_dash_is_preserved(tmp_path):
    tool_command = ["gitleaks", "detect", "--no-git", "--report-format=json"]
    command = build_docker_command("qaliti/gitleaks:latest", tool_command, tmp_path)
    index_image = command.index("qaliti/gitleaks:latest")
    assert command[index_image + 1:] == tool_command


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
