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
