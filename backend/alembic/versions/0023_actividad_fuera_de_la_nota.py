"""La actividad del proyecto sale de la nota ISO.

Dos cambios:

1. `dimensions.weight` admite 0. La actividad se sigue guardando como
   dimension (para ensenarla como indicador de salud), pero con peso 0.

2. Se recalcula la nota global de los analisis de REPOSITORIO ya guardados
   con la formula nueva. Sin esto, el primer analisis despues del cambio
   "bajaria" de golpe respecto al anterior (Flask, de 64 a 57,6) sin que el
   codigo hubiera cambiado: el aviso de caida de nota saltaria en falso y la
   grafica de evolucion tendria un escalon que no significa nada. Se rehacen
   tambien las diferencias de nota guardadas en las comparaciones.

   Los analisis COMBINADOS ya guardados conservan su nota: su explicacion de
   la discrepancia cita las notas en prosa, y reescribirla seria inventarla.
   Los de URL no cambian: nunca tuvieron actividad.

La formula va copiada aqui y no importada de la aplicacion: una migracion
tiene que dar lo mismo dentro de un ano, cuando scoring_service ya sea otro.
Una prueba comprueba que hoy coinciden.

Reversible: el downgrade recalcula con los pesos de antes y devuelve la
actividad al 15%.
"""

import sqlalchemy as sa
from alembic import op

revision = "0023"
down_revision = "0022"
branch_labels = None
depends_on = None

PESOS_VIEJOS = {
    "functional_suitability": 0.15,
    "reliability": 0.20,
    "security": 0.20,
    "maintainability": 0.20,
    "portability": 0.10,
    "project_activity": 0.15,
}
_ISO = {d: p for d, p in PESOS_VIEJOS.items() if d != "project_activity"}
PESOS_NUEVOS = {d: p / sum(_ISO.values()) for d, p in _ISO.items()}

TECHO_CRITICO = 40.0
TECHO_ALTO = 70.0


def nota(dimensiones: dict[str, float], severidades: set[str], pesos: dict[str, float]) -> float:
    """Media ponderada sobre lo medido, con los techos por gravedad."""
    presentes = {d: s for d, s in dimensiones.items() if d in pesos}
    if not presentes:
        return 0.0
    valor = sum(pesos[d] * s for d, s in presentes.items()) / sum(pesos[d] for d in presentes)
    if "critical" in severidades:
        valor = min(valor, TECHO_CRITICO)
    elif "high" in severidades:
        valor = min(valor, TECHO_ALTO)
    return round(valor, 2)


def _recalcular(pesos: dict[str, float], peso_actividad: float) -> None:
    bind = op.get_bind()
    analisis = bind.execute(
        sa.text(
            "SELECT id FROM analyses WHERE analysis_type = 'repository' AND status = 'completed'"
        )
    ).scalars().all()
    for analysis_id in analisis:
        dimensiones = {
            nombre: float(score)
            for nombre, score in bind.execute(
                sa.text("SELECT name, score FROM dimensions WHERE analysis_id = :id"),
                {"id": analysis_id},
            )
        }
        if not dimensiones:
            continue
        severidades = set(
            bind.execute(
                sa.text("SELECT DISTINCT severity::text FROM findings WHERE analysis_id = :id"),
                {"id": analysis_id},
            ).scalars()
        )
        bind.execute(
            sa.text("UPDATE analyses SET overall_score = :nota WHERE id = :id"),
            {"nota": nota(dimensiones, severidades, pesos), "id": analysis_id},
        )
        for nombre, peso in {**pesos, "project_activity": peso_actividad}.items():
            bind.execute(
                sa.text("UPDATE dimensions SET weight = :peso WHERE analysis_id = :id AND name = :nombre"),
                {"peso": round(peso, 3), "id": analysis_id, "nombre": nombre},
            )

    # Las diferencias guardadas en las comparaciones, con las notas nuevas.
    bind.execute(
        sa.text(
            """
            UPDATE analysis_comparisons c
               SET score_delta = COALESCE(a2.overall_score, 0) - COALESCE(a1.overall_score, 0)
              FROM analyses a1, analyses a2
             WHERE a1.id = c.analysis_1_id AND a2.id = c.analysis_2_id
               AND a2.analysis_type = 'repository'
            """
        )
    )


def upgrade() -> None:
    op.drop_constraint("dimensions_weight_check", "dimensions", type_="check")
    op.create_check_constraint("dimensions_weight_check", "dimensions", "weight >= 0 AND weight <= 1")
    _recalcular(PESOS_NUEVOS, peso_actividad=0.0)


def downgrade() -> None:
    _recalcular(PESOS_VIEJOS, peso_actividad=PESOS_VIEJOS["project_activity"])
    op.drop_constraint("dimensions_weight_check", "dimensions", type_="check")
    op.create_check_constraint("dimensions_weight_check", "dimensions", "weight > 0 AND weight <= 1")
