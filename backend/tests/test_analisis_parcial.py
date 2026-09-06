"""Un analizador que falla no puede llevarse por delante el informe entero.

Once analizadores corren sobre codigo ajeno. Que uno se atragante con algo que
no se previo es cuestion de tiempo, y hasta ahora eso dejaba al usuario sin
nada habiendo gastado su cuota, el clonado y el contenedor.

Que el informe incompleto valga no es una concesion: la puntuacion se normaliza
sobre los pesos de lo realmente medido y la confianza baja sola al haber menos
evidencia. El sistema ya sabia contarlo.
"""

from app.analyzers.base import AnalyzerResult, FindingData
from app.services.analysis_service import _analizar_lo_que_se_pueda
from app.services.scoring_service import calculate_confidence, calculate_overall_score


class _Bueno:
    name = "bueno"

    def __init__(self, dimension, metricas=3):
        self._dimension = dimension
        self._metricas = metricas

    def analyze(self, _repo_dir=None):
        return AnalyzerResult(
            dimension=self._dimension,
            metrics={f"m{i}": i for i in range(self._metricas)},
            findings=[],
        )


class _Explota:
    name = "explota"

    def analyze(self, _repo_dir=None):
        raise RuntimeError("algo que no se previo")


def test_los_demas_terminan_aunque_uno_reviente():
    resultados = _analizar_lo_que_se_pueda(
        None, [_Bueno("maintainability"), _Explota(), _Bueno("security")]
    )

    assert [r.dimension for r in resultados] == ["maintainability", "security"]


def test_si_fallan_todos_no_queda_nada():
    """Eso ya no es un informe incompleto, es no tener informe, y quien llama
    lo marca como fallido."""
    assert _analizar_lo_que_se_pueda(None, [_Explota(), _Explota()]) == []


def test_la_nota_se_reparte_entre_lo_que_si_se_midio():
    """Si no se normalizara, perder un analizador hundiria la nota como si esa
    dimension hubiera sacado un cero, que es mentira: no se midio."""
    completo = calculate_overall_score(
        {"maintainability": 80.0, "security": 80.0, "reliability": 80.0}
    )
    parcial = calculate_overall_score({"maintainability": 80.0, "security": 80.0})

    assert completo == parcial == 80.0


def test_la_confianza_baja_al_medir_menos():
    """Es lo que hace honesto un informe incompleto: la nota es la misma, pero
    se dice con cuanta evidencia se saco."""
    con_todo = calculate_confidence([_Bueno("x", metricas=10).analyze() for _ in range(5)])
    con_menos = calculate_confidence([_Bueno("x", metricas=10).analyze() for _ in range(2)])

    assert con_menos < con_todo


def test_un_hallazgo_critico_sigue_poniendo_techo():
    """La resiliencia no puede haber aflojado esto: un riesgo critico bloquea
    las notas altas aunque falte medir algo."""
    critico = FindingData(
        type="security", severity="critical", title="secreto expuesto", description="x"
    )

    nota = calculate_overall_score({"security": 95.0, "maintainability": 95.0}, [critico])

    assert nota < 95.0
