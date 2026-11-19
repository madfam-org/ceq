"""A worker without storage credentials reads the inputs of its job, and only those."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import fakeredis.aioredis as fakeredis
import pytest

from ceq_api import worker_lease
from ceq_api.auth.janua import JanuaUser, get_worker_principal, service_principal_id
from ceq_api.config import get_settings
from ceq_api.job_kinds import pending_key_for_kind
from ceq_api.models.job import Job
from ceq_api.models.output import Output
from ceq_api.models.production import Production

BUCKET = f"r2://{get_settings().r2_bucket}"
WORKER = "cpu-1"


@pytest.fixture
async def redis():
    client = fakeredis.FakeRedis(decode_responses=True)
    yield client
    await client.aclose()


@pytest.fixture
def worker_app(app, redis, mock_storage, monkeypatch):
    from ceq_api.routers import worker as worker_router

    async def principal():
        return JanuaUser(
            id=service_principal_id("ceq-cpu-worker"),
            email="ceq-cpu-worker@service.auth.madfam.io",
            client_id="ceq-cpu-worker",
            scopes=frozenset({"ceq:worker"}),
            is_service_principal=True,
        )

    mock_storage.is_configured = True
    mock_storage.generate_download_url = AsyncMock(return_value="https://r2.example/signed")
    monkeypatch.setattr(worker_router, "get_redis", lambda: redis)
    monkeypatch.setattr(worker_router, "get_storage", AsyncMock(return_value=mock_storage))
    app.dependency_overrides[get_worker_principal] = principal
    return app


async def add_job(db, production_id, step, deps=(), status="queued", kind="export"):
    job = Job(
        id=uuid4(),
        kind=kind,
        user_id=uuid4(),
        production_id=production_id,
        step=step,
        depends_on=list(deps),
        status=status,
        input_params={},
        queued_at=datetime.now(UTC),
    )
    db.add(job)
    await db.flush()
    return job


async def add_output(db, job, uri):
    db.add(
        Output(
            job_id=job.id,
            user_id=job.user_id,
            filename="take.mp4",
            storage_uri=uri,
            file_type="video/mp4",
            file_size_bytes=1,
            published_to=[],
        )
    )
    await db.flush()


async def lease(redis, job):
    await redis.lpush(pending_key_for_kind(job.kind), json.dumps({"id": str(job.id)}))
    await worker_lease.claim_next_job(
        redis, worker_id=WORKER, client_id="ceq-cpu-worker", ttl_seconds=60, capabilities=[job.kind]
    )


@pytest.fixture
async def production(db_session):
    row = Production(id=uuid4(), name="p", user_id=uuid4(), client_id="c", spec={})
    db_session.add(row)
    await db_session.flush()
    return row


async def ask(client, job, uri):
    return await client.post(
        f"/v1/worker/jobs/{job.id}/download-url", json={"worker_id": WORKER, "storage_uri": uri}
    )


async def test_a_job_reads_an_output_of_a_step_it_depends_on(
    worker_app, async_client, db_session, redis, production, mock_storage
):
    take = await add_job(
        db_session, production.id, "take", status="completed", kind="capture.stage"
    )
    uri = f"{BUCKET}/outputs/{take.id}/take.mp4"
    await add_output(db_session, take, uri)
    export = await add_job(db_session, production.id, "wide", deps=["take"])
    await lease(redis, export)

    response = await ask(async_client, export, uri)

    assert response.status_code == 200
    assert response.json()["download_url"] == "https://r2.example/signed"
    mock_storage.generate_download_url.assert_awaited_once()


async def test_it_cannot_read_a_step_it_does_not_depend_on(
    worker_app, async_client, db_session, redis, production
):
    other = await add_job(db_session, production.id, "other", status="completed")
    uri = f"{BUCKET}/outputs/{other.id}/take.mp4"
    await add_output(db_session, other, uri)
    await add_job(db_session, production.id, "take", status="completed")
    export = await add_job(db_session, production.id, "wide", deps=["take"])
    await lease(redis, export)

    assert (await ask(async_client, export, uri)).status_code == 404


async def test_it_cannot_read_another_production(
    worker_app, async_client, db_session, redis, production
):
    elsewhere = Production(id=uuid4(), name="q", user_id=uuid4(), client_id="c", spec={})
    db_session.add(elsewhere)
    await db_session.flush()
    foreign = await add_job(db_session, elsewhere.id, "take", status="completed")
    uri = f"{BUCKET}/outputs/{foreign.id}/take.mp4"
    await add_output(db_session, foreign, uri)
    await add_job(db_session, production.id, "take", status="completed")
    export = await add_job(db_session, production.id, "wide", deps=["take"])
    await lease(redis, export)

    assert (await ask(async_client, export, uri)).status_code == 404


@pytest.mark.parametrize(
    "uri",
    [
        "file:///etc/passwd",
        "r2://another-bucket/outputs/x/take.mp4",
        "{bucket}/outputs/{job}/../../secret",
    ],
)
async def test_a_reported_uri_outside_the_job_prefix_is_never_signed(
    worker_app, async_client, db_session, redis, production, mock_storage, uri
):
    take = await add_job(db_session, production.id, "take", status="completed")
    uri = uri.format(bucket=BUCKET, job=take.id)
    await add_output(db_session, take, uri)
    export = await add_job(db_session, production.id, "wide", deps=["take"])
    await lease(redis, export)

    assert (await ask(async_client, export, uri)).status_code == 404
    mock_storage.generate_download_url.assert_not_awaited()


async def test_an_unfinished_step_has_nothing_to_read(
    worker_app, async_client, db_session, redis, production
):
    take = await add_job(db_session, production.id, "take", status="running")
    uri = f"{BUCKET}/outputs/{take.id}/take.mp4"
    await add_output(db_session, take, uri)
    export = await add_job(db_session, production.id, "wide", deps=["take"])
    await lease(redis, export)

    assert (await ask(async_client, export, uri)).status_code == 404


async def test_a_job_outside_a_production_has_no_inputs(
    worker_app, async_client, db_session, redis
):
    lone = Job(
        id=uuid4(),
        kind="export",
        user_id=uuid4(),
        status="queued",
        input_params={},
        queued_at=datetime.now(UTC),
    )
    db_session.add(lone)
    await db_session.flush()
    await lease(redis, lone)

    assert (await ask(async_client, lone, f"{BUCKET}/outputs/{lone.id}/x.mp4")).status_code == 404


async def test_without_the_lease_it_is_refused(worker_app, async_client, db_session, production):
    take = await add_job(db_session, production.id, "take", status="completed")
    export = await add_job(db_session, production.id, "wide", deps=["take"])

    response = await ask(async_client, export, f"{BUCKET}/outputs/{take.id}/take.mp4")

    assert response.status_code in (404, 409)
