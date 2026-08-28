"""Detecta empeoramientos relevantes y deja un aviso al usuario.

Se avisa de lo que empeora, no de lo que mejora: un aviso que salta por
cualquier cosa deja de leerse, y entonces tampoco sirve cuando importa.

Las cuatro condiciones salen del spec:

- la puntuacion cae mas de 10 puntos,
- aparecen riesgos criticos que antes no estaban,
- se introducen vulnerabilidades de seguridad,
- la cobertura de pruebas se desploma.

Todas comparan con el analisis anterior **del mismo objetivo**. Sin ese
anterior no hay nada que comparar y no se avisa: el primer analisis de un
proyecto no es un empeoramiento, por mala que sea la nota.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.analysis import Analysis, Dimension, Finding

# Umbral del spec. Por debajo, la variacion es ruido entre commits.
SCORE_DROP_THRESHOLD = 10.0
# Una caida de cobertura menor cabe en anadir codigo nuevo sin sus pruebas
# todavia; a partir de aqui ya es un cambio de habito.
COVERAGE_DROP_THRESHOLD = 15.0


def build_notifications(db: Session, analysis: Analysis) -> list[dict]:
    """Compara con el analisis anterior y devuelve los avisos que procedan."""
    anterior = _analisis_anterior(db, analysis)
    if anterior is None:
        return []

    avisos: list[dict] = []
    _avisar_por_caida_de_nota(analysis, anterior, avisos)
    _avisar_por_hallazgos_nuevos(db, analysis, anterior, avisos)
    _avisar_por_caida_de_cobertura(db, analysis, anterior, avisos)
    return avisos


def persist_notifications(db: Session, analysis: Analysis) -> int:
    """Guarda los avisos del analisis. Devuelve cuantos creo.

    No debe hacer fallar al analisis: si algo va mal aqui, el resultado ya
    esta calculado y es lo que de verdad le importa al usuario.
    """
    from app.models.notification import Notification

    creados = 0
    for aviso in build_notifications(db, analysis):
        db.add(
            Notification(
                id=uuid.uuid4(),
                user_id=analysis.user_id,
                analysis_id=analysis.id,
                **aviso,
            )
        )
        try:
            db.commit()
            creados += 1
        except IntegrityError:
            # El indice unico (analysis_id, kind) impide duplicar un aviso si
            # la tarea se reintenta. No es un error: ya estaba.
            db.rollback()
    return creados


def _analisis_anterior(db: Session, analysis: Analysis) -> Analysis | None:
    """El analisis completado inmediatamente anterior del mismo objetivo."""
    consulta = select(Analysis).where(
        Analysis.id != analysis.id,
        Analysis.status == "completed",
        Analysis.analysis_type == analysis.analysis_type,
        Analysis.created_at < analysis.created_at,
    )
    if analysis.repository_id is not None:
        consulta = consulta.where(Analysis.repository_id == analysis.repository_id)
    elif analysis.app_id is not None:
        consulta = consulta.where(Analysis.app_id == analysis.app_id)
    else:
        return None

    return db.scalars(consulta.order_by(Analysis.created_at.desc()).limit(1)).first()


def _avisar_por_caida_de_nota(actual: Analysis, anterior: Analysis, avisos: list[dict]) -> None:
    if actual.overall_score is None or anterior.overall_score is None:
        return
    caida = float(anterior.overall_score) - float(actual.overall_score)
    if caida <= SCORE_DROP_THRESHOLD:
        return
    avisos.append(
        {
            "kind": "score_drop",
            "severity": "high",
            "title": f"La puntuacion ha bajado {caida:.0f} puntos",
            "body": (
                f"Has pasado de {float(anterior.overall_score):.0f} a "
                f"{float(actual.overall_score):.0f}. Revisa que ha cambiado desde el "
                "analisis anterior."
            ),
        }
    )


def _titulos(db: Session, analysis_id: uuid.UUID, severidades: set[str]) -> set[str]:
    return {
        titulo
        for titulo, severidad in db.execute(
            select(Finding.title, Finding.severity).where(Finding.analysis_id == analysis_id)
        )
        if severidad in severidades
    }


def _avisar_por_hallazgos_nuevos(
    db: Session, actual: Analysis, anterior: Analysis, avisos: list[dict]
) -> None:
    # Se comparan por titulo y no por cantidad: que el total no suba no
    # significa que no haya aparecido un problema nuevo, porque puede haberse
    # arreglado otro a la vez.
    criticos_nuevos = _titulos(db, actual.id, {"critical"}) - _titulos(
        db, anterior.id, {"critical"}
    )
    if criticos_nuevos:
        avisos.append(
            {
                "kind": "new_critical",
                "severity": "critical",
                "title": f"{len(criticos_nuevos)} riesgo(s) critico(s) nuevo(s)",
                "body": "Ha aparecido desde el analisis anterior: "
                + "; ".join(sorted(criticos_nuevos)[:3]),
            }
        )

    seguridad_actual = {
        titulo
        for titulo, tipo, severidad in db.execute(
            select(Finding.title, Finding.type, Finding.severity).where(
                Finding.analysis_id == actual.id
            )
        )
        if tipo in ("security", "secret", "dependency") and severidad in ("critical", "high")
    }
    seguridad_anterior = {
        titulo
        for titulo, tipo, severidad in db.execute(
            select(Finding.title, Finding.type, Finding.severity).where(
                Finding.analysis_id == anterior.id
            )
        )
        if tipo in ("security", "secret", "dependency") and severidad in ("critical", "high")
    }
    nuevas = seguridad_actual - seguridad_anterior
    # Si ya se avisó por critico, no se repite el mismo problema con otra
    # etiqueta.
    if nuevas and not criticos_nuevos:
        avisos.append(
            {
                "kind": "new_vulnerability",
                "severity": "high",
                "title": f"{len(nuevas)} problema(s) de seguridad nuevo(s)",
                "body": "Se ha introducido desde el analisis anterior: "
                + "; ".join(sorted(nuevas)[:3]),
            }
        )


def _cobertura(db: Session, analysis_id: uuid.UUID) -> float | None:
    """Saca la cobertura declarada de las metricas de la dimension de pruebas."""
    dimension = db.scalars(
        select(Dimension).where(
            Dimension.analysis_id == analysis_id, Dimension.name.in_(("reliability", "codigo:reliability"))
        )
    ).first()
    if dimension is None or not dimension.raw_metrics:
        return None
    # La metrica se llama `test_ratio` y es una proporcion (0.4 = 40%).
    valor = dimension.raw_metrics.get("test_ratio")
    return float(valor) * 100 if isinstance(valor, (int, float)) else None


def _avisar_por_caida_de_cobertura(
    db: Session, actual: Analysis, anterior: Analysis, avisos: list[dict]
) -> None:
    ahora = _cobertura(db, actual.id)
    antes = _cobertura(db, anterior.id)
    if ahora is None or antes is None:
        return
    caida = antes - ahora
    if caida <= COVERAGE_DROP_THRESHOLD:
        return
    avisos.append(
        {
            "kind": "coverage_drop",
            "severity": "medium",
            "title": "La proporcion de pruebas ha caido",
            "body": (
                f"Ha pasado de {antes:.0f}% a {ahora:.0f}% respecto al codigo fuente. "
                "Suele indicar codigo nuevo sin pruebas."
            ),
        }
    )
