"""Migration regression tests."""

from __future__ import annotations

import importlib
import os
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine


def test_outputs_unique_migration_deduplicates_before_constraint(monkeypatch):
    """The output idempotency migration must remove duplicates before adding the constraint."""
    migration = importlib.import_module(
        "ceq_api.alembic.versions.20260514_outputs_job_storage_unique"
    )

    class FakeOp:
        def __init__(self):
            self.executed: list[str] = []
            self.constraints: list[tuple[str, str, list[str]]] = []
            self.dropped: list[tuple[str, str, str]] = []

        def execute(self, sql):
            self.executed.append(str(sql))

        def create_unique_constraint(self, name, table_name, columns):
            self.constraints.append((name, table_name, columns))

        def drop_constraint(self, name, table_name, type_):
            self.dropped.append((name, table_name, type_))

    fake_op = FakeOp()
    monkeypatch.setattr(migration, "op", fake_op)

    migration.upgrade()
    migration.downgrade()

    dedupe_sql = fake_op.executed[0]
    assert "ROW_NUMBER() OVER" in dedupe_sql
    assert "PARTITION BY job_id, storage_uri" in dedupe_sql
    assert "DELETE FROM outputs" in dedupe_sql
    assert fake_op.constraints == [
        ("uq_outputs_job_storage_uri", "outputs", ["job_id", "storage_uri"])
    ]
    assert fake_op.dropped == [("uq_outputs_job_storage_uri", "outputs", "unique")]


@pytest.mark.skipif(
    not os.getenv("CEQ_TEST_POSTGRES_URL"),
    reason="set CEQ_TEST_POSTGRES_URL to run PostgreSQL-backed migration regression",
)
@pytest.mark.asyncio
async def test_outputs_unique_migration_on_postgres(monkeypatch):
    """Optional PostgreSQL proof for the window-function dedupe migration."""
    migration = importlib.import_module(
        "ceq_api.alembic.versions.20260514_outputs_job_storage_unique"
    )
    database_url = os.environ["CEQ_TEST_POSTGRES_URL"]
    engine = create_async_engine(database_url)
    schema_name = f"ceq_migration_test_{uuid4().hex}"

    try:
        async with engine.begin() as async_conn:
            await async_conn.execute(text(f'CREATE SCHEMA "{schema_name}"'))
            await async_conn.execute(text(f'SET search_path TO "{schema_name}"'))
            await async_conn.execute(
                text(
                    """
                    CREATE TABLE outputs (
                        id UUID PRIMARY KEY,
                        job_id UUID NOT NULL,
                        storage_uri TEXT NOT NULL,
                        created_at TIMESTAMPTZ,
                        updated_at TIMESTAMPTZ
                    )
                    """
                )
            )
            job_id = uuid4()
            storage_uri = "r2://ceq-assets/outputs/job/output.png"
            await async_conn.execute(
                text(
                    """
                    INSERT INTO outputs (id, job_id, storage_uri, created_at, updated_at)
                    VALUES
                      (:old_id, :job_id, :storage_uri, now() - interval '2 minutes', now() - interval '2 minutes'),
                      (:new_id, :job_id, :storage_uri, now() - interval '1 minute', now() - interval '1 minute')
                    """
                ),
                {
                    "old_id": uuid4(),
                    "new_id": uuid4(),
                    "job_id": job_id,
                    "storage_uri": storage_uri,
                },
            )

            def run_upgrade(sync_conn):
                from alembic.migration import MigrationContext
                from alembic.operations import Operations

                context = MigrationContext.configure(sync_conn)
                monkeypatch.setattr(migration, "op", Operations(context))
                migration.upgrade()

            await async_conn.run_sync(run_upgrade)

            rows = await async_conn.execute(text("SELECT count(*) FROM outputs"))
            assert rows.scalar_one() == 1

            constraint = await async_conn.execute(
                text(
                    """
                    SELECT count(*)
                    FROM pg_constraint
                    WHERE conname = 'uq_outputs_job_storage_uri'
                      AND conrelid = 'outputs'::regclass
                    """
                )
            )
            assert constraint.scalar_one() == 1
    finally:
        async with engine.begin() as async_conn:
            await async_conn.execute(text(f'DROP SCHEMA IF EXISTS "{schema_name}" CASCADE'))
        await engine.dispose()
