"""Quien lanzo cada analisis: la persona o la vigilancia.

Hace falta para saber a quien hay que contarle el resultado. Si el analisis lo
pidio el usuario, esta delante de la pantalla viendolo; avisarle de algo que
tiene a la vista es ruido. Si lo lanzo un monitor, no se ha enterado de nada, y
entonces el aviso es justo lo que da sentido a la funcion.

No se deduce de la existencia de un monitor: alguien puede empezar a vigilar un
proyecto despues, y eso reescribiria la historia de analisis anteriores que en
su momento fueron manuales.
"""

from alembic import op

revision = "0014"
down_revision = "0013"


def upgrade() -> None:
    op.execute(
        "ALTER TABLE analyses ADD COLUMN triggered_by VARCHAR(20) NOT NULL DEFAULT 'manual';"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE analyses DROP COLUMN triggered_by;")
