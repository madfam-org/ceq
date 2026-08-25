"""Tests for the HTTPS worker job-lease API (``/v1/worker/*``).

Covers:
- The lease store itself against a REAL Redis (fakeredis with Lua), so the
  atomic claim/heartbeat/release/requeue/reap scripts actually execute rather
  than being asserted against a mock's call log.
- Interop: a lease claim and a legacy Redis worker's ``BRPOPLPUSH`` contend on
  the same list and can never both get the same job.
- Crash recovery: an unheartbeated lease returns to pending; past the attempt
  budget it dead-letters instead of cycling.
- The scope matrix: a ``ceq:render`` token is 403 on ``/v1/worker/*``, a human
  token is 403, and only ``ceq:worker`` gets through.
- The endpoint lifecycle end to end through the ASGI app.
"""

from __future__ import annotations

import json
import time
from datetime import UTC, datetime
from uuid import UUID, uuid4

import fakeredis.aioredis as fakeredis
import pytest
from fastapi import HTTPException

from ceq_api import worker_lease
from ceq_api.auth.janua import JanuaUser, get_worker_principal, service_principal_id
from ceq_api.config import get_settings
from ceq_api.worker_lease import (
    LEASE_DEAD_LETTER_KEY,
    LEASE_INDEX_KEY,
    PENDING_KEY,
    PROCESSING_KEY,
    LeaseOutcome,
)

settings = get_settings()

WORKER_SCOPE = "ceq:worker"
RENDER_SCOPE = "ceq:render"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def redis():
    """A real Redis implementation with Lua support.

    The lease claim is a Lua script; a mock would let a broken script pass.
    """
    client = fakeredis.FakeRedis(decode_responses=True)
    yield client
    await client.aclose()


def job_payload(job_id: str) -> str:
    """A job envelope in the exact shape ``workflows.run_workflow`` enqueues."""
    return json.dumps(
        {
            "id": job_id,
            "workflow_id": str(uuid4()),
            "input": {"workflow_json": {"3": {}}, "params": {}, "job_id": job_id},
        }
    )


@pytest.fixture
def worker_principal() -> JanuaUser:
    """A machine principal holding the worker scope."""
    return JanuaUser(
        id=service_principal_id("ceq-gpu-worker"),
        email="ceq-gpu-worker@service.auth.madfam.io",
        client_id="ceq-gpu-worker",
        scopes=frozenset({WORKER_SCOPE}),
        is_service_principal=True,
    )


# ---------------------------------------------------------------------------
# Lease store — atomicity and lifecycle
# ---------------------------------------------------------------------------


class TestLeaseStore:
    """The Redis primitives underpinning the API."""

    async def test_claim_moves_pending_to_processing_and_opens_lease(self, redis):
        job_id = str(uuid4())
        await redis.lpush(PENDING_KEY, job_payload(job_id))

        leased = await worker_lease.claim_next_job(
            redis, worker_id="w1", client_id="c1", ttl_seconds=60
        )

        assert leased is not None
        assert leased.job_id == job_id
        assert leased.attempts == 1
        assert leased.payload["input"]["job_id"] == job_id

        # Same structures the Redis worker uses.
        assert await redis.llen(PENDING_KEY) == 0
        assert await redis.llen(PROCESSING_KEY) == 1

        lease = await worker_lease.get_lease(redis, job_id)
        assert lease is not None
        assert lease["worker_id"] == "w1"
        assert lease["client_id"] == "c1"
        assert await redis.zscore(LEASE_INDEX_KEY, job_id) == pytest.approx(
            leased.expires_at, abs=1
        )

    async def test_claim_on_empty_queue_returns_none(self, redis):
        assert (
            await worker_lease.claim_next_job(
                redis, worker_id="w1", client_id="c1", ttl_seconds=60
            )
            is None
        )

    async def test_concurrent_leasers_never_get_the_same_job(self, redis):
        """The core race: two HTTPS workers claiming at once."""
        job_id = str(uuid4())
        await redis.lpush(PENDING_KEY, job_payload(job_id))

        first = await worker_lease.claim_next_job(
            redis, worker_id="w1", client_id="c1", ttl_seconds=60
        )
        second = await worker_lease.claim_next_job(
            redis, worker_id="w2", client_id="c1", ttl_seconds=60
        )

        assert first is not None
        assert second is None
        assert (await worker_lease.get_lease(redis, job_id))["worker_id"] == "w1"

    async def test_interop_redis_worker_and_leaser_do_not_double_process(self, redis):
        """A legacy in-cluster worker and an HTTPS leaser share one queue.

        Two jobs, one claimed each way: neither claimant can see the other's
        job, because both pop the tail of the same list.
        """
        job_a, job_b = str(uuid4()), str(uuid4())
        # LPUSH order means job_a is at the tail and pops first.
        await redis.lpush(PENDING_KEY, job_payload(job_a))
        await redis.lpush(PENDING_KEY, job_payload(job_b))

        # Legacy worker: exactly what queue.QueueConsumer.run does.
        redis_claim = await redis.brpoplpush(PENDING_KEY, PROCESSING_KEY, timeout=1)
        assert json.loads(redis_claim)["id"] == job_a

        # HTTPS worker leases next; it must NOT get job_a.
        leased = await worker_lease.claim_next_job(
            redis, worker_id="https-1", client_id="c1", ttl_seconds=60
        )
        assert leased is not None
        assert leased.job_id == job_b

        # No lease was opened over the Redis worker's job.
        assert await worker_lease.get_lease(redis, job_a) is None
        assert await redis.llen(PENDING_KEY) == 0

    async def test_heartbeat_extends_lease_for_owner_only(self, redis):
        job_id = str(uuid4())
        await redis.lpush(PENDING_KEY, job_payload(job_id))
        leased = await worker_lease.claim_next_job(
            redis, worker_id="w1", client_id="c1", ttl_seconds=30
        )
        assert leased is not None

        outcome, new_expiry = await worker_lease.heartbeat_lease(
            redis, job_id=job_id, worker_id="w1", ttl_seconds=120, max_seconds=3600
        )
        assert outcome == LeaseOutcome.OK
        assert new_expiry is not None
        assert new_expiry > leased.expires_at

        # A different worker cannot extend someone else's lease.
        stolen, _ = await worker_lease.heartbeat_lease(
            redis, job_id=job_id, worker_id="w2", ttl_seconds=120, max_seconds=3600
        )
        assert stolen == LeaseOutcome.NOT_OWNER

    async def test_heartbeat_refuses_past_max_lease_duration(self, redis):
        """A wedged-but-heartbeating worker cannot hold a job forever."""
        job_id = str(uuid4())
        await redis.lpush(PENDING_KEY, job_payload(job_id))
        await worker_lease.claim_next_job(
            redis, worker_id="w1", client_id="c1", ttl_seconds=30
        )
        # Backdate the lease start well past the ceiling.
        await redis.hset(
            worker_lease.lease_key(job_id), "leased_at", str(time.time() - 5000)
        )

        outcome, expiry = await worker_lease.heartbeat_lease(
            redis, job_id=job_id, worker_id="w1", ttl_seconds=60, max_seconds=600
        )
        assert outcome == LeaseOutcome.MISSING
        assert expiry is None

    async def test_heartbeat_on_missing_lease_reports_missing(self, redis):
        outcome, _ = await worker_lease.heartbeat_lease(
            redis,
            job_id=str(uuid4()),
            worker_id="w1",
            ttl_seconds=60,
            max_seconds=600,
        )
        assert outcome == LeaseOutcome.MISSING

    async def test_release_clears_processing_and_lease(self, redis):
        job_id = str(uuid4())
        await redis.lpush(PENDING_KEY, job_payload(job_id))
        await worker_lease.claim_next_job(
            redis, worker_id="w1", client_id="c1", ttl_seconds=60
        )

        assert (
            await worker_lease.release_lease(redis, job_id=job_id, worker_id="w1")
            == LeaseOutcome.OK
        )
        assert await redis.llen(PROCESSING_KEY) == 0
        assert await redis.llen(PENDING_KEY) == 0
        assert await worker_lease.get_lease(redis, job_id) is None
        assert await redis.zscore(LEASE_INDEX_KEY, job_id) is None

    async def test_release_by_non_owner_is_rejected(self, redis):
        job_id = str(uuid4())
        await redis.lpush(PENDING_KEY, job_payload(job_id))
        await worker_lease.claim_next_job(
            redis, worker_id="w1", client_id="c1", ttl_seconds=60
        )

        assert (
            await worker_lease.release_lease(redis, job_id=job_id, worker_id="w2")
            == LeaseOutcome.NOT_OWNER
        )
        # The real owner's lease survives intact.
        assert await redis.llen(PROCESSING_KEY) == 1

    async def test_requeue_returns_job_and_preserves_attempts(self, redis):
        job_id = str(uuid4())
        await redis.lpush(PENDING_KEY, job_payload(job_id))
        await worker_lease.claim_next_job(
            redis, worker_id="w1", client_id="c1", ttl_seconds=60
        )

        assert (
            await worker_lease.requeue_lease(
                redis, job_id=job_id, worker_id="w1", attempts=1
            )
            == LeaseOutcome.OK
        )
        assert await redis.llen(PENDING_KEY) == 1
        assert await redis.llen(PROCESSING_KEY) == 0

        # Second claim sees attempt 2 — the retry budget survived the requeue.
        again = await worker_lease.claim_next_job(
            redis, worker_id="w2", client_id="c1", ttl_seconds=60
        )
        assert again is not None
        assert again.attempts == 2

    async def test_requeue_stub_expires_so_orphans_cannot_leak(self, redis):
        """A requeued job drained by a Redis-mode worker must not leak a key.

        The attempts stub is only consumed by a later lease claim. If a legacy
        in-cluster worker takes the payload instead, nothing ever reads it — and
        DB14 is a SHARED keyspace, so an unexpiring orphan per requeue is a leak.
        """
        job_id = str(uuid4())
        await redis.lpush(PENDING_KEY, job_payload(job_id))
        await worker_lease.claim_next_job(
            redis, worker_id="w1", client_id="c1", ttl_seconds=60
        )
        await worker_lease.requeue_lease(
            redis, job_id=job_id, worker_id="w1", attempts=1
        )

        ttl = await redis.ttl(worker_lease.lease_key(job_id))
        assert 0 < ttl <= worker_lease.ATTEMPTS_STUB_TTL_SECONDS

    async def test_reclaim_clears_stub_ttl(self, redis):
        """A live lease must never expire by key TTL out from under a worker."""
        job_id = str(uuid4())
        await redis.lpush(PENDING_KEY, job_payload(job_id))
        await worker_lease.claim_next_job(
            redis, worker_id="w1", client_id="c1", ttl_seconds=60
        )
        await worker_lease.requeue_lease(
            redis, job_id=job_id, worker_id="w1", attempts=1
        )
        await worker_lease.claim_next_job(
            redis, worker_id="w2", client_id="c1", ttl_seconds=60
        )

        # -1 == key exists with no expiry.
        assert await redis.ttl(worker_lease.lease_key(job_id)) == -1

    async def test_dead_letter_archives_without_requeue(self, redis):
        job_id = str(uuid4())
        await redis.lpush(PENDING_KEY, job_payload(job_id))
        await worker_lease.claim_next_job(
            redis, worker_id="w1", client_id="c1", ttl_seconds=60
        )

        assert (
            await worker_lease.dead_letter_lease(
                redis, job_id=job_id, worker_id="w1", reason="bad workflow"
            )
            == LeaseOutcome.OK
        )
        assert await redis.llen(PENDING_KEY) == 0
        assert await redis.llen(PROCESSING_KEY) == 0

        archived = json.loads(await redis.lindex(LEASE_DEAD_LETTER_KEY, 0))
        assert archived["job_id"] == job_id
        assert archived["reason"] == "bad workflow"


class TestCrashRecovery:
    """A worker that dies simply stops heartbeating; the reaper does the rest."""

    async def test_expired_lease_returns_job_to_pending(self, redis):
        job_id = str(uuid4())
        await redis.lpush(PENDING_KEY, job_payload(job_id))
        await worker_lease.claim_next_job(
            redis, worker_id="doomed", client_id="c1", ttl_seconds=1
        )

        # Nothing was reaped while the lease is live.
        assert await worker_lease.reap_expired(redis, max_attempts=3, now=time.time()) == []

        # Simulate the worker vanishing: advance past the visibility timeout.
        future = time.time() + 120
        actions = await worker_lease.reap_expired(redis, max_attempts=3, now=future)

        assert actions == [(job_id, "requeued")]
        assert await redis.llen(PENDING_KEY) == 1
        assert await redis.llen(PROCESSING_KEY) == 0
        assert await worker_lease.get_lease(redis, job_id) is None

        # And the recovered job is claimable again, by anyone.
        reclaimed = await worker_lease.claim_next_job(
            redis, worker_id="w2", client_id="c1", ttl_seconds=60
        )
        assert reclaimed is not None
        assert reclaimed.job_id == job_id
        assert reclaimed.attempts == 2

    async def test_reaper_dead_letters_past_attempt_budget(self, redis):
        job_id = str(uuid4())
        await redis.lpush(PENDING_KEY, job_payload(job_id))
        await worker_lease.claim_next_job(
            redis, worker_id="w1", client_id="c1", ttl_seconds=1
        )
        # Pretend this delivery already burned the budget.
        await redis.hset(worker_lease.lease_key(job_id), "attempts", "3")

        actions = await worker_lease.reap_expired(
            redis, max_attempts=3, now=time.time() + 120
        )

        assert actions == [(job_id, "dead_lettered")]
        assert await redis.llen(PENDING_KEY) == 0
        assert await redis.llen(LEASE_DEAD_LETTER_KEY) == 1

    async def test_stale_index_entry_is_cleaned_not_crashed(self, redis):
        """A lease completed between index scan and read must not break reaping."""
        await redis.zadd(LEASE_INDEX_KEY, {"ghost-job": time.time() - 10})

        assert await worker_lease.reap_expired(redis, max_attempts=3) == []
        assert await redis.zscore(LEASE_INDEX_KEY, "ghost-job") is None


# ---------------------------------------------------------------------------
# Scope matrix
# ---------------------------------------------------------------------------


class TestWorkerScopeGate:
    """``ceq:worker`` and ``ceq:render`` are separate capabilities."""

    async def _call(self, principal: JanuaUser | None):
        from unittest.mock import AsyncMock, MagicMock, patch

        request = MagicMock()
        request.state = MagicMock()
        credentials = MagicMock()
        credentials.credentials = "token"

        with patch(
            "ceq_api.auth.janua.validate_token",
            AsyncMock(return_value=principal),
        ):
            return await get_worker_principal(request, credentials)

    async def test_worker_scope_is_accepted(self, worker_principal):
        result = await self._call(worker_principal)
        assert result.client_id == "ceq-gpu-worker"

    async def test_render_scope_token_is_403(self):
        """A batch driver's submit credential must NOT be able to lease jobs."""
        render_principal = JanuaUser(
            id=service_principal_id("ceq-batch-driver"),
            email="ceq-batch-driver@service.auth.madfam.io",
            client_id="ceq-batch-driver",
            scopes=frozenset({RENDER_SCOPE}),
            is_service_principal=True,
        )

        with pytest.raises(HTTPException) as exc:
            await self._call(render_principal)

        assert exc.value.status_code == 403
        assert "ceq:worker" in exc.value.detail

    async def test_human_token_is_403_even_for_admin(self):
        """Leasing is a machine capability; a browser session is never right."""
        human = JanuaUser(id=uuid4(), email="admin@madfam.io", roles=["admin"])

        with pytest.raises(HTTPException) as exc:
            await self._call(human)

        assert exc.value.status_code == 403
        assert "machine credentials" in exc.value.detail

    async def test_invalid_token_is_401(self):
        with pytest.raises(HTTPException) as exc:
            await self._call(None)
        assert exc.value.status_code == 401

    async def test_missing_credentials_is_401(self):
        from unittest.mock import MagicMock

        request = MagicMock()
        request.state = MagicMock()

        with pytest.raises(HTTPException) as exc:
            await get_worker_principal(request, None)
        assert exc.value.status_code == 401

    async def test_no_dev_mode_bypass(self, monkeypatch):
        """Fails CLOSED when auth is disabled, unlike the human dependencies.

        `get_current_user` hands out a mock user when `janua_enabled` is False.
        This surface must not: it is public by design and leases carry every
        tenant's job payloads, so an auth-disabled deployment must reject rather
        than hand jobs to anonymous callers.
        """
        from unittest.mock import MagicMock

        import ceq_api.auth.janua as janua_module

        monkeypatch.setattr(janua_module.settings, "janua_enabled", False)
        request = MagicMock()
        request.state = MagicMock()

        with pytest.raises(HTTPException) as exc:
            await get_worker_principal(request, None)
        assert exc.value.status_code == 401

    async def test_disabled_lease_api_returns_503(self, monkeypatch):
        """WORKER_LEASE_ENABLED=false is a hard off switch for the surface."""
        from unittest.mock import MagicMock

        import ceq_api.auth.janua as janua_module

        monkeypatch.setattr(janua_module.settings, "worker_lease_enabled", False)
        request = MagicMock()
        request.state = MagicMock()

        with pytest.raises(HTTPException) as exc:
            await get_worker_principal(request, None)
        assert exc.value.status_code == 503

    async def test_scopes_are_independent(self, worker_principal):
        """Holding ceq:worker does not imply ceq:render, and vice versa."""
        assert worker_principal.has_scope(WORKER_SCOPE)
        assert not worker_principal.has_scope(RENDER_SCOPE)


# ---------------------------------------------------------------------------
# HTTP lifecycle through the app
# ---------------------------------------------------------------------------


@pytest.fixture
def lease_app(app, redis, worker_principal, monkeypatch):
    """The test app with a real (fake) Redis and an authenticated worker.

    The router calls ``get_redis()`` directly (same idiom as ``routers.jobs``)
    rather than through ``Depends``, so a dependency override would not reach
    it — the module reference is what has to be patched.
    """
    from ceq_api.db.redis import get_redis
    from ceq_api.routers import worker as worker_router

    async def override_principal():
        return worker_principal

    monkeypatch.setattr(worker_router, "get_redis", lambda: redis)
    app.dependency_overrides[get_redis] = lambda: redis
    app.dependency_overrides[get_worker_principal] = override_principal
    yield app


@pytest.fixture
async def queued_job(db_session, redis):
    """A real Job row plus its payload on the pending queue."""
    from ceq_api.models.job import Job
    from ceq_api.models.template import Template
    from ceq_api.models.workflow import Workflow

    template = Template(
        name="Lease Test",
        description="fixture",
        category="utility",
        workflow_json={"3": {}},
        input_schema={},
        tags=[],
    )
    db_session.add(template)
    await db_session.flush()

    workflow = Workflow(
        name="Lease Test WF",
        user_id=uuid4(),
        template_id=template.id,
        workflow_json={"3": {}},
    )
    db_session.add(workflow)
    await db_session.flush()

    job = Job(
        workflow_id=workflow.id,
        user_id=uuid4(),
        status="queued",
        input_params={},
        queued_at=datetime.now(UTC),
    )
    db_session.add(job)
    await db_session.flush()

    await redis.lpush(PENDING_KEY, job_payload(str(job.id)))
    return job


class TestLeaseEndpoints:
    """Full lease -> heartbeat -> complete / fail lifecycle over HTTP."""

    async def test_lease_returns_204_on_empty_queue(self, lease_app, async_client):
        response = await async_client.post(
            "/v1/worker/lease", json={"worker_id": "w1"}
        )
        assert response.status_code == 204

    async def test_full_success_lifecycle(
        self, lease_app, async_client, queued_job, redis, db_session
    ):
        from sqlalchemy import select

        from ceq_api.models.job import Job

        # 1. Lease
        leased = await async_client.post(
            "/v1/worker/lease", json={"worker_id": "gpu-1", "ttl_seconds": 120}
        )
        assert leased.status_code == 200
        body = leased.json()
        assert UUID(body["job_id"]) == queued_job.id
        assert body["attempt"] == 1
        assert body["heartbeat_interval_seconds"] > 0

        # 2. Heartbeat
        beat = await async_client.post(
            f"/v1/worker/jobs/{queued_job.id}/heartbeat",
            json={"worker_id": "gpu-1", "progress": 0.5, "current_node": "KSampler"},
        )
        assert beat.status_code == 200
        assert beat.json()["cancel_requested"] is False

        # 3. Complete
        done = await async_client.post(
            f"/v1/worker/jobs/{queued_job.id}/complete",
            json={
                "worker_id": "gpu-1",
                "outputs": [
                    {
                        "filename": "out.png",
                        "storage_uri": "r2://ceq-assets/outputs/out.png",
                        "file_type": "image/png",
                        "file_size_bytes": 2048,
                    }
                ],
                "gpu_seconds": 12.5,
            },
        )
        assert done.status_code == 200
        assert done.json()["status"] == "completed"
        assert done.json()["outputs_persisted"] == 1

        # Durable in Postgres, and the lease + processing entry are gone.
        refreshed = (
            await db_session.execute(select(Job).where(Job.id == queued_job.id))
        ).scalar_one()
        assert refreshed.status == "completed"
        assert refreshed.gpu_seconds == 12.5
        assert await worker_lease.get_lease(redis, str(queued_job.id)) is None
        assert await redis.llen(PROCESSING_KEY) == 0

    async def test_heartbeat_by_wrong_worker_is_409(
        self, lease_app, async_client, queued_job
    ):
        await async_client.post("/v1/worker/lease", json={"worker_id": "gpu-1"})

        response = await async_client.post(
            f"/v1/worker/jobs/{queued_job.id}/heartbeat",
            json={"worker_id": "impostor"},
        )
        assert response.status_code == 409

    async def test_complete_without_lease_is_409(
        self, lease_app, async_client, queued_job
    ):
        """A worker whose lease was reaped cannot land a stale result."""
        response = await async_client.post(
            f"/v1/worker/jobs/{queued_job.id}/complete",
            json={"worker_id": "gpu-1", "outputs": []},
        )
        assert response.status_code == 409

    async def test_fail_retryable_requeues_job(
        self, lease_app, async_client, queued_job, redis, db_session
    ):
        from sqlalchemy import select

        from ceq_api.models.job import Job

        await async_client.post("/v1/worker/lease", json={"worker_id": "gpu-1"})

        response = await async_client.post(
            f"/v1/worker/jobs/{queued_job.id}/fail",
            json={"worker_id": "gpu-1", "error": "CUDA OOM", "retryable": True},
        )

        assert response.status_code == 200
        assert response.json()["requeued"] is True
        assert response.json()["dead_lettered"] is False
        assert await redis.llen(PENDING_KEY) == 1

        # A retry is not a user-visible failure — the job row is untouched.
        refreshed = (
            await db_session.execute(select(Job).where(Job.id == queued_job.id))
        ).scalar_one()
        assert refreshed.status == "queued"

    async def test_fail_non_retryable_retires_job(
        self, lease_app, async_client, queued_job, redis, db_session
    ):
        from sqlalchemy import select

        from ceq_api.models.job import Job

        await async_client.post("/v1/worker/lease", json={"worker_id": "gpu-1"})

        response = await async_client.post(
            f"/v1/worker/jobs/{queued_job.id}/fail",
            json={
                "worker_id": "gpu-1",
                "error": "workflow references a missing model",
                "retryable": False,
            },
        )

        assert response.status_code == 200
        assert response.json()["dead_lettered"] is True
        assert await redis.llen(PENDING_KEY) == 0
        assert await redis.llen(LEASE_DEAD_LETTER_KEY) == 1

        refreshed = (
            await db_session.execute(select(Job).where(Job.id == queued_job.id))
        ).scalar_one()
        assert refreshed.status == "failed"
        assert refreshed.error == "workflow references a missing model"

    async def test_fail_retires_after_attempt_budget(
        self, lease_app, async_client, queued_job, redis, db_session
    ):
        """Retryable failures still stop once attempts are exhausted."""
        from sqlalchemy import select

        from ceq_api.models.job import Job

        await async_client.post("/v1/worker/lease", json={"worker_id": "gpu-1"})
        # Pretend previous deliveries burned the budget.
        await redis.hset(
            worker_lease.lease_key(str(queued_job.id)),
            "attempts",
            str(settings.worker_lease_max_attempts),
        )

        response = await async_client.post(
            f"/v1/worker/jobs/{queued_job.id}/fail",
            json={"worker_id": "gpu-1", "error": "CUDA OOM", "retryable": True},
        )

        assert response.json()["requeued"] is False
        assert response.json()["dead_lettered"] is True

        refreshed = (
            await db_session.execute(select(Job).where(Job.id == queued_job.id))
        ).scalar_one()
        assert refreshed.status == "failed"

    async def test_cancel_surfaces_on_heartbeat(
        self, lease_app, async_client, queued_job, redis
    ):
        """A user cancel reaches an external worker via its next heartbeat."""
        await async_client.post("/v1/worker/lease", json={"worker_id": "gpu-1"})

        # What jobs.cancel_job writes.
        await redis.hset(
            f"ceq:job:{queued_job.id}",
            mapping={"status": "cancelled", "cancel_requested": "true"},
        )

        beat = await async_client.post(
            f"/v1/worker/jobs/{queued_job.id}/heartbeat",
            json={"worker_id": "gpu-1"},
        )
        assert beat.status_code == 200
        assert beat.json()["cancel_requested"] is True

    async def test_lease_reaps_before_claiming(
        self, lease_app, async_client, queued_job, redis
    ):
        """A crashed worker's job is recovered by the next worker asking for work."""
        first = await async_client.post(
            "/v1/worker/lease", json={"worker_id": "doomed", "ttl_seconds": 10}
        )
        assert first.status_code == 200

        # Queue is empty for a second worker while the lease is live.
        assert (
            await async_client.post("/v1/worker/lease", json={"worker_id": "gpu-2"})
        ).status_code == 204

        # Expire the lease as if "doomed" was preempted mid-job.
        await redis.hset(
            worker_lease.lease_key(str(queued_job.id)),
            "expires_at",
            str(time.time() - 1),
        )
        await redis.zadd(LEASE_INDEX_KEY, {str(queued_job.id): time.time() - 1})

        recovered = await async_client.post(
            "/v1/worker/lease", json={"worker_id": "gpu-2"}
        )
        assert recovered.status_code == 200
        assert UUID(recovered.json()["job_id"]) == queued_job.id
        assert recovered.json()["attempt"] == 2
