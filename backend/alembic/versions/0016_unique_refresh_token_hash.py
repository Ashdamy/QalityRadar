"""El hash de un token de refresco no puede repetirse.

Dos filas con el mismo hash, una viva y otra revocada, hacen que la busqueda
devuelva una u otra sin criterio: cerrar sesion revoca una y la otra sigue
abriendo. Es exactamente lo que pasaba antes de que los tokens llevaran `jti`,
porque dos emitidos en el mismo segundo salian identicos.

El `jti` ya lo impide. Esto lo pone por escrito donde no depende de que nadie
se acuerde: si algun dia vuelve a ocurrir, la base de datos se niega en vez de
dejar una sesion en un estado ambiguo.
"""

import sqlalchemy as sa
from alembic import op

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Los duplicados que dejo el periodo sin `jti`: se conserva el mas
    # reciente, que es el que la aplicacion habria acabado usando.
    op.execute(
        sa.text(
            """
            DELETE FROM refresh_tokens a
            USING refresh_tokens b
            WHERE a.token_hash = b.token_hash
              AND (a.created_at, a.id) < (b.created_at, b.id)
            """
        )
    )
    op.create_unique_constraint("uq_refresh_tokens_hash", "refresh_tokens", ["token_hash"])


def downgrade() -> None:
    op.drop_constraint("uq_refresh_tokens_hash", "refresh_tokens", type_="unique")
