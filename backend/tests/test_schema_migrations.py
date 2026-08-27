import uuid

import pytest
import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError

from app.core.database import engine

EXPECTED_TABLES = {
    "users", "repositories", "deployed_apps", "analyses", "dimensions", "findings",
    "discrepancies", "analysis_comparisons", "improvements", "regressions",
    "benchmark_data", "shared_reports", "refresh_tokens",
}


def test_all_tables_exist_after_migrations():
    inspector = sa.inspect(engine)
    existing = set(inspector.get_table_names())
    assert EXPECTED_TABLES.issubset(existing)


def test_benchmark_data_is_seeded():
    with engine.connect() as conn:
        count = conn.execute(sa.text("SELECT COUNT(*) FROM benchmark_data")).scalar_one()
    assert count >= 9


def test_analyses_target_chk_constraint_exists():
    with engine.connect() as conn:
        conname = conn.execute(
            sa.text(
                "SELECT conname FROM pg_constraint "
                "WHERE conrelid = 'analyses'::regclass AND contype = 'c' AND conname = 'analyses_target_chk'"
            )
        ).scalar_one_or_none()
    assert conname == "analyses_target_chk"


def test_deleting_user_cascades_to_repositories_and_analyses():
    conn = engine.connect()
    trans = conn.begin()
    try:
        user_id = uuid.uuid4()
        repo_id = uuid.uuid4()
        analysis_id = uuid.uuid4()

        conn.execute(
            sa.text("INSERT INTO users (id, email, password_hash) VALUES (:id, :email, 'x')"),
            {"id": user_id, "email": f"{user_id}@example.com"},
        )
        conn.execute(
            sa.text(
                "INSERT INTO repositories (id, user_id, github_id, name, full_name) "
                "VALUES (:id, :user_id, 424242, 'repo', 'owner/repo')"
            ),
            {"id": repo_id, "user_id": user_id},
        )
        conn.execute(
            sa.text(
                "INSERT INTO analyses (id, user_id, repository_id, analysis_type) "
                "VALUES (:id, :user_id, :repo_id, 'repository')"
            ),
            {"id": analysis_id, "user_id": user_id, "repo_id": repo_id},
        )

        conn.execute(sa.text("DELETE FROM users WHERE id = :id"), {"id": user_id})

        repo_count = conn.execute(
            sa.text("SELECT COUNT(*) FROM repositories WHERE id = :id"), {"id": repo_id}
        ).scalar_one()
        analysis_count = conn.execute(
            sa.text("SELECT COUNT(*) FROM analyses WHERE id = :id"), {"id": analysis_id}
        ).scalar_one()

        assert repo_count == 0
        assert analysis_count == 0
    finally:
        trans.rollback()
        conn.close()


def test_repositories_unique_user_github_id_enforced():
    conn = engine.connect()
    trans = conn.begin()
    try:
        user_id = uuid.uuid4()
        conn.execute(
            sa.text("INSERT INTO users (id, email, password_hash) VALUES (:id, :email, 'x')"),
            {"id": user_id, "email": f"{user_id}@example.com"},
        )
        conn.execute(
            sa.text(
                "INSERT INTO repositories (id, user_id, github_id, name, full_name) "
                "VALUES (gen_random_uuid(), :user_id, 999, 'repo', 'owner/repo')"
            ),
            {"user_id": user_id},
        )

        with pytest.raises(IntegrityError):
            with conn.begin_nested():
                conn.execute(
                    sa.text(
                        "INSERT INTO repositories (id, user_id, github_id, name, full_name) "
                        "VALUES (gen_random_uuid(), :user_id, 999, 'repo2', 'owner/repo2')"
                    ),
                    {"user_id": user_id},
                )
    finally:
        trans.rollback()
        conn.close()
