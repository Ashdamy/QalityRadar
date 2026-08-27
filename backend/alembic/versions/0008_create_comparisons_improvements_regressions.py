# backend/alembic/versions/0008_create_comparisons_improvements_regressions.py
from alembic import op

revision = "0008"
down_revision = "0007"


def upgrade() -> None:
    op.execute("""
        CREATE TABLE analysis_comparisons (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            analysis_1_id UUID NOT NULL REFERENCES analyses(id) ON DELETE CASCADE,
            analysis_2_id UUID NOT NULL REFERENCES analyses(id) ON DELETE CASCADE,
            score_delta NUMERIC(5,2) NOT NULL,
            improvements_count INT NOT NULL DEFAULT 0,
            regressions_count INT NOT NULL DEFAULT 0,
            summary_text TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (analysis_1_id, analysis_2_id)
        );
    """)
    op.execute("CREATE INDEX idx_comparisons_analysis_2 ON analysis_comparisons(analysis_2_id);")

    op.execute("""
        CREATE TABLE improvements (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            comparison_id UUID NOT NULL REFERENCES analysis_comparisons(id) ON DELETE CASCADE,
            dimension VARCHAR(50) NOT NULL,
            previous_score NUMERIC(5,2),
            current_score NUMERIC(5,2),
            delta NUMERIC(5,2) NOT NULL,
            description TEXT NOT NULL,
            evidence JSONB
        );
    """)
    op.execute("CREATE INDEX idx_improvements_comparison_id ON improvements(comparison_id);")

    op.execute("""
        CREATE TABLE regressions (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            comparison_id UUID NOT NULL REFERENCES analysis_comparisons(id) ON DELETE CASCADE,
            dimension VARCHAR(50) NOT NULL,
            previous_score NUMERIC(5,2),
            current_score NUMERIC(5,2),
            delta NUMERIC(5,2) NOT NULL,
            description TEXT NOT NULL,
            evidence JSONB,
            severity finding_severity NOT NULL
        );
    """)
    op.execute("CREATE INDEX idx_regressions_comparison_id ON regressions(comparison_id);")


def downgrade() -> None:
    op.execute("DROP TABLE regressions;")
    op.execute("DROP TABLE improvements;")
    op.execute("DROP TABLE analysis_comparisons;")
