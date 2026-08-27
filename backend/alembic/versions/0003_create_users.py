# backend/alembic/versions/0003_create_users.py
from alembic import op

revision = "0003"
down_revision = "0002"


def upgrade() -> None:
    op.execute("""
        CREATE TABLE users (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            email VARCHAR(255) NOT NULL UNIQUE,
            password_hash VARCHAR(255),
            github_id BIGINT UNIQUE,
            github_username VARCHAR(255),
            github_access_token_encrypted TEXT,
            avatar_url TEXT,
            plan plan_tier NOT NULL DEFAULT 'free',
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT users_auth_method_chk CHECK (password_hash IS NOT NULL OR github_id IS NOT NULL)
        );
    """)


def downgrade() -> None:
    op.execute("DROP TABLE users;")
