"""Tests for productions (RFC 0061): the submit route, its scope gate, the
graph rules, and how a production moves on as its jobs finish.
"""

from __future__ import annotations

import importlib
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import select

import ceq_api.auth.janua as janua_module
from ceq_api import productions as productions_module
from ceq_api.auth.janua import JanuaUser, get_production_principal, service_principal_id
from ceq_api.models.job import Job, JobStatus
from ceq_api.models.output import Output
from ceq_api.productions import (
    GraphError,
    cancel_dependents,
    check_capture_url,
    host_allowed,
    on_job_finished,
    production_status,
    release_ready_jobs,
    validate_graph,
)
from ceq_api.routers import productions as productions_router
from ceq_api.routers.jobs import JobCompletionReport, JobOutputReport, persist_job_completion

PRODUCE_SCOPE = "ceq:produce"
CLIENT = "cinematic-pointer"
HOSTS = ["enclii.dev", ".madfam.io"]


def principal(client_id: str = CLIENT, scopes: frozenset[str] = frozenset({PRODUCE_SCOPE})):
    return JanuaUser(
        id=service_principal_id(client_id),
        email=f"{client_id}@service.auth.madfam.io",
        client_id=client_id,
        scopes=scopes,
        is_service_principal=True,
    )


def step(name, kind="edit", deps=(), **params):
    return {"step": name, "kind": kind, "params": params, "depends_on": list(deps)}


def capture(name, url="https://enclii.dev/", deps=()):
    return step(name, "capture.stage", deps, url=url)


# ---------------------------------------------------------------------------
# Who may submit
# ---------------------------------------------------------------------------


class TestProductionScopeGate:
    async def _call(self, who, monkeypatch, named=(CLIENT,)):
        monkeypatch.setattr(janua_module.settings, "production_submit_client_ids", list(named))
        request = MagicMock()
        request.state = MagicMock()
        credentials = MagicMock()
        credentials.credentials = "token"
        with patch("ceq_api.auth.janua.validate_token", AsyncMock(return_value=who)):
            return await get_production_principal(request, credentials)

    async def test_named_client_with_the_scope_is_accepted(self, monkeypatch):
        result = await self._call(principal(), monkeypatch)
        assert result.client_id == CLIENT

    @pytest.mark.parametrize("scope", ["ceq:render", "ceq:worker"])
    async def test_other_ceq_scopes_do_not_imply_it(self, scope, monkeypatch):
        with pytest.raises(HTTPException) as exc:
            await self._call(principal(scopes=frozenset({scope})), monkeypatch)
        assert exc.value.status_code == 403
        assert PRODUCE_SCOPE in exc.value.detail

    async def test_scope_without_being_named_is_403(self, monkeypatch):
        with pytest.raises(HTTPException) as exc:
            await self._call(principal("someone-else"), monkeypatch)
        assert exc.value.status_code == 403
        assert "not named" in exc.value.detail

    async def test_default_names_nobody(self, monkeypatch):
        with pytest.raises(HTTPException) as exc:
            await self._call(principal(), monkeypatch, named=())
        assert exc.value.status_code == 403

    async def test_human_is_403_even_for_admin(self, monkeypatch):
        human = JanuaUser(id=uuid4(), email="admin@madfam.io", roles=["admin"])
        with pytest.raises(HTTPException) as exc:
            await self._call(human, monkeypatch)
        assert exc.value.status_code == 403

    async def test_invalid_token_is_401(self, monkeypatch):
        with pytest.raises(HTTPException) as exc:
            await self._call(None, monkeypatch)
        assert exc.value.status_code == 401

    async def test_no_dev_mode_bypass(self, monkeypatch):
        monkeypatch.setattr(janua_module.settings, "janua_enabled", False)
        request = MagicMock()
        request.state = MagicMock()
        with pytest.raises(HTTPException) as exc:
            await get_production_principal(request, None)
        assert exc.value.status_code == 401

    async def test_off_switch_is_503(self, monkeypatch):
        monkeypatch.setattr(janua_module.settings, "production_submit_enabled", False)
        request = MagicMock()
        request.state = MagicMock()
        with pytest.raises(HTTPException) as exc:
            await get_production_principal(request, None)
        assert exc.value.status_code == 503


# ---------------------------------------------------------------------------
# Which pages may be opened
# ---------------------------------------------------------------------------


class TestCaptureHosts:
    def test_exact_and_subdomain_entries(self):
        assert host_allowed("enclii.dev", HOSTS)
        assert host_allowed("CV.madfam.io", HOSTS)
        assert host_allowed("a.b.madfam.io", HOSTS)

    def test_what_they_do_not_match(self):
        assert not host_allowed("madfam.io", HOSTS)  # dot entry is subdomains only
        assert not host_allowed("www.enclii.dev", HOSTS)  # exact entry is exact
        assert not host_allowed("evilmadfam.io", HOSTS)
        assert not host_allowed("madfam.io.evil.com", HOSTS)
        assert not host_allowed("enclii.dev", [])

    @pytest.mark.parametrize(
        "url",
        [
            "http://enclii.dev/",
            "https://example.com/",
            "https://user:pw@enclii.dev/",
            "https://enclii.dev:8443/",
            "https://enclii.dev@evil.com/",
            "https://127.0.0.1/",
            "https://[::1]/",
            "file:///etc/passwd",
            # A browser ends the host at a backslash; Python does not.
            "https://evil.example\\.cv.madfam.io/x",
            "https://169.254.169.254\\.madfam.io/",
            "https://evil.example%5c.cv.madfam.io/",
            "https://cv.madfam.io\t/",
            "https://cv.madfam.io /",
            "https://1.2.3.4.madfam.io.5/",
            "https://münchen.madfam.io/",
            "https://a_b.madfam.io/",
            "https://a:b/",
            "https://[x/",
            "https://cv.madfam.io/\x00",
            "",
            None,
        ],
    )
    def test_refused_urls(self, url):
        with pytest.raises(GraphError):
            check_capture_url(url, HOSTS)

    def test_allowed_url_comes_back_canonical(self):
        assert check_capture_url("HTTPS://Enclii.dev./pricing?x=1#top", HOSTS) == (
            "https://enclii.dev/pricing?x=1"
        )
        assert check_capture_url("https://cv.madfam.io:443", HOSTS) == "https://cv.madfam.io/"

    @pytest.mark.parametrize(
        "params",
        [
            {"source": "file:///etc/passwd"},
            {"input": "concat:a|b"},
            {"nested": {"deep": ["ok", "http://internal/"]}},
            {"audio": "s3://bucket/key"},
            {"http://key": 1},
            {"text": "a\x00b"},
        ],
    )
    def test_no_other_location_anywhere_in_params(self, params):
        for kind_step in (
            step("a", "edit", **params),
            {**capture("a"), "params": {"url": "https://enclii.dev/", **params}},
        ):
            with pytest.raises(GraphError, match="may not carry a location"):
                validate_graph([kind_step], allowed_hosts=HOSTS, max_jobs=5)

    def test_ordinary_params_pass(self):
        validate_graph(
            [step("a", "export", aspect="16:9", formats=["mp4", "webm"], crf=17, note="16:9 cut")],
            allowed_hosts=HOSTS,
            max_jobs=5,
        )


# ---------------------------------------------------------------------------
# The graph
# ---------------------------------------------------------------------------


class TestGraph:
    def _validate(self, steps, max_jobs=20):
        return validate_graph(steps, allowed_hosts=HOSTS, max_jobs=max_jobs)

    def test_order_respects_dependencies(self):
        order = self._validate(
            [step("export", "export", ["edit"]), step("edit", "edit", ["take"]), capture("take")]
        )
        assert order == ["take", "edit", "export"]

    @pytest.mark.parametrize(
        ("steps", "message"),
        [
            ([], "at least one"),
            ([step("a"), step("a")], "unique"),
            ([step("a", "comfy")], "cannot be part of a production"),
            ([step("a", "nope")], "cannot be part of a production"),
            ([step("a", deps=["a"])], "depends on itself"),
            ([step("a", deps=["ghost"])], "unknown step"),
            ([step("a", deps=["b", "b"]), step("b")], "twice"),
            ([step("a", deps=["b"]), step("b", deps=["a"])], "cycle"),
            ([capture("a", "https://example.com/")], "not one this deployment may capture"),
            ([step("a", "capture.page")], "needs params.url"),
        ],
    )
    def test_refused_graphs(self, steps, message):
        with pytest.raises(GraphError, match=message):
            self._validate(steps)

    def test_too_many_steps(self):
        with pytest.raises(GraphError, match="at most 2"):
            self._validate([step("a"), step("b"), step("c")], max_jobs=2)

    def test_status_is_read_from_the_jobs(self):
        def jobs(*statuses):
            return [Job(kind="edit", user_id=uuid4(), status=s) for s in statuses]

        assert production_status(jobs("queued", "queued")) == "queued"
        assert production_status(jobs("completed", "queued")) == "running"
        assert production_status(jobs("running", "queued")) == "running"
        assert production_status(jobs("completed", "completed")) == "completed"
        assert production_status(jobs("completed", "cancelled")) == "cancelled"
        assert production_status(jobs("failed", "cancelled")) == "failed"


# ---------------------------------------------------------------------------
# Moving a production on
# ---------------------------------------------------------------------------


@pytest.fixture
def queued(monkeypatch):
    """Payloads handed to the queue, in order."""
    sent: list[dict] = []

    async def fake_enqueue(payload):
        sent.append(payload)

    monkeypatch.setattr(productions_module, "enqueue_job", fake_enqueue)
    return sent


@pytest.fixture
def production_app(app, monkeypatch):
    async def override():
        return principal()

    app.dependency_overrides[get_production_principal] = override
    monkeypatch.setattr(productions_router.settings, "production_allowed_hosts", HOSTS)
    return app


TRAILER = {
    "name": "enclii landing",
    "steps": [
        capture("take"),
        step("edit", "edit", ["take"]),
        step("wide", "export", ["edit"], aspect="16:9"),
        step("tall", "export", ["edit"], aspect="9:16"),
    ],
}


async def submit(async_client, body=None):
    response = await async_client.post("/v1/productions/", json=body or TRAILER)
    assert response.status_code == 201, response.text
    return response.json()


async def job_for(db_session, production_id, name) -> Job:
    result = await db_session.execute(
        select(Job).where(Job.production_id == production_id, Job.step == name)
    )
    return result.scalar_one()


async def finish(db_session, job: Job, status="completed", outputs=()):
    return await persist_job_completion(
        job.id,
        JobCompletionReport(
            status=status,
            outputs=[
                JobOutputReport(
                    filename=name,
                    storage_uri=f"r2://ceq/outputs/{job.id}/{name}",
                    file_type="video",
                    file_size_bytes=1,
                )
                for name in outputs
            ],
        ),
        db_session,
    )


class TestSubmitAndRun:
    async def test_only_the_roots_are_queued_on_submit(self, production_app, async_client, queued):
        data = await submit(async_client)

        assert data["status"] == "queued"
        assert [(j["step"], j["waiting"]) for j in data["jobs"]] == [
            ("take", False),
            ("edit", True),
            ("wide", True),
            ("tall", True),
        ]
        assert [p["step"] for p in queued] == ["take"]
        assert queued[0]["kind"] == "capture.stage"
        assert queued[0]["input"]["params"] == {"url": "https://enclii.dev/"}
        assert queued[0]["input"]["inputs"] == {}

    async def test_a_finished_step_releases_the_next_with_its_outputs(
        self, production_app, async_client, queued, db_session
    ):
        data = await submit(async_client)
        take = await job_for(db_session, data["id"], "take")

        await finish(db_session, take, outputs=["take.mp4"])

        assert [p["step"] for p in queued] == ["take", "edit"]
        assert queued[1]["input"]["inputs"] == {
            "take": [
                {
                    "filename": "take.mp4",
                    "storage_uri": f"r2://ceq/outputs/{take.id}/take.mp4",
                    "file_type": "video",
                }
            ]
        }

    async def test_both_exports_are_released_together_and_the_production_completes(
        self, production_app, async_client, queued, db_session
    ):
        data = await submit(async_client)
        await finish(db_session, await job_for(db_session, data["id"], "take"))
        await finish(db_session, await job_for(db_session, data["id"], "edit"), outputs=["cut.mp4"])
        assert [p["step"] for p in queued] == ["take", "edit", "wide", "tall"]

        await finish(db_session, await job_for(db_session, data["id"], "wide"))
        await finish(db_session, await job_for(db_session, data["id"], "tall"))

        response = await async_client.get(f"/v1/productions/{data['id']}")
        assert response.json()["status"] == "completed"
        assert len(queued) == 4

    async def test_a_step_is_never_released_twice(
        self, production_app, async_client, queued, db_session
    ):
        data = await submit(async_client)
        take = await job_for(db_session, data["id"], "take")
        await finish(db_session, take)
        await on_job_finished(db_session, take)
        assert await release_ready_jobs(db_session, take.production_id) == []

        assert [p["step"] for p in queued] == ["take", "edit"]

    async def test_a_failed_step_cancels_everything_that_needed_it(
        self, production_app, async_client, queued, db_session
    ):
        data = await submit(async_client)

        await finish(db_session, await job_for(db_session, data["id"], "take"), status="failed")

        body = (await async_client.get(f"/v1/productions/{data['id']}")).json()
        assert body["status"] == "failed"
        states = {j["step"]: (j["status"], j["error"]) for j in body["jobs"]}
        assert states["edit"] == ("cancelled", "Not run: step 'take' did not complete.")
        assert states["wide"][0] == "cancelled"
        assert states["tall"][0] == "cancelled"
        assert [p["step"] for p in queued] == ["take"]

    async def test_a_failure_leaves_an_independent_branch_alone(
        self, production_app, async_client, queued, db_session
    ):
        data = await submit(
            async_client,
            {
                "name": "two branches",
                "steps": [
                    capture("a"),
                    capture("b"),
                    step("after-a", deps=["a"]),
                    step("after-b", deps=["b"]),
                ],
            },
        )
        a = await job_for(db_session, data["id"], "a")

        await finish(db_session, a, status="failed")
        cancelled_again = await cancel_dependents(db_session, a)

        assert cancelled_again == []
        assert (await job_for(db_session, data["id"], "after-a")).status == "cancelled"
        assert (await job_for(db_session, data["id"], "after-b")).status == "queued"
        await finish(db_session, await job_for(db_session, data["id"], "b"))
        assert [p["step"] for p in queued] == ["a", "b", "after-b"]

    async def test_a_job_outside_a_production_is_untouched(self, db_session, queued):
        lone = Job(kind="export", user_id=uuid4(), status=JobStatus.COMPLETED.value)
        await on_job_finished(db_session, lone)
        assert queued == []


class TestRepairAndCancel:
    async def test_a_second_terminal_report_is_ignored(
        self, production_app, async_client, queued, db_session
    ):
        data = await submit(async_client)
        take = await job_for(db_session, data["id"], "take")
        await finish(db_session, take, status="failed")

        result = await finish(db_session, take, status="completed", outputs=["late.mp4"])

        assert result.status == "failed"
        assert result.outputs_persisted == 0
        assert (await job_for(db_session, data["id"], "edit")).status == "cancelled"
        assert [p["step"] for p in queued] == ["take"]

    async def test_an_output_outside_its_job_prefix_is_not_passed_on(
        self, production_app, async_client, queued, db_session
    ):
        data = await submit(async_client)
        take = await job_for(db_session, data["id"], "take")
        await persist_job_completion(
            take.id,
            JobCompletionReport(
                status="completed",
                outputs=[
                    JobOutputReport(
                        filename="x",
                        storage_uri="file:///etc/passwd",
                        file_type="video",
                        file_size_bytes=1,
                    ),
                    JobOutputReport(
                        filename="ok.mp4",
                        storage_uri=f"r2://ceq/outputs/{take.id}/ok.mp4",
                        file_type="video",
                        file_size_bytes=1,
                    ),
                ],
            ),
            db_session,
        )

        assert [o["filename"] for o in queued[1]["input"]["inputs"]["take"]] == ["ok.mp4"]

    async def test_reading_queues_a_step_that_was_ready_but_never_queued(
        self, production_app, async_client, queued, db_session
    ):
        data = await submit(async_client)
        take = await job_for(db_session, data["id"], "take")
        take.status = "completed"  # completed without the hook, as an older pod would
        await db_session.flush()
        assert [p["step"] for p in queued] == ["take"]

        body = (await async_client.get(f"/v1/productions/{data['id']}")).json()

        assert [p["step"] for p in queued] == ["take", "edit"]
        assert {j["step"]: j["waiting"] for j in body["jobs"]}["edit"] is False

    async def test_cancelling_a_production_ends_every_unfinished_job(
        self, production_app, async_client, queued, db_session, mock_redis, monkeypatch
    ):
        monkeypatch.setattr(productions_router, "get_redis", lambda: mock_redis)
        data = await submit(async_client)
        await finish(db_session, await job_for(db_session, data["id"], "take"))

        response = await async_client.delete(f"/v1/productions/{data['id']}")

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "cancelled"
        assert {j["step"]: j["status"] for j in body["jobs"]} == {
            "take": "completed",
            "edit": "cancelled",
            "wide": "cancelled",
            "tall": "cancelled",
        }
        # Only `edit` had been queued, so only it is pulled and signalled.
        edit_id = str((await job_for(db_session, data["id"], "edit")).id)
        assert [c.args[0] for c in mock_redis.publish.call_args_list] == [
            f"ceq:job:{edit_id}:control"
        ]
        # And it frees the client's quota: nothing is unfinished any more.
        assert (await async_client.delete(f"/v1/productions/{data['id']}")).status_code == 200

    async def test_another_client_cannot_cancel(self, production_app, async_client, queued):
        data = await submit(async_client)

        async def other():
            return principal("other-client")

        production_app.dependency_overrides[get_production_principal] = other
        assert (await async_client.delete(f"/v1/productions/{data['id']}")).status_code == 404

    async def test_cancelling_one_job_cancels_what_needed_it(
        self, production_app, app, async_client, queued, db_session, mock_redis, monkeypatch
    ):
        from ceq_api.auth import get_service_or_user
        from ceq_api.routers import jobs as jobs_router

        async def as_owner():
            return principal()

        app.dependency_overrides[get_service_or_user] = as_owner
        monkeypatch.setattr(jobs_router, "get_redis", lambda: mock_redis)
        monkeypatch.setattr(jobs_router, "publish_job_update", AsyncMock())
        data = await submit(async_client)
        take = await job_for(db_session, data["id"], "take")

        response = await async_client.delete(f"/v1/jobs/{take.id}")

        assert response.status_code == 204
        body = (await async_client.get(f"/v1/productions/{data['id']}")).json()
        assert {j["status"] for j in body["jobs"]} == {"cancelled"}


class TestSubmitRoute:
    async def test_a_graph_that_cannot_run_is_422_and_stores_nothing(
        self, production_app, async_client, queued, db_session
    ):
        response = await async_client.post(
            "/v1/productions/",
            json={"name": "x", "steps": [capture("take", "https://example.com/")]},
        )

        assert response.status_code == 422
        assert "example.com" in response.json()["detail"]
        assert (await db_session.execute(select(Job))).scalars().all() == []
        assert queued == []

    async def test_no_host_is_allowed_by_default(self, app, async_client, queued, monkeypatch):
        async def override():
            return principal()

        app.dependency_overrides[get_production_principal] = override
        monkeypatch.setattr(productions_router.settings, "production_allowed_hosts", [])

        response = await async_client.post(
            "/v1/productions/", json={"name": "x", "steps": [capture("take")]}
        )

        assert response.status_code == 422

    @pytest.mark.parametrize("name", ["Take", "a b", "", "-lead", "x" * 65])
    async def test_step_names_are_plain(self, production_app, async_client, queued, name):
        response = await async_client.post(
            "/v1/productions/", json={"name": "x", "steps": [step(name)]}
        )
        assert response.status_code == 422

    async def test_bad_names_and_oversized_lists_are_422(
        self, production_app, async_client, queued
    ):
        for body in (
            {"name": "a\u0000b", "steps": [step("a")]},
            {"name": "x", "steps": [step(f"s{i}") for i in range(101)]},
            {"name": "x", "steps": [step("a", deps=["Not A Step"])]},
        ):
            assert (await async_client.post("/v1/productions/", json=body)).status_code == 422

    async def test_oversized_params_are_422(self, production_app, async_client, queued):
        response = await async_client.post(
            "/v1/productions/",
            json={"name": "x", "steps": [step("a", blob="y" * 20000)]},
        )
        assert response.status_code == 422

    async def test_active_productions_per_client_are_capped(
        self, production_app, async_client, queued, monkeypatch
    ):
        monkeypatch.setattr(productions_router.settings, "production_max_active_per_client", 2)
        await submit(async_client)
        await submit(async_client)

        response = await async_client.post("/v1/productions/", json=TRAILER)

        assert response.status_code == 429

    async def test_another_clients_production_is_404(self, production_app, async_client, queued):
        data = await submit(async_client)

        async def other():
            return principal("other-client")

        production_app.dependency_overrides[get_production_principal] = other

        response = await async_client.get(f"/v1/productions/{data['id']}")
        assert response.status_code == 404

    async def test_unknown_production_is_404(self, production_app, async_client):
        response = await async_client.get(f"/v1/productions/{uuid4()}")
        assert response.status_code == 404

    async def test_outputs_belong_to_the_submitting_principal(
        self, production_app, async_client, queued, db_session
    ):
        data = await submit(async_client)
        take = await job_for(db_session, data["id"], "take")
        await finish(db_session, take, outputs=["take.mp4"])

        output = (await db_session.execute(select(Output))).scalar_one()
        assert output.user_id == service_principal_id(CLIENT)


# ---------------------------------------------------------------------------
# Migration
# ---------------------------------------------------------------------------


class FakeOp:
    def __init__(self):
        self.calls: list[tuple] = []

    def __getattr__(self, name):
        def record(*args, **kwargs):
            self.calls.append((name, args, kwargs))

        return record


class TestMigration:
    def _migration(self):
        return importlib.import_module("ceq_api.alembic.versions.20261119_add_productions")

    def test_new_job_columns_cannot_break_an_older_writer(self, monkeypatch):
        migration = self._migration()
        fake = FakeOp()
        monkeypatch.setattr(migration, "op", fake)

        migration.upgrade()

        assert "lock_timeout" in fake.calls[0][1][0]
        columns = [args[1] for name, args, _ in fake.calls if name == "add_column"]
        assert {c.name for c in columns} == {"production_id", "step", "depends_on", "released_at"}
        for column in columns:
            assert column.nullable or column.server_default is not None, column.name

    def test_downgrade_removes_what_upgrade_added(self, monkeypatch):
        migration = self._migration()
        fake = FakeOp()
        monkeypatch.setattr(migration, "op", fake)

        migration.downgrade()

        dropped = [args[1] for name, args, _ in fake.calls if name == "drop_column"]
        assert set(dropped) == {"production_id", "step", "depends_on", "released_at"}
        assert fake.calls[-1][0] == "drop_table"

    def test_it_is_the_single_head(self):
        from alembic.config import Config
        from alembic.script import ScriptDirectory

        config = Config()
        config.set_main_option("script_location", "ceq_api:alembic")
        assert ScriptDirectory.from_config(config).get_heads() == ["20261119_productions"]
