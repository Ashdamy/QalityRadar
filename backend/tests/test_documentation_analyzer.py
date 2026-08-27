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
