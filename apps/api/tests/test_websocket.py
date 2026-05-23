"""Tests for WebSocket job streaming."""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from starlette.websockets import WebSocketDisconnect


class FakeQueryResult:
    """Query result stub used by fake async SQLAlchemy sessions."""

    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class FakeDbSession:
    """Minimal async session used by websocket ownership checks."""

    def __init__(self, job):
        self._job = job

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):  # noqa: ARG002
        return None

    async def execute(self, _query):
        return FakeQueryResult(self._job)


class FakePubSub:
    """Redis pubsub shim with deterministic message playback."""

    def __init__(self, messages: list[dict] | None = None):
        self.messages = messages or []
        self.subscribe_calls: list[str] = []
        self.unsubscribe_calls: list[tuple[str]] = []
        self.closed = False

    async def subscribe(self, channel: str) -> None:
        self.subscribe_calls.append(channel)

    async def unsubscribe(self, channel: str) -> None:
        self.unsubscribe_calls.append((channel,))

    async def close(self) -> None:
        self.closed = True

    async def listen(self):
        for message in self.messages:
            yield message


class FakeRedis:
    """Redis client shim with injectable initial status + pubsub messages."""

    def __init__(self, messages: list[dict] | None = None, initial_status: dict[str, str] | None = None):
        self.pubsub_obj = FakePubSub(messages or [])
        self.initial_status = initial_status or {}

    def pubsub(self):
        return self.pubsub_obj

    async def hgetall(self, key: str):  # noqa: ARG002
        return self.initial_status


def pubsub_message(message_type: str, payload: dict | None = None) -> dict:
    return {
        "type": "message",
        "data": json.dumps({"type": message_type, "data": payload or {}}),
    }


class TestWebSocketAuthentication:
    """Tests for WebSocket authentication."""

    def test_websocket_without_token(self, client):
        """WebSocket connection without token should be rejected."""
        job_id = uuid4()

        with pytest.raises(WebSocketDisconnect) as exc_info:
            with client.websocket_connect(f"/v1/jobs/{job_id}/stream") as websocket:
                del websocket

        assert exc_info.value.code == 4001

    def test_websocket_with_invalid_token(self, client, mock_user):
        """Invalid tokens must close with auth required."""
        job_id = uuid4()

        with patch("ceq_api.routers.jobs.validate_token", return_value=None):
            with pytest.raises(WebSocketDisconnect) as exc_info:
                with client.websocket_connect(f"/v1/jobs/{job_id}/stream?token=invalid"):
                    pass

        assert exc_info.value.code == 4001


class TestWebSocketJobOwnership:
    """Tests for WebSocket job ownership verification."""

    def test_websocket_job_not_found(self, client, mock_user):
        """A missing job should close with 4004."""
        job_id = uuid4()

        with patch("ceq_api.db.session.async_session_maker", return_value=FakeDbSession(None)):
            with patch(
                "ceq_api.routers.jobs.validate_token",
                AsyncMock(return_value=mock_user),
            ):
                with pytest.raises(WebSocketDisconnect) as exc_info:
                    with client.websocket_connect(f"/v1/jobs/{job_id}/stream?token=valid"):
                        pass

        assert exc_info.value.code == 4004

    def test_websocket_job_not_owned(self, client, mock_user):
        """Jobs owned by someone else should close with 4003."""
        job_id = uuid4()
        other_user_id = uuid4()
        job = SimpleNamespace(id=job_id, user_id=other_user_id)

        with patch("ceq_api.db.session.async_session_maker", return_value=FakeDbSession(job)):
            with patch(
                "ceq_api.routers.jobs.validate_token",
                AsyncMock(return_value=mock_user),
            ):
                with pytest.raises(WebSocketDisconnect) as exc_info:
                    with client.websocket_connect(f"/v1/jobs/{job_id}/stream?token=valid"):
                        pass

        assert exc_info.value.code == 4003


class TestWebSocketMessaging:
    """Tests for WebSocket message handling."""

    def test_websocket_ping_pong(self, client, mock_user):
        """WebSocket should respond to ping with pong."""
        job_id = uuid4()
        job = SimpleNamespace(id=job_id, user_id=mock_user.id)
        fake_redis = FakeRedis(messages=[], initial_status={"status": "running", "progress": "0.35"})

        with patch("ceq_api.db.session.async_session_maker", return_value=FakeDbSession(job)):
            with patch("ceq_api.routers.jobs.get_redis", return_value=fake_redis):
                with patch(
                    "ceq_api.routers.jobs.validate_token",
                    AsyncMock(return_value=mock_user),
                ):
                    with client.websocket_connect(f"/v1/jobs/{job_id}/stream?token=valid") as websocket:
                        assert websocket.receive_json()["type"] == "connected"
                        assert websocket.receive_json()["type"] == "status"
                        websocket.send_text("ping")
                        assert websocket.receive_json()["type"] == "pong"

    def test_websocket_keepalive(self, client, mock_user):
        """WebSocket should send keepalive when no messages arrive from the client."""
        job_id = uuid4()
        job = SimpleNamespace(id=job_id, user_id=mock_user.id)
        fake_redis = FakeRedis(messages=[], initial_status={"status": "queued", "progress": "0.0"})

        async def timeout_immediately(*_args, **_kwargs):
            raise TimeoutError

        with patch("ceq_api.db.session.async_session_maker", return_value=FakeDbSession(job)):
            with patch("ceq_api.routers.jobs.get_redis", return_value=fake_redis):
                with patch(
                    "ceq_api.routers.jobs.validate_token",
                    AsyncMock(return_value=mock_user),
                ):
                    with patch("ceq_api.routers.jobs.asyncio.wait_for", side_effect=timeout_immediately):
                        with client.websocket_connect(f"/v1/jobs/{job_id}/stream?token=valid") as websocket:
                            assert websocket.receive_json()["type"] == "connected"
                            assert websocket.receive_json()["type"] == "status"
                            assert websocket.receive_json()["type"] == "keepalive"


class TestWebSocketPubSub:
    """Tests for Redis pub/sub integration."""

    def test_websocket_receives_progress_updates(self, client, mock_user):
        """WebSocket should forward Redis pubsub payloads."""
        job_id = uuid4()
        job = SimpleNamespace(id=job_id, user_id=mock_user.id)
        fake_redis = FakeRedis(
            messages=[
                pubsub_message("progress", {"percent": 0.62}),
                pubsub_message("complete", {"message": "done"}),
            ],
            initial_status={"status": "running", "progress": "0.42"},
        )

        with patch("ceq_api.db.session.async_session_maker", return_value=FakeDbSession(job)):
            with patch("ceq_api.routers.jobs.get_redis", return_value=fake_redis):
                with patch(
                    "ceq_api.routers.jobs.validate_token",
                    AsyncMock(return_value=mock_user),
                ):
                    with client.websocket_connect(f"/v1/jobs/{job_id}/stream?token=valid") as websocket:
                        assert websocket.receive_json()["type"] == "connected"
                        assert websocket.receive_json()["type"] == "status"
                        data = websocket.receive_json()
                        assert data["type"] == "progress"
                        assert data["data"]["percent"] == 0.62
                        # Terminal message should close the stream cleanly.
                        assert websocket.receive_json()["type"] == "complete"
                        websocket.close()

    def test_websocket_receives_completion(self, client, mock_user):
        """WebSocket should forward terminal completion message."""
        job_id = uuid4()
        job = SimpleNamespace(id=job_id, user_id=mock_user.id)
        fake_redis = FakeRedis(
            messages=[pubsub_message("complete", {"message": "finished"})],
            initial_status={"status": "running", "progress": "1.0"},
        )

        with patch("ceq_api.db.session.async_session_maker", return_value=FakeDbSession(job)):
            with patch("ceq_api.routers.jobs.get_redis", return_value=fake_redis):
                with patch(
                    "ceq_api.routers.jobs.validate_token",
                    AsyncMock(return_value=mock_user),
                ):
                    with client.websocket_connect(f"/v1/jobs/{job_id}/stream?token=valid") as websocket:
                        assert websocket.receive_json()["type"] == "connected"
                        assert websocket.receive_json()["type"] == "status"
                        completion = websocket.receive_json()
                        assert completion["type"] == "complete"


class TestWebSocketErrorHandling:
    """Tests for WebSocket error handling."""

    def test_websocket_disconnect_cleanup(self, client, mock_user):
        """WebSocket disconnect should always clean up Redis pubsub state."""
        job_id = uuid4()
        job = SimpleNamespace(id=job_id, user_id=mock_user.id)
        fake_redis = FakeRedis(messages=[pubsub_message("complete", {"message": "done"})])

        with patch("ceq_api.db.session.async_session_maker", return_value=FakeDbSession(job)):
            with patch("ceq_api.routers.jobs.get_redis", return_value=fake_redis):
                with patch(
                    "ceq_api.routers.jobs.validate_token",
                    AsyncMock(return_value=mock_user),
                ):
                    with client.websocket_connect(f"/v1/jobs/{job_id}/stream?token=valid") as websocket:
                        assert websocket.receive_json()["type"] == "connected"
                        websocket.receive_json()  # status / complete if any initial status omitted
                        websocket.receive_json()  # completion marker

        assert fake_redis.pubsub_obj.subscribe_calls == [f"ceq:job:{job_id}:status"]
        assert fake_redis.pubsub_obj.unsubscribe_calls == [(f"ceq:job:{job_id}:status",)]
        assert fake_redis.pubsub_obj.closed is True

    def test_websocket_malformed_pubsub_message(self, client, mock_user):
        """Malformed pubsub payloads should not terminate the connection."""
        job_id = uuid4()
        job = SimpleNamespace(id=job_id, user_id=mock_user.id)
        fake_redis = FakeRedis(
            messages=[
                {"type": "message", "data": "not-json"},
                pubsub_message("complete", {"message": "done"}),
            ],
            initial_status={"status": "running", "progress": "0.1"},
        )

        with patch("ceq_api.db.session.async_session_maker", return_value=FakeDbSession(job)):
            with patch("ceq_api.routers.jobs.get_redis", return_value=fake_redis):
                with patch(
                    "ceq_api.routers.jobs.validate_token",
                    AsyncMock(return_value=mock_user),
                ):
                    with client.websocket_connect(f"/v1/jobs/{job_id}/stream?token=valid") as websocket:
                        assert websocket.receive_json()["type"] == "connected"
                        assert websocket.receive_json()["type"] == "status"
                        complete = websocket.receive_json()
                        assert complete["type"] == "complete"

    def test_websocket_redis_connection_error(self, client, mock_user):
        """Redis failures should be turned into error messages instead of hard crashes."""

        class FailingRedis(FakeRedis):
            async def hgetall(self, key: str):  # noqa: ARG002
                raise RuntimeError("redis unavailable")

        job_id = uuid4()
        job = SimpleNamespace(id=job_id, user_id=mock_user.id)
        fake_redis = FailingRedis(messages=[pubsub_message("complete", {"message": "done"})])

        with patch("ceq_api.db.session.async_session_maker", return_value=FakeDbSession(job)):
            with patch("ceq_api.routers.jobs.get_redis", return_value=fake_redis):
                with patch(
                    "ceq_api.routers.jobs.validate_token",
                    AsyncMock(return_value=mock_user),
                ):
                    with client.websocket_connect(f"/v1/jobs/{job_id}/stream?token=valid") as websocket:
                        assert websocket.receive_json()["type"] == "connected"
                        terminal = websocket.receive_json()
                        assert terminal["type"] == "error"
                        assert "redis unavailable" in terminal["data"]["message"]


class TestWebSocketCloseCodes:
    """Tests for WebSocket close codes."""

    def test_close_code_4001_auth_required(self, client):
        """Close code 4001 should be used for missing authentication."""
        with pytest.raises(WebSocketDisconnect) as exc_info:
            with client.websocket_connect(f"/v1/jobs/{uuid4()}/stream"):
                pass

        assert exc_info.value.code == 4001

    def test_close_code_4003_access_denied(self, client, mock_user):
        """Close code 4003 should be used when job ownership check fails."""
        other_user_id = uuid4()
        job_id = uuid4()
        job = SimpleNamespace(id=job_id, user_id=other_user_id)

        with patch("ceq_api.db.session.async_session_maker", return_value=FakeDbSession(job)):
            with patch(
                "ceq_api.routers.jobs.validate_token",
                AsyncMock(return_value=mock_user),
            ):
                with pytest.raises(WebSocketDisconnect) as exc_info:
                    with client.websocket_connect(f"/v1/jobs/{job_id}/stream?token=valid"):
                        pass

        assert exc_info.value.code == 4003

    def test_close_code_4004_not_found(self, client, mock_user):
        """Close code 4004 should be used for missing jobs."""
        with patch("ceq_api.db.session.async_session_maker", return_value=FakeDbSession(None)):
            with patch(
                "ceq_api.routers.jobs.validate_token",
                AsyncMock(return_value=mock_user),
            ):
                with pytest.raises(WebSocketDisconnect) as exc_info:
                    with client.websocket_connect(f"/v1/jobs/{uuid4()}/stream?token=valid"):
                        pass

        assert exc_info.value.code == 4004
