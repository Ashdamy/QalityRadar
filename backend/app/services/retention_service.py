"""Purga de analisis antiguos.

Sin esto la base crece sin limite: cada analisis arrastra sus dimensiones y
sus hallazgos, y un repositorio analizado a diario acumula miles de filas que
nadie va a mirar.

Dos reglas, y una que manda sobre las otras dos:

- Como mucho 50 analisis por repositorio (o aplicacion).
- Nada mas viejo de 90 dias.
- **Pero siempre se conservan los 10 ultimos**, aunque los 10 sean de hace dos
  anos. Un proyecto que se analizo en su dia y se dejo aparcado no debe
  quedarse sin historico: si se retoma, la comparacion con el pasado es justo
  lo que da valor.
"""

from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models.analysis import Analysis

MAX_PER_TARGET = 50
RETENTION_DAYS = 90
ALWAYS_KEEP = 10


def purge_old_analyses(db: Session) -> int:
    """Borra los analisis sobrantes. Devuelve cuantos elimino.

    Las dimensiones, hallazgos y discrepancias caen solas: sus claves ajenas
    estan declaradas con ON DELETE CASCADE.
    """
    corte = datetime.now(timezone.utc) - timedelta(days=RETENTION_DAYS)
    a_borrar: list = []

    for columna in (Analysis.repository_id, Analysis.app_id):
        objetivos = db.scalars(select(columna).where(columna.is_not(None)).distinct()).all()
        for objetivo in objetivos:
            # Del mas nuevo al mas viejo: los primeros son los que se quedan.
            historico = db.scalars(
                select(Analysis)
                .where(columna == objetivo)
                .order_by(Analysis.created_at.desc())
            ).all()

            protegidos = historico[:ALWAYS_KEEP]
            candidatos = historico[ALWAYS_KEEP:]

            for indice, analisis in enumerate(candidatos, start=ALWAYS_KEEP):
                creado = analisis.created_at
                if creado is not None and creado.tzinfo is None:
                    creado = creado.replace(tzinfo=timezone.utc)

                sobra_por_cantidad = indice >= MAX_PER_TARGET
                sobra_por_antiguedad = creado is not None and creado < corte
                if sobra_por_cantidad or sobra_por_antiguedad:
                    a_borrar.append(analisis.id)

            del protegidos  # explicito: estan fuera del borrado por diseno

    if not a_borrar:
        return 0

    # Un analisis combinado puede aparecer dos veces (tiene repositorio y
    # aplicacion), asi que se deduplica antes de borrar.
    unicos = list(dict.fromkeys(a_borrar))
    db.execute(delete(Analysis).where(Analysis.id.in_(unicos)))
    db.commit()
    return len(unicos)
