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


# --- Pesos -----------------------------------------------------------------


def test_weights_match_the_spec():
    assert REPOSITORY_WEIGHTS["functional_suitability"] == 0.15
    assert REPOSITORY_WEIGHTS["reliability"] == 0.20
    assert REPOSITORY_WEIGHTS["security"] == 0.20
    assert REPOSITORY_WEIGHTS["maintainability"] == 0.20
    assert REPOSITORY_WEIGHTS["portability"] == 0.10
    assert REPOSITORY_WEIGHTS["project_activity"] == 0.15
    assert sum(REPOSITORY_WEIGHTS.values()) == pytest.approx(1.0)


# --- Los puntos se ganan, no se regalan ------------------------------------


def test_an_empty_dimension_scores_zero_not_one_hundred():
    # Este es el fallo que corrige el modelo: sin evidencia no hay nota.
    assert score_dimension("maintainability", {}, []) == 0.0
    assert score_dimension("functional_suitability", {}, []) == 0.0
    assert score_dimension("reliability", {}, []) == 0.0


def test_a_dimension_without_a_rubric_yet_scores_zero():
    # La actividad del proyecto aun no se mide: no se acredita calidad no
    # comprobada.
    assert score_dimension("project_activity", {"lo que sea": 1}, []) == 0.0


def test_absence_of_problems_earns_nothing_when_nothing_was_scanned():
    # Sin archivos escaneados no se puede premiar "no tiene capturas
    # silenciosas" ni "no tiene secretos": no se ha mirado.
    assert score_dimension("reliability", {}, []) == 0.0
    assert score_dimension("security", {}, []) == 0.0
    assert score_dimension("security", {"code_files_scanned": 0}, []) == 0.0


def test_a_repository_with_no_tests_loses_the_whole_maturity_block():
    con_tests = score_dimension(
        "reliability",
        {"code_files_scanned": 20, "test_file_count": 10, "test_ratio": 0.5},
        [],
    )
    sin_tests = score_dimension(
        "reliability",
        {"code_files_scanned": 20, "test_file_count": 0, "test_ratio": 0.0},
        [],
    )
    # La madurez es el bloque mas grande de la dimension: sin pruebas se
    # pierde entero, y eso debe notarse con claridad en la nota.
    assert con_tests - sin_tests >= 30
    assert sin_tests < 20


def test_more_tests_earn_a_higher_reliability_score():
    pocos = score_dimension(
        "reliability", {"code_files_scanned": 20, "test_file_count": 1, "test_ratio": 0.02}, []
    )
    muchos = score_dimension(
        "reliability",
        {
            "code_files_scanned": 20,
            "test_file_count": 40,
            "test_ratio": 0.6,
            "has_integration_tests": True,
            "has_e2e_tests": True,
        },
        [],
    )
    assert 0 < pocos < muchos <= 100


def test_a_one_line_readme_earns_far_less_than_a_real_one():
    minimo = score_dimension("functional_suitability", {"has_readme": True, "readme_length": 12}, [])
    completo = score_dimension(
        "functional_suitability",
        {
            "has_readme": True,
            "readme_length": 4000,
            "readme_has_install_instructions": True,
            "readme_has_usage_section": True,
            "readme_has_code_examples": True,
            "has_license": True,
            "has_contributing": True,
            "has_changelog": True,
            "has_architecture_docs": True,
            "has_api_docs": True,
            "has_examples": True,
            "completeness_files_scanned": 30,
            "unimplemented_stub_count": 0,
            "pending_markers_per_file": 0.1,
        },
        [],
    )
    assert minimo < 25
    assert completo == 100.0


def test_maintainability_rewards_real_signals_not_mere_existence():
    desnudo = score_dimension("maintainability", {"code_file_count": 3, "average_file_lines": 900, "largest_file_lines": 2000}, [])
    cuidado = score_dimension(
        "maintainability",
        {
            "code_file_count": 50,
            "average_file_lines": 120,
            "largest_file_lines": 300,
            "has_gitignore": True,
            "has_dependency_manifest": True,
            "has_linter_config": True,
            "top_level_directory_count": 4,
            "project_shape": "fullstack",
            "average_function_lines": 18,
            "comment_ratio": 0.12,
            "function_documentation_ratio": 0.7,
            "max_nesting_depth": 3,
            "type_annotation_ratio": 0.9,
            "duplicated_file_count": 0,
        },
        [],
    )
    assert desnudo < 25
    assert cuidado == 100.0


def test_scores_are_bounded_between_zero_and_one_hundred():
    generoso = score_dimension(
        "functional_suitability",
        {
            "has_readme": True,
            "readme_length": 999999,
            "readme_has_install_instructions": True,
            "readme_has_usage_section": True,
            "readme_has_code_examples": True,
            "has_license": True,
            "has_contributing": True,
            "has_changelog": True,
            "has_architecture_docs": True,
        },
        [],
    )
    assert 0.0 <= generoso <= 100.0


# --- Puntuacion global ------------------------------------------------------


def test_overall_score_normalises_over_the_weights_present():
    assert calculate_overall_score({"reliability": 80.0, "security": 60.0}) == pytest.approx(70.0)


def test_overall_score_is_weighted_not_a_plain_average():
    # portabilidad pesa 0.10 y seguridad 0.20 -> (100*0.1 + 0*0.2) / 0.3 = 33.3
    assert calculate_overall_score({"portability": 100.0, "security": 0.0}) == pytest.approx(33.3, abs=0.1)


def test_overall_score_of_nothing_is_zero_not_a_crash():
    assert calculate_overall_score({}) == 0.0


def test_overall_score_ignores_unknown_dimensions():
    assert calculate_overall_score({"reliability": 50.0, "inventada": 100.0}) == pytest.approx(50.0)


def test_a_critical_finding_caps_the_overall_score():
    # El spec exige que los riesgos criticos bloqueen las puntuaciones altas.
    perfecto = {"reliability": 100.0, "maintainability": 100.0}
    assert calculate_overall_score(perfecto) == 100.0
    assert calculate_overall_score(perfecto, [_finding("critical")]) == 40.0


def test_a_high_finding_caps_the_overall_score_less_severely():
    perfecto = {"reliability": 100.0, "maintainability": 100.0}
    assert calculate_overall_score(perfecto, [_finding("high")]) == 70.0


def test_the_cap_never_raises_a_low_score():
    bajo = {"reliability": 10.0}
    assert calculate_overall_score(bajo, [_finding("critical")]) == 10.0


def test_minor_findings_do_not_cap_the_score():
    perfecto = {"reliability": 100.0, "maintainability": 100.0}
    assert calculate_overall_score(perfecto, [_finding("medium"), _finding("low")]) == 100.0


# --- Confianza --------------------------------------------------------------


def test_confidence_grows_with_the_amount_of_evidence():
    poca = calculate_confidence([AnalyzerResult(dimension="reliability", metrics={})])
    mucha = calculate_confidence(
        [
            AnalyzerResult(dimension="reliability", metrics={str(i): i for i in range(8)}),
            AnalyzerResult(dimension="security", metrics={str(i): i for i in range(8)}),
        ]
    )
    assert mucha > poca


def test_confidence_is_capped_at_one_hundred():
    abundante = [AnalyzerResult(dimension="reliability", metrics={str(i): i for i in range(80)})]
    assert calculate_confidence(abundante) == 100.0


def test_confidence_of_no_evidence_is_zero():
    assert calculate_confidence([]) == 0.0
