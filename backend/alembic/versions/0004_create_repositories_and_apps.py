# backend/alembic/versions/0004_create_repositories_and_apps.py
from alembic import op

revision = "0004"
down_revision = "0003"


def upgrade() -> None:
    op.execute("""
        CREATE TABLE repositories (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            github_id BIGINT NOT NULL,
            name VARCHAR(255) NOT NULL,
            full_name VARCHAR(500) NOT NULL,
            default_branch VARCHAR(255) NOT NULL DEFAULT 'main',
            is_private BOOLEAN NOT NULL DEFAULT false,
            last_analyzed_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (user_id, github_id)
        );
    """)
    op.execute("CREATE INDEX idx_repositories_user_id ON repositories(user_id);")

    op.execute("""
        CREATE TABLE deployed_apps (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id UUID REFERENCES users(id) ON DELETE CASCADE,
            name VARCHAR(255),
            url TEXT NOT NULL,
            last_analyzed_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
    """)
    op.execute("CREATE INDEX idx_deployed_apps_user_id ON deployed_apps(user_id);")
    op.execute("CREATE INDEX idx_deployed_apps_url ON deployed_apps(url);")


def downgrade() -> None:
    op.execute("DROP TABLE deployed_apps;")
    op.execute("DROP TABLE repositories;")
