"""Marca de rotacion en los tokens de refresco.

Rotar significa que cada renovacion emite un token nuevo y anula el anterior:
un token robado deja de servir en cuanto el dueno renueva, en vez de valer los
30 dias enteros.

La columna guarda **cuando** se roto, no solo que se roto. Hace falta para
distinguir dos casos que por lo demas son identicos: el token que acaba de
rotarse hace un segundo (dos pestanas renovando a la vez, que no es un ataque)
y el que se anulo al cerrar sesion.
"""

import sqlalchemy as sa
from alembic import op

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "refresh_tokens",
        sa.Column("rotated_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("refresh_tokens", "rotated_at")
