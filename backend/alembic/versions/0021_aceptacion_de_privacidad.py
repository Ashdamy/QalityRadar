"""Prueba de que el usuario acepto la politica de privacidad.

La Ley 1581 de 2012 pide una autorizacion previa, expresa e informada para
tratar datos personales, y que el responsable pueda demostrarla despues
(Decreto 1377 de 2013, art. 8). Sin esta columna no habia forma de probar que
nadie acepto nada.

`privacy_version` dice que texto se acepto: cuando la politica cambie de forma
sustancial, se sabra quien acepto la anterior.

Las cuentas existentes quedan a nulo a proposito: no aceptaron nada, y fingir
lo contrario seria fabricar la prueba.
"""

import sqlalchemy as sa
from alembic import op

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("privacy_accepted_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("privacy_version", sa.String(20), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "privacy_version")
    op.drop_column("users", "privacy_accepted_at")
