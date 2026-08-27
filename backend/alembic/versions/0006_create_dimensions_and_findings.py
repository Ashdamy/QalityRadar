# backend/alembic/versions/0006_create_dimensions_and_findings.py
from alembic import op

revision = "0006"
down_revision = "0005"


def upgrade() -> None:
    op.execute("""
        CREATE TABLE dimensions (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            analysis_id UUID NOT NULL REFERENCES analyses(id) ON DELETE CASCADE,
            name VARCHAR(50) NOT NULL,
            score NUMERIC(5,2) NOT NULL CHECK (score >= 0 AND score <= 100),
            weight NUMERIC(4,3) NOT NULL CHECK (weight > 0 AND weight <= 1),
            raw_metrics JSONB,
            UNIQUE (analysis_id, name)
        );
    """)
    op.execute("CREATE INDEX idx_dimensions_analysis_id ON dimensions(analysis_id);")

    op.execute("""
        CREATE TABLE findings (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            analysis_id UUID NOT NULL REFERENCES analyses(id) ON DELETE CASCADE,
            type finding_type NOT NULL,
            severity finding_severity NOT NULL,
            title VARCHAR(500) NOT NULL,
            description TEXT NOT NULL,
            file_path TEXT,
            url TEXT,
            recommendation TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
    """)
    op.execute("CREATE INDEX idx_findings_analysis_id ON findings(analysis_id);")
    op.execute("CREATE INDEX idx_findings_analysis_severity ON findings(analysis_id, severity);")


def downgrade() -> None:
    op.execute("DROP TABLE findings;")
    op.execute("DROP TABLE dimensions;")
