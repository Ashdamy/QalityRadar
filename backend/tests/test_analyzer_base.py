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
