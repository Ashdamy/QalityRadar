# backend/alembic/versions/0002_create_enums.py
from alembic import op

revision = "0002"
down_revision = "0001"


def upgrade() -> None:
    op.execute("CREATE TYPE analysis_type AS ENUM ('repository', 'url', 'combined');")
    op.execute(
        "CREATE TYPE analysis_status AS ENUM "
        "('pending', 'cloning', 'running', 'scoring', 'completed', 'failed', 'timeout');"
    )
    op.execute("CREATE TYPE finding_severity AS ENUM ('critical', 'high', 'medium', 'low', 'info');")
    op.execute(
        "CREATE TYPE finding_type AS ENUM ("
        "'security', 'test_coverage', 'documentation', 'dependency', "
        "'cicd', 'structure', 'activity', "
        "'performance', 'accessibility', 'seo', 'compatibility', 'usability');"
    )
    op.execute("CREATE TYPE plan_tier AS ENUM ('free');")


def downgrade() -> None:
    op.execute("DROP TYPE plan_tier;")
    op.execute("DROP TYPE finding_type;")
    op.execute("DROP TYPE finding_severity;")
    op.execute("DROP TYPE analysis_status;")
    op.execute("DROP TYPE analysis_type;")
