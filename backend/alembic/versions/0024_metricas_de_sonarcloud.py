"""Metricas importadas de SonarCloud, ligadas a un analisis.

Van en el propio analisis (clave, metricas y fecha) y no en `raw_metrics` de
la dimension: `raw_metrics` es lo que midieron nuestros analizadores, y estas
las midio otro. Al puntuar se juntan, pero guardarlas aparte permite volver a
importarlas o saber cuando se trajeron sin tocar lo medido.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0024"
down_revision = "0023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("analyses", sa.Column("sonar_project_key", sa.String(400), nullable=True))
    op.add_column("analyses", sa.Column("sonar_metrics", JSONB(), nullable=True))
    op.add_column("analyses", sa.Column("sonar_imported_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("analyses", "sonar_imported_at")
    op.drop_column("analyses", "sonar_metrics")
    op.drop_column("analyses", "sonar_project_key")
