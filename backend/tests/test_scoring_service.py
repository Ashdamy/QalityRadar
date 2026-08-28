import pytest

from app.analyzers.base import AnalyzerResult, FindingData
from app.services.scoring_service import (
    REPOSITORY_WEIGHTS,
    calculate_confidence,
    calculate_overall_score,
    score_dimension,
)


def _finding(severity: str) -> FindingData:
    return FindingData(type="security", severity=severity, title="t", description="d")


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
    high = score_dimension("security", {}, [_finding("high")])
    low = score_dimension("security", {}, [_finding("low")])
    assert critical < high < low < 100.0


def test_info_findings_do_not_reduce_the_score():
    assert score_dimension("security", {}, [_finding("info")]) == 100.0


def test_score_never_goes_below_zero():
    findings = [_finding("critical") for _ in range(20)]
    assert score_dimension("security", {}, findings) == 0.0


def test_overall_score_normalises_over_the_weights_present():
    # Solo dos dimensiones medidas: el resultado se normaliza sobre sus pesos,
    # no sobre 1.0, para no penalizar lo que aun no se ha medido.
    assert calculate_overall_score({"reliability": 80.0, "security": 60.0}) == pytest.approx(70.0)


def test_overall_score_is_weighted_not_a_plain_average():
    # portabilidad pesa 0.10 y seguridad 0.20 -> (100*0.1 + 0*0.2) / 0.3 = 33.3
    assert calculate_overall_score({"portability": 100.0, "security": 0.0}) == pytest.approx(33.3, abs=0.1)


def test_overall_score_of_nothing_is_zero_not_a_crash():
    assert calculate_overall_score({}) == 0.0


def test_overall_score_ignores_unknown_dimensions():
    # Una dimension que no esta en la tabla de pesos no debe arrastrar el
    # resultado ni provocar un KeyError.
    assert calculate_overall_score({"reliability": 50.0, "inventada": 100.0}) == pytest.approx(50.0)


def test_confidence_grows_with_the_amount_of_evidence():
    poca = calculate_confidence([AnalyzerResult(dimension="reliability", metrics={})])
    mucha = calculate_confidence(
        [
            AnalyzerResult(dimension="reliability", metrics={"a": 1, "b": 2}),
            AnalyzerResult(dimension="security", metrics={"c": 3}),
            AnalyzerResult(dimension="maintainability", metrics={"d": 4}),
        ]
    )
    assert mucha > poca


def test_confidence_is_capped_at_one_hundred():
    abundante = [AnalyzerResult(dimension="reliability", metrics={str(i): i for i in range(50)})]
    assert calculate_confidence(abundante) == 100.0


def test_confidence_of_no_evidence_is_zero():
    assert calculate_confidence([]) == 0.0
