"""Tests for the HTTPS lease-mode consumer (``ceq_worker.lease``).

All HTTP is mocked: these assert the worker's *protocol* behavior — token
minting and proactive refresh, empty-queue backoff, heartbeat cadence, lease
loss, and how handler results map onto /complete vs /fail.
"""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from ceq_worker.config import Settings
from ceq_worker.lease import (
    LeaseConsumer,
    ServiceTokenProvider,
    TokenExpiredError,
    _completion_output_payload,
)


def make_response(status_code: int, json_body: dict | None = None) -> MagicMock:
    """A stand-in for an httpx.Response with the fields the consumer reads."""
    response = MagicMock(spec=httpx.Response)
    response.status_code = status_code
    response.json.return_value = json_body or {}
    response.text = "" if json_body is None else str(json_body)
    return response


# ---------------------------------------------------------------------------
# Mode selection
# ---------------------------------------------------------------------------


class TestLeaseModeSelection:
    """Redis mode stays the default; lease mode needs the full credential set."""

    def test_disabled_without_configuration(self):
        assert Settings(_env_file=None).lease_mode_enabled is False

    def test_disabled_when_credentials_are_partial(self):
        partial = Settings(
            _env_file=None,
            lease_url="https://api.ceq.lol",
            janua_client_id="ceq-gpu-worker",
            janua_client_secret="",
        )
        assert partial.lease_mode_enabled is False

    def test_enabled_with_url_and_credentials(self):
        configured = Settings(
            _env_file=None,
            lease_url="https://api.ceq.lol",
            janua_client_id="ceq-gpu-worker",
            janua_client_secret="shhh",
        )
        assert configured.lease_mode_enabled is True

    def test_default_scope_is_the_worker_scope(self):
        """Not ceq:render — executing jobs is a separate capability."""
        assert Settings(_env_file=None).janua_scope == "ceq:worker"


# ---------------------------------------------------------------------------
# Token provider
# ---------------------------------------------------------------------------


class TestServiceTokenProvider:
    """client_credentials minting, cached and refreshed ahead of expiry."""

    async def test_mints_and_caches_a_token(self):
        client = MagicMock()
        client.post = AsyncMock(
            return_value=make_response(
                200, {"access_token": "tok-1", "expires_in": 3600}
            )
        )
        provider = ServiceTokenProvider(client)

        assert await provider.get_token() == "tok-1"
        assert await provider.get_token() == "tok-1"
        # Cached: one network mint for two reads.
        assert client.post.await_count == 1

    async def test_requests_client_credentials_grant_with_scope(self):
        client = MagicMock()
        client.post = AsyncMock(
            return_value=make_response(200, {"access_token": "t", "expires_in": 60})
        )

        await ServiceTokenProvider(client).get_token()

        payload = client.post.await_args.kwargs["data"]
        assert payload["grant_type"] == "client_credentials"
        assert payload["scope"] == "ceq:worker"

    async def test_remints_before_expiry(self):
        """A GPU job can outlive a token; discovering that at /complete is fatal."""
        client = MagicMock()
        client.post = AsyncMock(
            side_effect=[
                # Expires inside the refresh leeway, so the next read re-mints.
                make_response(200, {"access_token": "tok-1", "expires_in": 30}),
                make_response(200, {"access_token": "tok-2", "expires_in": 3600}),
            ]
        )
        provider = ServiceTokenProvider(client)

        assert await provider.get_token() == "tok-1"
        assert await provider.get_token() == "tok-2"

    async def test_force_refresh_bypasses_the_cache(self):
        client = MagicMock()
        client.post = AsyncMock(
            side_effect=[
                make_response(200, {"access_token": "tok-1", "expires_in": 3600}),
                make_response(200, {"access_token": "tok-2", "expires_in": 3600}),
            ]
        )
        provider = ServiceTokenProvider(client)

        assert await provider.get_token() == "tok-1"
        assert await provider.get_token(force_refresh=True) == "tok-2"

    async def test_rejected_credentials_raise(self):
        client = MagicMock()
        client.post = AsyncMock(return_value=make_response(401))

        with pytest.raises(TokenExpiredError):
            await ServiceTokenProvider(client).get_token()

    async def test_missing_access_token_raises(self):
        client = MagicMock()
        client.post = AsyncMock(return_value=make_response(200, {"token_type": "Bearer"}))

        with pytest.raises(TokenExpiredError):
            await ServiceTokenProvider(client).get_token()


# ---------------------------------------------------------------------------
# Lease polling
# ---------------------------------------------------------------------------


def build_consumer() -> LeaseConsumer:
    """A consumer with its HTTP layer stubbed out."""
    consumer = LeaseConsumer()
    consumer._client = MagicMock()
    consumer._tokens = MagicMock()
    consumer._tokens.get_token = AsyncMock(return_value="tok")
    consumer._running = True
    return consumer


class TestLeasePolling:
    async def test_empty_queue_returns_none(self):
        """204 is the normal empty-queue answer, not an error."""
        consumer = build_consumer()
        consumer._post = AsyncMock(return_value=make_response(204))

        assert await consumer._lease_one() is None

    async def test_leased_job_is_returned(self):
        consumer = build_consumer()
        consumer._post = AsyncMock(
            return_value=make_response(
                200,
                {"job_id": "job-1", "payload": {"input": {}}, "attempt": 1},
            )
        )

        leased = await consumer._lease_one()
        assert leased is not None
        assert leased["job_id"] == "job-1"

    async def test_missing_scope_raises_credential_error(self):
        """A 403 means the Janua client grant is wrong — not a transient blip."""
        consumer = build_consumer()
        consumer._post = AsyncMock(return_value=make_response(403))

        with pytest.raises(TokenExpiredError, match="scope"):
            await consumer._lease_one()

    async def test_server_error_raises_transport_error(self):
        consumer = build_consumer()
        consumer._post = AsyncMock(return_value=make_response(503))

        with pytest.raises(httpx.HTTPError):
            await consumer._lease_one()

    async def test_post_remints_once_on_401(self):
        """Covers a credential rotated mid-flight, after the proactive refresh."""
        consumer = LeaseConsumer()
        consumer._client = MagicMock()
        consumer._client.post = AsyncMock(
            side_effect=[make_response(401), make_response(200, {"ok": True})]
        )
        consumer._tokens = MagicMock()
        consumer._tokens.get_token = AsyncMock(return_value="tok")

        response = await consumer._post("/v1/worker/lease", {})

        assert response.status_code == 200
        consumer._tokens.get_token.assert_any_await(force_refresh=True)
        assert consumer._client.post.await_count == 2

    async def test_post_does_not_loop_on_repeated_401(self):
        consumer = LeaseConsumer()
        consumer._client = MagicMock()
        consumer._client.post = AsyncMock(return_value=make_response(401))
        consumer._tokens = MagicMock()
        consumer._tokens.get_token = AsyncMock(return_value="tok")

        response = await consumer._post("/v1/worker/lease", {})

        assert response.status_code == 401
        # One retry only — not an infinite re-mint loop.
        assert consumer._client.post.await_count == 2


# ---------------------------------------------------------------------------
# Heartbeat
# ---------------------------------------------------------------------------


class TestHeartbeat:
    async def test_returns_when_lease_is_lost(self):
        """409 means another worker owns the job now; stop immediately."""
        consumer = build_consumer()
        consumer._post = AsyncMock(return_value=make_response(409))

        start = time.time()
        await consumer._heartbeat_loop("job-1", interval=0)

        assert time.time() - start < 1
        assert consumer._cancel_requested is False

    async def test_returns_and_flags_on_cancel(self):
        consumer = build_consumer()
        consumer._post = AsyncMock(
            return_value=make_response(
                200, {"lease_expires_at": "2026-01-01T00:00:00Z", "cancel_requested": True}
            )
        )

        await consumer._heartbeat_loop("job-1", interval=0)

        assert consumer._cancel_requested is True

    async def test_survives_a_transient_network_error(self):
        """The visibility timeout has room for a missed beat by design."""
        consumer = build_consumer()
        consumer._post = AsyncMock(
            side_effect=[
                httpx.ConnectError("blip"),
                make_response(200, {"cancel_requested": True}),
            ]
        )

        await consumer._heartbeat_loop("job-1", interval=0)

        # It kept going after the error rather than abandoning the job.
        assert consumer._post.await_count == 2
        assert consumer._cancel_requested is True


# ---------------------------------------------------------------------------
# Result reporting
# ---------------------------------------------------------------------------


class TestResultReporting:
    async def test_success_posts_complete_with_outputs(self):
        consumer = build_consumer()
        consumer._post = AsyncMock(return_value=make_response(200, {"status": "completed"}))

        await consumer._report_result(
            "job-1",
            {
                "success": True,
                "outputs": [
                    {
                        "filename": "out.png",
                        "storage_uri": "r2://ceq-assets/outputs/out.png",
                        "file_type": "image/png",
                        "file_size_bytes": 1024,
                    }
                ],
                "execution_time": 9.5,
            },
            elapsed=10.0,
        )

        path, payload = consumer._post.await_args.args
        assert path == "/v1/worker/jobs/job-1/complete"
        assert payload["gpu_seconds"] == 9.5
        assert payload["outputs"][0]["storage_uri"] == "r2://ceq-assets/outputs/out.png"

    async def test_execution_failure_is_reported_retryable(self):
        """A different GPU box may well succeed; the API caps the attempts."""
        consumer = build_consumer()
        consumer._post = AsyncMock(return_value=make_response(200, {"requeued": True}))

        await consumer._report_result(
            "job-1", {"success": False, "error": "CUDA OOM"}, elapsed=3.0
        )

        path, payload = consumer._post.await_args.args
        assert path == "/v1/worker/jobs/job-1/fail"
        assert payload["retryable"] is True
        assert payload["cancelled"] is False

    async def test_cancelled_result_is_reported_non_retryable(self):
        consumer = build_consumer()
        consumer._post = AsyncMock(return_value=make_response(200, {}))

        await consumer._report_result(
            "job-1",
            {"success": False, "cancelled": True, "error": "Job cancelled"},
            elapsed=1.0,
        )

        _path, payload = consumer._post.await_args.args
        assert payload["cancelled"] is True
        assert payload["retryable"] is False

    async def test_failure_report_transport_error_is_swallowed(self):
        """The lease expires and the reaper recovers the job — do not crash."""
        consumer = build_consumer()
        consumer._post = AsyncMock(side_effect=httpx.ConnectError("down"))

        await consumer._report_fail("job-1", error="boom", retryable=True)


class TestOutputNormalization:
    """Same descriptor shape the Redis path sends, so both modes persist alike."""

    def test_known_fields_map_directly(self):
        payload = _completion_output_payload(
            {
                "filename": "out.png",
                "storage_uri": "r2://b/out.png",
                "file_type": "image/png",
                "file_size_bytes": 512,
                "width": 1024,
                "height": 1024,
            }
        )

        assert payload["filename"] == "out.png"
        assert payload["width"] == 1024
        assert payload["duration_seconds"] is None

    def test_unknown_fields_fold_into_metadata(self):
        payload = _completion_output_payload(
            {
                "filename": "out.png",
                "storage_uri": "r2://b/out.png",
                "file_type": "image/png",
                "file_size_bytes": 512,
                "public_url": "https://cdn/out.png",
                "seed": 42,
            }
        )

        assert payload["metadata"]["public_url"] == "https://cdn/out.png"
        assert payload["metadata"]["seed"] == 42

    def test_existing_metadata_is_preserved(self):
        payload = _completion_output_payload(
            {
                "filename": "out.png",
                "storage_uri": "r2://b/out.png",
                "file_type": "image/png",
                "file_size_bytes": 512,
                "metadata": {"model_hash": "abc"},
                "seed": 7,
            }
        )

        assert payload["metadata"]["model_hash"] == "abc"
        assert payload["metadata"]["seed"] == 7


class TestInitializationGuard:
    async def test_initialize_refuses_without_credentials(self):
        consumer = LeaseConsumer()

        with pytest.raises(RuntimeError, match="CEQ_LEASE_URL"):
            await consumer.initialize()
