"""Cancelar un analisis en marcha y reintentar uno fallido.

`cancelled` se anade al enum de estados. En Postgres, ALTER TYPE ... ADD VALUE
no puede ir dentro de una transaccion, y Alembic abre una por migracion: de ahi
el COMMIT explicito antes.

`retry_count` acota los reintentos gratuitos. Sin el, reintentar sin gastar
cuota seria un bucle infinito con el que saltarse los limites de uso.
"""

import sqlalchemy as sa
from alembic import op

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("COMMIT")
    op.execute("ALTER TYPE analysis_status ADD VALUE IF NOT EXISTS 'cancelled'")

    op.add_column(
        "analyses",
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("analyses", "retry_count")
    # El valor del enum no se quita: Postgres no permite eliminar valores de un
    # tipo enumerado, y dejarlo no molesta a nadie.
