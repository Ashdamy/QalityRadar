"""Analisis combinado (Modo 3): codigo frente a produccion.

Ejecuta los dos analisis y compara sus resultados. Lo valioso no es la media
de ambas notas, sino la **discrepancia**: cuando el repositorio y la web
cuentan historias distintas, algo explica esa diferencia y suele ser
accionable.

Dos casos tipicos y opuestos:

- Codigo malo, produccion buena: la plataforma de despliegue esta regalando
  HTTPS, compresion y cabeceras que no estan en el repositorio. Al migrar de
  proveedor esa ventaja desaparece.
- Codigo bueno, produccion mala: el proyecto esta bien hecho pero mal
  desplegado o mal configurado, y el usuario final no recibe esa calidad.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.analysis import Analysis, Dimension, Discrepancy, Finding
from app.services.scoring_service import (
    REPOSITORY_WEIGHTS,
    URL_WEIGHTS,
    CRITICAL_FINDING_SCORE_CAP,
    HIGH_FINDING_SCORE_CAP,
)

# Umbral del spec: por debajo de esto la diferencia es ruido, no una historia.
SIGNIFICANT_DISCREPANCY = 15.0

SEVERITY_RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}


def consolidate_score(repo_score: float, url_score: float) -> float:
    """Media ponderada por la cantidad de evidencia de cada modo.

    No es una media simple: el analisis de repositorio cubre seis dimensiones
    partiendo del codigo fuente completo, y el de URL cinco partiendo de una
    respuesta HTTP. Cada lado aporta segun cuantas dimensiones sostiene.

    Ojo: los pesos de cada modo estan normalizados a 1.0 por separado, asi que
    sumarlos no distingue un modo de otro. La ponderacion tiene que salir del
    numero de dimensiones.
    """
    dims_repo = len(REPOSITORY_WEIGHTS)
    dims_url = len(URL_WEIGHTS)
    total = dims_repo + dims_url
    return round((repo_score * dims_repo + url_score * dims_url) / total, 2)


def explain_discrepancy(repo_score: float, url_score: float) -> tuple[str, str] | None:
    """Devuelve (explicacion, recomendaciones) si la brecha es significativa."""
    delta = repo_score - url_score
    if abs(delta) < SIGNIFICANT_DISCREPANCY:
        return None

    if delta < 0:
        # Produccion mejor que el codigo.
        explicacion = (
            f"Tu codigo puntua {repo_score:g} pero en produccion se ve como {url_score:g}. "
            "La aplicacion desplegada esta mejor de lo que el repositorio sugiere. "
            "Lo habitual es que la plataforma de despliegue anada por su cuenta HTTPS, "
            "compresion y cabeceras de cache, de modo que la web hereda buenas practicas "
            "que no estan en tu codigo."
        )
        recomendaciones = (
            "Esa ventaja no es tuya: si migras de proveedor, desaparece y la nota de "
            "produccion caeria hacia la del codigo. Lleva esas configuraciones al propio "
            "repositorio y ataca primero lo que ninguna plataforma puede compensar: las "
            "pruebas, la documentacion y la estructura del codigo."
        )
    else:
        # Codigo mejor que produccion.
        explicacion = (
            f"Tu codigo puntua {repo_score:g} pero en produccion se ve como {url_score:g}. "
            "El proyecto esta mejor hecho de lo que llega al usuario final: algo se pierde "
            "entre el repositorio y el despliegue. Suele deberse a configuracion del "
            "servidor, del proveedor o del proceso de publicacion."
        )
        recomendaciones = (
            "Revisa la configuracion de despliegue antes que el codigo: comprueba las "
            "cabeceras de seguridad, la compresion y la cache del servidor. El esfuerzo "
            "invertido en el repositorio no le esta llegando a quien usa la aplicacion."
        )

    return explicacion, recomendaciones


def build_improvement_plan(
    repo_findings: list[Finding],
    url_findings: list[Finding],
    discrepancy_recommendation: str | None,
) -> list[dict]:
    """Plan priorizado que mezcla ambos analisis y la propia discrepancia.

    Se ordena por gravedad real, no por origen: un problema critico del codigo
    va antes que uno medio de produccion, y al reves.
    """
    plan: list[dict] = []
    for finding, origen in [(f, "codigo") for f in repo_findings] + [
        (f, "produccion") for f in url_findings
    ]:
        if finding.severity in ("critical", "high", "medium"):
            plan.append(
                {
                    "severity": finding.severity,
                    "origin": origen,
                    "title": finding.title,
                    "detail": finding.recommendation or finding.description,
                }
            )

    plan.sort(key=lambda item: SEVERITY_RANK.get(item["severity"], 9))

    if discrepancy_recommendation:
        # La accion derivada de la discrepancia se inserta en tercer lugar: es
        # importante, pero no debe desplazar a los problemas criticos.
        plan.insert(
            min(2, len(plan)),
            {
                "severity": "high",
                "origin": "discrepancia",
                "title": "Reducir la dependencia de la plataforma de despliegue",
                "detail": discrepancy_recommendation,
            },
        )

    return plan[:10]


def persist_discrepancy(
    db: Session,
    analysis: Analysis,
    repo_score: float,
    url_score: float,
) -> Discrepancy | None:
    explicado = explain_discrepancy(repo_score, url_score)
    if explicado is None:
        return None

    explicacion, recomendaciones = explicado
    fila = Discrepancy(
        id=uuid.uuid4(),
        analysis_id=analysis.id,
        repo_score=repo_score,
        url_score=url_score,
        delta=round(repo_score - url_score, 2),
        explanation=explicacion,
        recommendations=recomendaciones,
    )
    db.add(fila)
    return fila


def copy_results_into(
    db: Session, target: Analysis, source: Analysis, weights: dict[str, float]
) -> tuple[dict[str, float], list[Finding]]:
    """Duplica dimensiones y hallazgos de un sub-analisis en el combinado.

    Se copian en vez de referenciarse para que el analisis combinado sea
    autocontenido: al consultarlo, exportarlo a PDF o compararlo con otro no
    hay que reconstruirlo desde sus dos mitades.
    """
    from sqlalchemy import select

    dimensiones = db.scalars(select(Dimension).where(Dimension.analysis_id == source.id)).all()
    hallazgos = db.scalars(select(Finding).where(Finding.analysis_id == source.id)).all()

    puntuaciones: dict[str, float] = {}
    for dimension in dimensiones:
        puntuaciones[dimension.name] = float(dimension.score)
        db.add(
            Dimension(
                id=uuid.uuid4(),
                analysis_id=target.id,
                name=dimension.name,
                score=dimension.score,
                weight=weights.get(dimension.name, dimension.weight),
                raw_metrics=dimension.raw_metrics,
            )
        )

    copiados: list[Finding] = []
    for hallazgo in hallazgos:
        copia = Finding(
            id=uuid.uuid4(),
            analysis_id=target.id,
            type=hallazgo.type,
            severity=hallazgo.severity,
            title=hallazgo.title,
            description=hallazgo.description,
            file_path=hallazgo.file_path,
            url=hallazgo.url,
            recommendation=hallazgo.recommendation,
        )
        db.add(copia)
        copiados.append(hallazgo)

    return puntuaciones, copiados


def apply_severity_cap(score: float, findings: list[Finding]) -> float:
    """El techo por riesgo critico tambien aplica a la nota consolidada."""
    severidades = {f.severity for f in findings}
    if "critical" in severidades:
        return round(min(score, CRITICAL_FINDING_SCORE_CAP), 2)
    if "high" in severidades:
        return round(min(score, HIGH_FINDING_SCORE_CAP), 2)
    return round(score, 2)


def now() -> datetime:
    return datetime.now(timezone.utc)
