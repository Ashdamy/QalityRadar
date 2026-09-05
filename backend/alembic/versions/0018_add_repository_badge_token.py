"""Token publico de la insignia del README.

La insignia es un SVG con la nota que el dueno del repositorio pega en su
portada, asi que su token es publico por definicion y **no caduca**: uno que se
apagara solo dejaria una imagen rota en el README de un proyecto ajeno.

Va en la tabla de repositorios y no en una propia porque es uno por
repositorio: pedir la insignia dos veces devuelve la misma, que es lo que hace
falta para poder pegarla y olvidarse.
"""

import sqlalchemy as sa
from alembic import op

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("repositories", sa.Column("badge_token", sa.String(64), nullable=True))
    op.create_unique_constraint("uq_repositories_badge_token", "repositories", ["badge_token"])


def downgrade() -> None:
    op.drop_constraint("uq_repositories_badge_token", "repositories", type_="unique")
    op.drop_column("repositories", "badge_token")
