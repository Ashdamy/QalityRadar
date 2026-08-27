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
