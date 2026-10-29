"""Desglose de cada dimension por subcaracteristica de ISO/IEC 25010:2023.

Columna propia en vez de meterlo en `raw_metrics`: `raw_metrics` es lo que
midieron los analizadores (la entrada de la puntuacion, que ademas se copia a
`analyses.raw_data` y lee la comprobacion de correspondencia del modo
combinado); el desglose es el resultado de puntuar. Mezclarlos haria que una
clave calculada pudiera confundirse con una medida.

Nula en los analisis anteriores: no se recalcula hacia atras porque sus
metricas se puntuaron con rubricas que ya pudieron cambiar, y un desglose que
no cuadrase con la nota guardada seria peor que ninguno.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0022"
down_revision = "0021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("dimensions", sa.Column("subcharacteristics", JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column("dimensions", "subcharacteristics")
