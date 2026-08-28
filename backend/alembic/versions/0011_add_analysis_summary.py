"""Resumen ejecutivo de un analisis individual.

Hasta ahora el resumen generado solo existia al comparar dos analisis. Un
analisis suelto tambien merece una lectura en prosa de sus resultados, asi
que se guarda junto al resto del analisis en vez de regenerarlo en cada
consulta: el texto depende de datos que ya no cambian.
"""

from alembic import op

revision = "0011"
down_revision = "0010"


def upgrade() -> None:
    op.execute("ALTER TABLE analyses ADD COLUMN summary_text TEXT;")
    op.execute("ALTER TABLE analyses ADD COLUMN summary_source VARCHAR(20);")


def downgrade() -> None:
    op.execute("ALTER TABLE analyses DROP COLUMN summary_source;")
    op.execute("ALTER TABLE analyses DROP COLUMN summary_text;")
