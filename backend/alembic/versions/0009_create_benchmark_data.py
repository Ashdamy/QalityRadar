# backend/alembic/versions/0009_create_benchmark_data.py
import sqlalchemy as sa
from alembic import op

revision = "0009"
down_revision = "0008"

SEED_ROWS = [
    ("javascript", "maintainability", 62.0), ("javascript", "security", 58.0),
    ("javascript", "reliability", 60.0), ("python", "maintainability", 68.0),
    ("python", "security", 65.0), ("python", "reliability", 66.0),
    ("typescript", "maintainability", 71.0), ("typescript", "security", 67.0),
    ("typescript", "reliability", 69.0),
]


def upgrade() -> None:
    op.execute("""
        CREATE TABLE benchmark_data (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            language VARCHAR(50) NOT NULL,
            dimension VARCHAR(50) NOT NULL,
            avg_score NUMERIC(5,2) NOT NULL,
            source VARCHAR(255) NOT NULL,
            is_simulated BOOLEAN NOT NULL DEFAULT true,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (language, dimension)
        );
    """)
    for language, dimension, avg_score in SEED_ROWS:
        op.execute(
            sa.text(
                "INSERT INTO benchmark_data (language, dimension, avg_score, source, is_simulated) "
                "VALUES (:language, :dimension, :avg_score, :source, true)"
            ).bindparams(
                language=language,
                dimension=dimension,
                avg_score=avg_score,
                source="State of Open Source 2025 (simulado)",
            )
        )


def downgrade() -> None:
    op.execute("DROP TABLE benchmark_data;")
