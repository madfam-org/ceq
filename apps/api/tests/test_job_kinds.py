"""Tests for job kinds (RFC 0061): the closed set, where a job is queued,
where a cancel looks for it, the model guard and the migration.

The capability lease itself is covered in ``test_worker_lease.py``.
"""

from __future__ import annotations

import importlib
import json
from datetime import UTC, datetime
from uuid import uuid4

import fakeredis.aioredis as fakeredis
import pytest

from ceq_api import job_kinds
from ceq_api.db import redis as redis_module
from ceq_api.job_kinds import (
    ALL_PENDING_KEYS,
    COMFY_PENDING_KEY,
    JOB_KINDS,
    JobKind,
    pending_key_for_kind,
    validate_job_kind,
)
from ceq_api.models.job import Job
from ceq_api.routers.jobs import JobStatusResponse, _remove_pending_job


@pytest.fixture
async def redis():
    client = fakeredis.FakeRedis(decode_responses=True)
    yield client
    await client.aclose()


class TestKindSet:
    def test_comfy_keeps_the_original_list(self):
        assert pending_key_for_kind("comfy") == "ceq:jobs:pending"
        assert COMFY_PENDING_KEY == "ceq:jobs:pending"

    def test_every_other_kind_has_its_own_list(self):
        keys = {kind: pending_key_for_kind(kind) for kind in JOB_KINDS}
        assert len(set(keys.values())) == len(JOB_KINDS)
        for kind, key in keys.items():
            if kind != JobKind.COMFY.value:
                assert key == f"ceq:jobs:pending:{kind}"
        assert set(ALL_PENDING_KEYS) == set(keys.values())

    def test_unknown_kind_is_rejected(self):
        with pytest.raises(ValueError, match="Unknown job kind"):
            validate_job_kind("render.gpu")
        with pytest.raises(ValueError):
            pending_key_for_kind("")


class TestEnqueueRouting:
    async def test_job_without_a_kind_goes_to_the_comfy_list(self, redis, monkeypatch):
        monkeypatch.setattr(redis_module, "_redis", redis)

        await redis_module.enqueue_job({"id": "a"})

        assert await redis.llen(COMFY_PENDING_KEY) == 1

    async def test_job_is_queued_on_the_list_of_its_kind(self, redis, monkeypatch):
        monkeypatch.setattr(redis_module, "_redis", redis)

        await redis_module.enqueue_job({"id": "a", "kind": "capture.stage"})

        assert await redis.llen(COMFY_PENDING_KEY) == 0
        assert await redis.llen("ceq:jobs:pending:capture.stage") == 1

    async def test_unknown_kind_is_not_queued_anywhere(self, redis, monkeypatch):
        monkeypatch.setattr(redis_module, "_redis", redis)

        with pytest.raises(ValueError):
            await redis_module.enqueue_job({"id": "a", "kind": "nope"})

        assert await redis.keys("*") == []


class TestCancelRemovesFromTheRightList:
    async def test_cancel_removes_a_non_comfy_job_from_its_own_list(self, redis):
        job_id = uuid4()
        other = json.dumps({"id": str(uuid4()), "kind": "export"})
        await redis.lpush(
            "ceq:jobs:pending:export",
            json.dumps({"id": str(job_id), "kind": "export", "input": {}}),
            other,
        )

        removed = await _remove_pending_job(redis, job_id, "export")

        assert removed == 1
        assert await redis.lrange("ceq:jobs:pending:export", 0, -1) == [other]

    async def test_cancel_of_a_comfy_job_leaves_other_lists_alone(self, redis):
        job_id = uuid4()
        same_id_elsewhere = json.dumps({"id": str(job_id)})
        await redis.lpush(COMFY_PENDING_KEY, json.dumps({"id": str(job_id)}))
        await redis.lpush("ceq:jobs:pending:edit", same_id_elsewhere)

        removed = await _remove_pending_job(redis, job_id)

        assert removed == 1
        assert await redis.llen(COMFY_PENDING_KEY) == 0
        assert await redis.llen("ceq:jobs:pending:edit") == 1


class TestJobModel:
    def test_kind_outside_the_set_is_rejected_before_the_database(self):
        with pytest.raises(ValueError, match="Unknown job kind"):
            Job(kind="render.gpu", user_id=uuid4())

    def test_non_comfy_job_needs_no_workflow(self):
        job = Job(kind=JobKind.EXPORT.value, user_id=uuid4())
        assert job.workflow_id is None
        assert job.kind == "export"

    def test_table_keeps_the_workflow_guarantee_for_comfy(self):
        names = {c.name for c in Job.__table__.constraints}
        assert {"ck_jobs_kind", "ck_jobs_comfy_has_workflow"} <= names
        assert Job.__table__.c.workflow_id.nullable is True
        assert Job.__table__.c.kind.server_default.arg == "comfy"

    def test_status_response_carries_kind_and_a_null_workflow(self):
        response = JobStatusResponse(
            id=uuid4(),
            kind="capture.page",
            status="queued",
            input_params={},
            queued_at=datetime.now(UTC),
            brand_message="queued",
        )
        dumped = response.model_dump()
        assert dumped["kind"] == "capture.page"
        assert dumped["workflow_id"] is None


class FakeOp:
    """Records what a migration asks Alembic to do."""

    def __init__(self):
        self.calls: list[tuple] = []

    def f(self, name):
        return name

    def __getattr__(self, name):
        def record(*args, **kwargs):
            self.calls.append((name, args, kwargs))

        return record


class TestMigration:
    def _migration(self):
        return importlib.import_module("ceq_api.alembic.versions.20261118_add_job_kind")

    def test_frozen_kind_list_matches_the_code_today(self):
        """The migration freezes its own list; this fails when a kind is added
        to the code without a new migration that widens ``ck_jobs_kind``."""
        assert tuple(self._migration().JOB_KINDS) == job_kinds.JOB_KINDS

    def test_upgrade_is_safe_for_rows_and_writers_that_predate_kinds(self, monkeypatch):
        migration = self._migration()
        fake = FakeOp()
        monkeypatch.setattr(migration, "op", fake)

        migration.upgrade()

        assert fake.calls[0][0] == "execute"
        assert "lock_timeout" in fake.calls[0][1][0]
        by_name = {name: (args, kwargs) for name, args, kwargs in fake.calls}
        column = by_name["add_column"][0][1]
        assert column.name == "kind"
        assert column.nullable is False
        assert column.server_default.arg == "comfy"
        assert by_name["alter_column"][1]["nullable"] is True
        checks = [args for name, args, _ in fake.calls if name == "create_check_constraint"]
        assert {c[0] for c in checks} == {"ck_jobs_kind", "ck_jobs_comfy_has_workflow"}
        kind_check = next(c[2] for c in checks if c[0] == "ck_jobs_kind")
        for kind in job_kinds.JOB_KINDS:
            assert f"'{kind}'" in kind_check

    def test_downgrade_undoes_the_upgrade_in_reverse(self, monkeypatch):
        migration = self._migration()
        fake = FakeOp()
        monkeypatch.setattr(migration, "op", fake)

        migration.downgrade()

        assert [name for name, _, _ in fake.calls] == [
            "drop_constraint",
            "drop_constraint",
            "alter_column",
            "drop_column",
        ]
        assert fake.calls[2][2]["nullable"] is False

    def test_migration_is_the_single_head(self):
        from alembic.config import Config
        from alembic.script import ScriptDirectory

        config = Config()
        config.set_main_option("script_location", "ceq_api:alembic")
        assert "20261118_job_kind" in {r.revision for r in ScriptDirectory.from_config(config).walk_revisions()}
