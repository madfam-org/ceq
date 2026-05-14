"""Tests for admin operations endpoints."""

from __future__ import annotations

import json
from uuid import uuid4

import httpx
import pytest
from fastapi import status

from ceq_api.auth import get_current_user


async def _override_admin(mock_admin_user):
    return mock_admin_user


def _dead_letter(job_id: str) -> str:
    return json.dumps(
        {
            "job_id": job_id,
            "worker_id": "ceq-worker-0",
            "url": f"http://test/v1/jobs/{job_id}/outputs/report",
            "payload": {
                "status": "completed",
                "outputs": [
                    {
                        "filename": "output.png",
                        "storage_uri": "r2://ceq-assets/outputs/job/output.png",
                        "file_type": "image/png",
                        "file_size_bytes": 1024,
                    }
                ],
            },
            "error": "HTTP 503",
            "status_code": 503,
            "attempts": 3,
        }
    )


class TestOperationsAuth:
    def test_operations_status_requires_admin(self, client):
        response = client.get("/v1/operations/status")

        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert "Admin access required" in response.json()["detail"]


class TestOperationsStatus:
    @pytest.mark.asyncio
    async def test_status_returns_runtime_gates(
        self,
        app,
        async_client,
        mock_admin_user,
        mock_redis,
        monkeypatch,
    ):
        from ceq_api.routers import operations

        async def admin_user():
            return await _override_admin(mock_admin_user)

        app.dependency_overrides[get_current_user] = admin_user
        monkeypatch.setattr(operations.settings, "job_completion_callback_token", "token")
        monkeypatch.setattr(operations.settings, "job_webhook_secret", "webhook-secret")

        async def llen(key):
            return {
                "ceq:jobs:pending": 2,
                "ceq:jobs:processing": 1,
                "ceq:jobs:completion:dead": 3,
            }.get(key, 0)

        mock_redis.llen.side_effect = llen

        response = await async_client.get("/v1/operations/status")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["callback_token_configured"] is True
        assert data["webhook_secret_configured"] is True
        assert data["redis"]["pending_jobs"] == 2
        assert data["redis"]["processing_jobs"] == 1
        assert data["redis"]["completion_dead_letters"] == 3


class TestCompletionDeadLetters:
    @pytest.mark.asyncio
    async def test_list_completion_dead_letters(
        self,
        app,
        async_client,
        mock_admin_user,
        mock_redis,
    ):
        async def admin_user():
            return await _override_admin(mock_admin_user)

        app.dependency_overrides[get_current_user] = admin_user
        job_id = str(uuid4())
        mock_redis.lrange.return_value = [_dead_letter(job_id)]
        mock_redis.llen.return_value = 1

        response = await async_client.get("/v1/operations/completion-dead-letters")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["redis_key"] == "ceq:jobs:completion:dead"
        assert data["count"] == 1
        assert data["items"][0]["index"] == 0
        assert data["items"][0]["job_id"] == job_id
        assert data["items"][0]["payload"]["status"] == "completed"

    @pytest.mark.asyncio
    async def test_replay_completion_dead_letter_removes_success(
        self,
        app,
        async_client,
        mock_admin_user,
        mock_redis,
        monkeypatch,
    ):
        from ceq_api.routers import operations

        async def admin_user():
            return await _override_admin(mock_admin_user)

        class FakeReplayClient:
            calls: list[dict] = []

            def __init__(self, timeout):
                self.timeout = timeout

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                return None

            async def post(self, url, headers, json):
                self.__class__.calls.append(
                    {
                        "url": url,
                        "headers": headers,
                        "json": json,
                        "timeout": self.timeout,
                    }
                )
                return httpx.Response(200, json={"ok": True})

        app.dependency_overrides[get_current_user] = admin_user
        monkeypatch.setattr(operations.settings, "job_completion_callback_token", "token")
        monkeypatch.setattr(operations.httpx, "AsyncClient", FakeReplayClient)

        job_id = str(uuid4())
        raw = _dead_letter(job_id)
        mock_redis.lrange.return_value = [raw]
        mock_redis.lrem.return_value = 1

        response = await async_client.post("/v1/operations/completion-dead-letters/0/replay")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["status"] == "replayed"
        assert data["removed"] is True
        assert data["job_id"] == job_id
        assert FakeReplayClient.calls[0]["headers"]["X-CEQ-Worker-Token"] == "token"
        assert FakeReplayClient.calls[0]["json"]["status"] == "completed"
        mock_redis.lrem.assert_awaited_once_with("ceq:jobs:completion:dead", 1, raw)
        mock_redis.hset.assert_awaited()

    @pytest.mark.asyncio
    async def test_replay_completion_dead_letter_keeps_failed_payload(
        self,
        app,
        async_client,
        mock_admin_user,
        mock_redis,
        monkeypatch,
    ):
        from ceq_api.routers import operations

        async def admin_user():
            return await _override_admin(mock_admin_user)

        class FailingReplayClient:
            def __init__(self, timeout):
                self.timeout = timeout

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                return None

            async def post(self, url, headers, json):
                return httpx.Response(422, text="invalid payload")

        app.dependency_overrides[get_current_user] = admin_user
        monkeypatch.setattr(operations.settings, "job_completion_callback_token", "token")
        monkeypatch.setattr(operations.httpx, "AsyncClient", FailingReplayClient)
        mock_redis.lrange.return_value = [_dead_letter(str(uuid4()))]

        response = await async_client.post("/v1/operations/completion-dead-letters/0/replay")

        assert response.status_code == status.HTTP_502_BAD_GATEWAY
        assert response.json()["detail"]["upstream_status_code"] == 422
        mock_redis.lrem.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_discard_completion_dead_letter(
        self,
        app,
        async_client,
        mock_admin_user,
        mock_redis,
    ):
        async def admin_user():
            return await _override_admin(mock_admin_user)

        app.dependency_overrides[get_current_user] = admin_user
        raw = _dead_letter(str(uuid4()))
        mock_redis.lrange.return_value = [raw]
        mock_redis.lrem.return_value = 1

        response = await async_client.delete("/v1/operations/completion-dead-letters/0")

        assert response.status_code == status.HTTP_200_OK
        assert response.json() == {"index": 0, "removed": True}
        mock_redis.lrem.assert_awaited_once_with("ceq:jobs:completion:dead", 1, raw)
