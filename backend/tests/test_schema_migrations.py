import sqlalchemy as sa

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
