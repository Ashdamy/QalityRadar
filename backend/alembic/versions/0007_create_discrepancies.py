# backend/alembic/versions/0007_create_discrepancies.py
from alembic import op

revision = "0007"
down_revision = "0006"


def upgrade() -> None:
    op.execute("""
        CREATE TABLE discrepancies (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            analysis_id UUID NOT NULL UNIQUE REFERENCES analyses(id) ON DELETE CASCADE,
            repo_score NUMERIC(5,2) NOT NULL,
            url_score NUMERIC(5,2) NOT NULL,
            delta NUMERIC(5,2) NOT NULL,
            explanation TEXT NOT NULL,
            recommendations TEXT
        );
    """)


def downgrade() -> None:
    op.execute("DROP TABLE discrepancies;")
