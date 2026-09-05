"""Rastro de entradas, salidas y fallos de cada cuenta.

Sin esto no habia forma de contestar la pregunta que se hace despues de un
susto: si alguien entro en una cuenta ajena, cuando, y desde donde.

Se guarda lo minimo que la contesta. El correo de un intento contra una cuenta
que no existe **no** se guarda: seria construir la lista de correos que alguien
probo, que es justo lo que no hace falta tener.

La tabla se purga a los 90 dias con el resto del mantenimiento: una IP es un
dato personal y guardarla para siempre no ayuda a nadie.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import INET

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "auth_events",
        sa.Column(
            "id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "user_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("event", sa.String(40), nullable=False),
        sa.Column("ip", INET, nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    # La consulta que se hace de verdad: que le paso a esta cuenta, lo mas
    # reciente primero.
    op.create_index(
        "idx_auth_events_user_created",
        "auth_events",
        ["user_id", sa.text("created_at DESC")],
    )
    # Y la de la purga.
    op.create_index("idx_auth_events_created", "auth_events", ["created_at"])


def downgrade() -> None:
    op.drop_index("idx_auth_events_created", table_name="auth_events")
    op.drop_index("idx_auth_events_user_created", table_name="auth_events")
    op.drop_table("auth_events")
