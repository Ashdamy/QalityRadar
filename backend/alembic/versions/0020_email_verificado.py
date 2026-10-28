"""Verificacion del correo.

`email_verified_at` nulo significa que nadie ha demostrado que el correo es
suyo. Hasta ahora bastaba con escribir uno cualquiera para tener cuenta, y como
los limites de uso son por cuenta, quien quisiera saltarselos solo tenia que
inventarse correos.

Las cuentas que ya existen se dan por verificadas: son anteriores a la
exigencia y dejarlas fuera de golpe no protege nada, porque el proyecto aun no
esta abierto al publico.
"""

import sqlalchemy as sa
from alembic import op

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.execute("UPDATE users SET email_verified_at = created_at")


def downgrade() -> None:
    op.drop_column("users", "email_verified_at")
