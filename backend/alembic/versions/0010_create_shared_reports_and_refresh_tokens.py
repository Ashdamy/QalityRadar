# backend/alembic/versions/0010_create_shared_reports_and_refresh_tokens.py
from alembic import op

revision = "0010"
down_revision = "0009"


def upgrade() -> None:
    op.execute("""
        CREATE TABLE shared_reports (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            analysis_id UUID NOT NULL REFERENCES analyses(id) ON DELETE CASCADE,
            token VARCHAR(64) NOT NULL UNIQUE,
            expires_at TIMESTAMPTZ NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
    """)
    op.execute("CREATE INDEX idx_shared_reports_token ON shared_reports(token);")

    op.execute("""
        CREATE TABLE refresh_tokens (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            token_hash VARCHAR(255) NOT NULL,
            expires_at TIMESTAMPTZ NOT NULL,
            revoked BOOLEAN NOT NULL DEFAULT false,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
    """)
    op.execute("CREATE INDEX idx_refresh_tokens_user_id ON refresh_tokens(user_id);")
    op.execute("CREATE INDEX idx_refresh_tokens_hash ON refresh_tokens(token_hash);")


def downgrade() -> None:
    op.execute("DROP TABLE refresh_tokens;")
    op.execute("DROP TABLE shared_reports;")
