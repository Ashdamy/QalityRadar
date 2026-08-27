# backend/alembic/versions/0005_create_analyses.py
from alembic import op

revision = "0005"
down_revision = "0004"


def upgrade() -> None:
    op.execute("""
        CREATE TABLE analyses (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id UUID REFERENCES users(id) ON DELETE SET NULL,
            repository_id UUID REFERENCES repositories(id) ON DELETE CASCADE,
            app_id UUID REFERENCES deployed_apps(id) ON DELETE CASCADE,
            analysis_type analysis_type NOT NULL,
            status analysis_status NOT NULL DEFAULT 'pending',
            overall_score NUMERIC(5,2),
            confidence_level NUMERIC(5,2),
            commit_hash VARCHAR(40),
            commit_message TEXT,
            branch VARCHAR(255),
            raw_data JSONB,
            error_message TEXT,
            started_at TIMESTAMPTZ,
            completed_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT analyses_target_chk CHECK (
                (repository_id IS NOT NULL AND app_id IS NULL) OR
                (repository_id IS NULL AND app_id IS NOT NULL) OR
                (repository_id IS NOT NULL AND app_id IS NOT NULL)
            )
        );
    """)
    op.execute("CREATE INDEX idx_analyses_repository_timeline ON analyses(repository_id, created_at DESC);")
    op.execute("CREATE INDEX idx_analyses_app_timeline ON analyses(app_id, created_at DESC);")
    op.execute("CREATE INDEX idx_analyses_user_created ON analyses(user_id, created_at DESC);")
    op.execute(
        "CREATE INDEX idx_analyses_status ON analyses(status) "
        "WHERE status IN ('pending', 'cloning', 'running', 'scoring');"
    )


def downgrade() -> None:
    op.execute("DROP TABLE analyses;")
