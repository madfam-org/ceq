"""Tests for job management endpoints."""

import hashlib
import hmac
import json
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import httpx
import pytest
from fastapi import status

from ceq_api.models.job import Job, JobStatus
from ceq_api.models.output import Output


class TestListJobs:
    """Tests for GET /v1/jobs/"""

    def test_list_jobs_empty(self, client):
        """Should return empty list when no jobs exist."""
        response = client.get("/v1/jobs/")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["jobs"] == []
        assert data["total"] == 0

    @pytest.mark.asyncio
    async def test_list_jobs_with_data(self, async_client, db_session, mock_user):
        """Should return jobs owned by user."""
        # Create a workflow first (required for job foreign key)
        from ceq_api.models.workflow import Workflow

        workflow = Workflow(
            name="Test Workflow",
            description="Test",
            workflow_json={"test": "data"},
            input_schema={},
            user_id=mock_user.id,
        )
        db_session.add(workflow)
        await db_session.flush()

        # Create test job
        job = Job(
            workflow_id=workflow.id,
            user_id=mock_user.id,
            status=JobStatus.QUEUED.value,
            progress=0.0,
            input_params={"prompt": "test"},
            queued_at=datetime.now(UTC),
        )
        db_session.add(job)
        await db_session.commit()

        response = await async_client.get("/v1/jobs/")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert len(data["jobs"]) == 1
        assert data["jobs"][0]["status"] == "queued"

    def test_list_jobs_filter_by_status(self, client):
        """Should filter jobs by status."""
        response = client.get("/v1/jobs/?status_filter=running")

        assert response.status_code == status.HTTP_200_OK
        # All returned jobs should have running status
        for job in response.json()["jobs"]:
            assert job["status"] == "running"

    def test_list_jobs_invalid_status_filter(self, client):
        """Should reject invalid status filter."""
        response = client.get("/v1/jobs/?status_filter=invalid")

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "Invalid status" in response.json()["detail"]

    def test_list_jobs_pagination(self, client):
        """Should respect pagination parameters."""
        response = client.get("/v1/jobs/?skip=0&limit=10")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["skip"] == 0
        assert data["limit"] == 10


class TestGetJob:
    """Tests for GET /v1/jobs/{job_id}"""

    def test_get_job_not_found(self, client):
        """Should return 404 for non-existent job."""
        fake_id = uuid4()
        response = client.get(f"/v1/jobs/{fake_id}")

        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert "not found" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_get_job_success(self, async_client, db_session, mock_user):
        """Should return job details."""
        # Create workflow and job
        from ceq_api.models.workflow import Workflow

        workflow = Workflow(
            name="Test Workflow",
            description="Test",
            workflow_json={"test": "data"},
            input_schema={},
            user_id=mock_user.id,
        )
        db_session.add(workflow)
        await db_session.flush()

        job = Job(
            workflow_id=workflow.id,
            user_id=mock_user.id,
            status=JobStatus.RUNNING.value,
            progress=0.5,
            current_node="KSampler",
            input_params={"prompt": "test"},
            output_metadata={"cancel_requested_at": "2026-05-14T00:00:00+00:00"},
            queued_at=datetime.now(UTC),
        )
        db_session.add(job)
        await db_session.flush()

        db_session.add(
            Output(
                job_id=job.id,
                user_id=mock_user.id,
                filename="output.png",
                storage_uri="r2://ceq-assets/outputs/output.png",
                file_type="image/png",
                file_size_bytes=1024,
                width=512,
                height=512,
                output_metadata={"seed": 42},
                published_to=[{"channel": "webhook", "url": "https://hooks.example.com", "published_at": "2026-05-14T00:00:01+00:00"}],
            )
        )
        await db_session.commit()

        response = await async_client.get(f"/v1/jobs/{job.id}")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["status"] == "running"
        assert data["progress"] == 0.5
        assert data["current_node"] == "KSampler"
        assert data["output_metadata"]["cancel_requested_at"] == "2026-05-14T00:00:00+00:00"
        assert data["outputs"][0]["metadata"]["seed"] == 42
        assert data["outputs"][0]["published_to"][0]["channel"] == "webhook"
        assert "brand_message" in data

    @pytest.mark.asyncio
    async def test_get_job_forbidden(self, async_client, db_session, mock_user):
        """Should return 403 when accessing another user's job."""
        from ceq_api.models.workflow import Workflow

        other_user_id = uuid4()

        workflow = Workflow(
            name="Test Workflow",
            description="Test",
            workflow_json={"test": "data"},
            input_schema={},
            user_id=other_user_id,
        )
        db_session.add(workflow)
        await db_session.flush()

        job = Job(
            workflow_id=workflow.id,
            user_id=other_user_id,  # Different user
            status=JobStatus.QUEUED.value,
            progress=0.0,
            input_params={},
            queued_at=datetime.now(UTC),
        )
        db_session.add(job)
        await db_session.commit()

        response = await async_client.get(f"/v1/jobs/{job.id}")

        assert response.status_code == status.HTTP_403_FORBIDDEN


class TestPollJobStatus:
    """Tests for GET /v1/jobs/{job_id}/poll"""

    @pytest.mark.asyncio
    async def test_poll_job_status(self, async_client, db_session, mock_user, mock_redis):
        """Should return job status from Redis if available."""
        from ceq_api.models.workflow import Workflow

        workflow = Workflow(
            name="Test Workflow",
            description="Test",
            workflow_json={"test": "data"},
            input_schema={},
            user_id=mock_user.id,
        )
        db_session.add(workflow)
        await db_session.flush()

        job = Job(
            workflow_id=workflow.id,
            user_id=mock_user.id,
            status=JobStatus.RUNNING.value,
            progress=0.5,
            input_params={},
            queued_at=datetime.now(UTC),
        )
        db_session.add(job)
        await db_session.commit()

        # Patch get_redis at module level since it's called directly
        with patch("ceq_api.routers.jobs.get_redis", return_value=mock_redis):
            response = await async_client.get(f"/v1/jobs/{job.id}/poll")

        assert response.status_code == status.HTTP_200_OK


class TestCancelJob:
    """Tests for DELETE /v1/jobs/{job_id}"""

    def test_cancel_job_not_found(self, client):
        """Should return 404 for non-existent job."""
        fake_id = uuid4()
        response = client.delete(f"/v1/jobs/{fake_id}")

        assert response.status_code == status.HTTP_404_NOT_FOUND

    @pytest.mark.asyncio
    async def test_cancel_job_success(self, async_client, db_session, mock_user, mock_redis):
        """Should cancel a queued job."""
        from ceq_api.models.workflow import Workflow

        workflow = Workflow(
            name="Test Workflow",
            description="Test",
            workflow_json={"test": "data"},
            input_schema={},
            user_id=mock_user.id,
        )
        db_session.add(workflow)
        await db_session.flush()

        job = Job(
            workflow_id=workflow.id,
            user_id=mock_user.id,
            status=JobStatus.QUEUED.value,
            progress=0.0,
            input_params={},
            queued_at=datetime.now(UTC),
        )
        db_session.add(job)
        await db_session.commit()
        queued_payload = json.dumps({"id": str(job.id), "input": {"job_id": str(job.id)}})
        mock_redis.lrange.return_value = [queued_payload]

        # Patch Redis functions at module level since they're called directly
        with patch("ceq_api.routers.jobs.get_redis", return_value=mock_redis), \
             patch("ceq_api.routers.jobs.publish_job_update", new_callable=AsyncMock):
            response = await async_client.delete(f"/v1/jobs/{job.id}")

        assert response.status_code == status.HTTP_204_NO_CONTENT

        # Verify job was cancelled - refetch from database to get updated state
        from sqlalchemy import select
        result = await db_session.execute(select(Job).where(Job.id == job.id))
        updated_job = result.scalar_one()
        assert updated_job.status == JobStatus.CANCELLED.value
        mock_redis.lrem.assert_any_call("ceq:jobs:pending", 0, queued_payload)
        mock_redis.hset.assert_any_call(
            f"ceq:job:{job.id}",
            mapping={
                "status": JobStatus.CANCELLED.value,
                "progress": "0.0",
                "cancel_requested": "true",
            },
        )
        control_calls = [
            call
            for call in mock_redis.publish.call_args_list
            if call.args[0] == f"ceq:job:{job.id}:control"
        ]
        assert control_calls
        control_payload = json.loads(control_calls[0].args[1])
        assert control_payload["action"] == "cancel"
        assert control_payload["job_id"] == str(job.id)

    @pytest.mark.asyncio
    async def test_cancel_job_refunds_gpu_job_credit_debit(
        self,
        async_client,
        db_session,
        mock_user,
        mock_redis,
        monkeypatch,
    ):
        """Cancelling a metered GPU job refunds the submission debit once."""
        from sqlalchemy import select

        from ceq_api.models import CreditLedgerEntry, CreditLedgerType
        from ceq_api.models.workflow import Workflow
        from ceq_api.routers import jobs as jobs_router

        monkeypatch.setattr(jobs_router.settings, "gpu_job_credit_debits_enabled", True)

        workflow = Workflow(
            name="Metered Workflow",
            description="Test",
            workflow_json={"test": "data"},
            input_schema={},
            user_id=mock_user.id,
        )
        db_session.add(workflow)
        await db_session.flush()

        job = Job(
            workflow_id=workflow.id,
            user_id=mock_user.id,
            status=JobStatus.QUEUED.value,
            progress=0.0,
            input_params={},
            queued_at=datetime.now(UTC),
        )
        db_session.add(job)
        await db_session.flush()
        db_session.add(
            CreditLedgerEntry(
                user_id=mock_user.id,
                org_id=mock_user.org_id,
                job_id=job.id,
                amount=-25,
                transaction_type=CreditLedgerType.DEBIT.value,
                reason="gpu-job:social",
                idempotency_key=f"gpu-job:{job.id}:debit",
                ledger_metadata={},
            )
        )
        await db_session.flush()

        with patch("ceq_api.routers.jobs.get_redis", return_value=mock_redis), \
             patch("ceq_api.routers.jobs.publish_job_update", new_callable=AsyncMock):
            response = await async_client.delete(f"/v1/jobs/{job.id}")

        assert response.status_code == status.HTTP_204_NO_CONTENT
        result = await db_session.execute(
            select(CreditLedgerEntry).where(
                CreditLedgerEntry.transaction_type == CreditLedgerType.REFUND.value
            )
        )
        refund = result.scalar_one()
        assert refund.amount == 25
        assert refund.job_id == job.id
        assert refund.idempotency_key == f"gpu-job:{job.id}:refund"

    @pytest.mark.asyncio
    async def test_cancel_running_job_does_not_reset_progress(self, async_client, db_session, mock_user, mock_redis):
        """Canceling running jobs should preserve observed progress."""
        from ceq_api.models.workflow import Workflow

        workflow = Workflow(
            name="Test Workflow",
            description="Test",
            workflow_json={"test": "data"},
            input_schema={},
            user_id=mock_user.id,
        )
        db_session.add(workflow)
        await db_session.flush()

        job = Job(
            workflow_id=workflow.id,
            user_id=mock_user.id,
            status=JobStatus.RUNNING.value,
            progress=0.72,
            input_params={},
            queued_at=datetime.now(UTC),
            started_at=datetime.now(UTC),
        )
        db_session.add(job)
        await db_session.commit()
        mock_redis.lrange.return_value = []

        with patch("ceq_api.routers.jobs.get_redis", return_value=mock_redis), \
             patch("ceq_api.routers.jobs.publish_job_update", new_callable=AsyncMock):
            response = await async_client.delete(f"/v1/jobs/{job.id}")

        assert response.status_code == status.HTTP_204_NO_CONTENT

        from sqlalchemy import select
        result = await db_session.execute(select(Job).where(Job.id == job.id))
        updated_job = result.scalar_one()
        assert updated_job.status == JobStatus.CANCELLED.value
        assert updated_job.progress == 0.72
        assert updated_job.completed_at is None
        assert updated_job.output_metadata["cancel_requested_from_status"] == JobStatus.RUNNING.value
        mock_redis.hset.assert_any_call(
            f"ceq:job:{job.id}",
            mapping={
                "status": JobStatus.CANCELLED.value,
                "progress": "0.72",
                "cancel_requested": "true",
            },
        )

    @pytest.mark.asyncio
    async def test_cancel_job_already_completed(self, async_client, db_session, mock_user):
        """Should not allow cancelling completed job."""
        from ceq_api.models.workflow import Workflow

        workflow = Workflow(
            name="Test Workflow",
            description="Test",
            workflow_json={"test": "data"},
            input_schema={},
            user_id=mock_user.id,
        )
        db_session.add(workflow)
        await db_session.flush()

        job = Job(
            workflow_id=workflow.id,
            user_id=mock_user.id,
            status=JobStatus.COMPLETED.value,
            progress=1.0,
            input_params={},
            queued_at=datetime.now(UTC),
            completed_at=datetime.now(UTC),
        )
        db_session.add(job)
        await db_session.commit()

        response = await async_client.delete(f"/v1/jobs/{job.id}")

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "Cannot cancel" in response.json()["detail"]


class TestJobCompletionReport:
    """Tests for POST /v1/jobs/{job_id}/outputs/report"""

    class FakeWebhookClient:
        """Capture outbound webhook delivery attempts."""

        calls: list[dict] = []
        responses: list[httpx.Response | Exception] = []

        def __init__(self, timeout):
            self.timeout = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def post(self, url, content, headers):
            self.__class__.calls.append(
                {
                    "url": url,
                    "content": content,
                    "headers": headers,
                    "timeout": self.timeout,
                }
            )
            response = self.__class__.responses.pop(0)
            if isinstance(response, Exception):
                raise response
            return response

    @staticmethod
    def _configure_webhook(monkeypatch, jobs_router, responses):
        from ceq_api.services import job_webhooks

        monkeypatch.setattr(jobs_router.settings, "job_webhook_secret", "webhook-secret")
        monkeypatch.setattr(jobs_router.settings, "job_webhook_max_attempts", 3)
        monkeypatch.setattr(jobs_router.settings, "job_webhook_retry_backoff_seconds", 0.0)
        monkeypatch.setattr(jobs_router.settings, "job_webhook_timeout_seconds", 2.0)
        monkeypatch.setattr(job_webhooks, "get_settings", lambda: jobs_router.settings)
        TestJobCompletionReport.FakeWebhookClient.calls = []
        TestJobCompletionReport.FakeWebhookClient.responses = list(responses)
        monkeypatch.setattr(
            job_webhooks.httpx,
            "AsyncClient",
            TestJobCompletionReport.FakeWebhookClient,
        )

        class FakeStorage:
            def get_public_url(self, storage_uri: str) -> str:
                return f"https://cdn.example.com/{storage_uri.rsplit('/', 1)[-1]}"

        async def fake_get_storage():
            return FakeStorage()

        monkeypatch.setattr(jobs_router, "get_storage", fake_get_storage)

    @pytest.mark.asyncio
    async def test_report_job_outputs_persists_completion(
        self,
        async_client,
        db_session,
        mock_user,
        monkeypatch,
    ):
        """Worker callback should persist final job status and outputs."""
        from sqlalchemy import select

        from ceq_api.models.output import Output
        from ceq_api.models.workflow import Workflow
        from ceq_api.routers import jobs as jobs_router

        monkeypatch.setattr(
            jobs_router.settings,
            "job_completion_callback_token",
            "test-token",
        )

        workflow = Workflow(
            name="Test Workflow",
            description="Test",
            workflow_json={"test": "data"},
            input_schema={},
            user_id=mock_user.id,
        )
        db_session.add(workflow)
        await db_session.flush()

        job = Job(
            workflow_id=workflow.id,
            user_id=mock_user.id,
            status=JobStatus.RUNNING.value,
            progress=0.5,
            input_params={},
            queued_at=datetime.now(UTC),
        )
        db_session.add(job)
        await db_session.commit()

        payload = {
            "status": "completed",
            "outputs": [
                {
                    "filename": "output.png",
                    "storage_uri": "r2://ceq-assets/outputs/job/output.png",
                    "file_type": "image/png",
                    "file_size_bytes": 1024,
                    "width": 512,
                    "height": 512,
                    "preview_url": "https://cdn.example.com/output.png",
                    "metadata": {"seed": 42},
                }
            ],
            "metadata": {"vram_peak_gb": 12.5},
            "worker_id": "worker-a",
            "gpu_seconds": 4.2,
        }

        response = await async_client.post(
            f"/v1/jobs/{job.id}/outputs/report",
            headers={"X-CEQ-Worker-Token": "test-token"},
            json=payload,
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.json()["outputs_persisted"] == 1

        job_result = await db_session.execute(select(Job).where(Job.id == job.id))
        updated_job = job_result.scalar_one()
        assert updated_job.status == JobStatus.COMPLETED.value
        assert updated_job.progress == 1.0
        assert updated_job.worker_id == "worker-a"

        output_result = await db_session.execute(
            select(Output).where(Output.job_id == job.id)
        )
        output = output_result.scalar_one()
        assert output.filename == "output.png"
        assert output.file_type == "image/png"
        assert output.file_size_bytes == 1024
        assert output.preview_url == "https://cdn.example.com/output.png"

    @pytest.mark.asyncio
    async def test_report_job_outputs_delivers_signed_webhook(
        self,
        async_client,
        db_session,
        mock_user,
        monkeypatch,
    ):
        """Terminal worker callbacks should deliver signed user webhooks."""
        from sqlalchemy import select

        from ceq_api.models.workflow import Workflow
        from ceq_api.routers import jobs as jobs_router

        monkeypatch.setattr(
            jobs_router.settings,
            "job_completion_callback_token",
            "test-token",
        )
        self._configure_webhook(monkeypatch, jobs_router, [httpx.Response(204)])

        workflow = Workflow(
            name="Test Workflow",
            description="Test",
            workflow_json={"test": "data"},
            input_schema={},
            user_id=mock_user.id,
        )
        db_session.add(workflow)
        await db_session.flush()

        job = Job(
            workflow_id=workflow.id,
            user_id=mock_user.id,
            status=JobStatus.RUNNING.value,
            progress=0.5,
            input_params={"prompt": "test"},
            queued_at=datetime.now(UTC),
            webhook_url="https://hooks.example.com/ceq",
        )
        db_session.add(job)
        await db_session.commit()

        response = await async_client.post(
            f"/v1/jobs/{job.id}/outputs/report",
            headers={"X-CEQ-Worker-Token": "test-token"},
            json={
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
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.json()["outputs_persisted"] == 1
        assert len(self.FakeWebhookClient.calls) == 1

        call = self.FakeWebhookClient.calls[0]
        assert call["url"] == "https://hooks.example.com/ceq"
        assert call["headers"]["X-CEQ-Event"] == "job.completed"
        assert call["headers"]["X-CEQ-Job-ID"] == str(job.id)
        expected_signature = hmac.new(
            b"webhook-secret",
            call["content"],
            hashlib.sha256,
        ).hexdigest()
        assert call["headers"]["X-CEQ-Signature"] == f"sha256={expected_signature}"

        payload = json.loads(call["content"])
        assert payload["event"] == "job.completed"
        assert payload["job"]["id"] == str(job.id)
        assert payload["job"]["input_params"] == {"prompt": "test"}
        assert payload["outputs"][0]["public_url"] == "https://cdn.example.com/output.png"

        job_result = await db_session.execute(select(Job).where(Job.id == job.id))
        updated_job = job_result.scalar_one()
        delivery = updated_job.output_metadata["webhook_delivery"]
        assert delivery["status"] == "delivered"
        assert delivery["attempts"] == 1
        assert delivery["last_status_code"] == 204

    @pytest.mark.asyncio
    async def test_report_job_outputs_retries_retryable_webhook_failure(
        self,
        async_client,
        db_session,
        mock_user,
        monkeypatch,
    ):
        """5xx webhook responses should retry before recording success."""
        from sqlalchemy import select

        from ceq_api.models.workflow import Workflow
        from ceq_api.routers import jobs as jobs_router

        monkeypatch.setattr(
            jobs_router.settings,
            "job_completion_callback_token",
            "test-token",
        )
        monkeypatch.setattr(jobs_router.settings, "job_webhook_max_attempts", 2)
        self._configure_webhook(
            monkeypatch,
            jobs_router,
            [httpx.Response(500, text="temporary"), httpx.Response(200)],
        )
        monkeypatch.setattr(jobs_router.settings, "job_webhook_max_attempts", 2)

        workflow = Workflow(
            name="Test Workflow",
            description="Test",
            workflow_json={"test": "data"},
            input_schema={},
            user_id=mock_user.id,
        )
        db_session.add(workflow)
        await db_session.flush()

        job = Job(
            workflow_id=workflow.id,
            user_id=mock_user.id,
            status=JobStatus.RUNNING.value,
            progress=0.5,
            input_params={},
            queued_at=datetime.now(UTC),
            webhook_url="https://hooks.example.com/ceq",
        )
        db_session.add(job)
        await db_session.commit()

        response = await async_client.post(
            f"/v1/jobs/{job.id}/outputs/report",
            headers={"X-CEQ-Worker-Token": "test-token"},
            json={"status": "completed", "outputs": []},
        )

        assert response.status_code == status.HTTP_200_OK
        assert len(self.FakeWebhookClient.calls) == 2
        job_result = await db_session.execute(select(Job).where(Job.id == job.id))
        delivery = job_result.scalar_one().output_metadata["webhook_delivery"]
        assert delivery["status"] == "delivered"
        assert delivery["attempts"] == 2

    @pytest.mark.asyncio
    async def test_report_job_outputs_records_permanent_webhook_failure(
        self,
        async_client,
        db_session,
        mock_user,
        monkeypatch,
    ):
        """Permanent 4xx webhook responses should not retry."""
        from sqlalchemy import select

        from ceq_api.models.workflow import Workflow
        from ceq_api.routers import jobs as jobs_router

        monkeypatch.setattr(
            jobs_router.settings,
            "job_completion_callback_token",
            "test-token",
        )
        self._configure_webhook(
            monkeypatch,
            jobs_router,
            [httpx.Response(410, text="gone"), httpx.Response(200)],
        )

        workflow = Workflow(
            name="Test Workflow",
            description="Test",
            workflow_json={"test": "data"},
            input_schema={},
            user_id=mock_user.id,
        )
        db_session.add(workflow)
        await db_session.flush()

        job = Job(
            workflow_id=workflow.id,
            user_id=mock_user.id,
            status=JobStatus.RUNNING.value,
            progress=0.5,
            input_params={},
            queued_at=datetime.now(UTC),
            webhook_url="https://hooks.example.com/ceq",
        )
        db_session.add(job)
        await db_session.commit()

        response = await async_client.post(
            f"/v1/jobs/{job.id}/outputs/report",
            headers={"X-CEQ-Worker-Token": "test-token"},
            json={"status": "failed", "error": "executor failed", "outputs": []},
        )

        assert response.status_code == status.HTTP_200_OK
        assert len(self.FakeWebhookClient.calls) == 1
        job_result = await db_session.execute(select(Job).where(Job.id == job.id))
        delivery = job_result.scalar_one().output_metadata["webhook_delivery"]
        assert delivery["status"] == "failed"
        assert delivery["attempts"] == 1
        assert delivery["last_status_code"] == 410
        assert delivery["last_error"] == "gone"

    @pytest.mark.asyncio
    async def test_report_job_outputs_refunds_failed_gpu_job_debit(
        self,
        async_client,
        db_session,
        mock_user,
        monkeypatch,
    ):
        """Worker failure reports refund a previously debited GPU job."""
        from sqlalchemy import select

        from ceq_api.models import CreditLedgerEntry, CreditLedgerType
        from ceq_api.models.workflow import Workflow
        from ceq_api.routers import jobs as jobs_router

        monkeypatch.setattr(
            jobs_router.settings,
            "job_completion_callback_token",
            "test-token",
        )
        monkeypatch.setattr(jobs_router.settings, "gpu_job_credit_debits_enabled", True)

        workflow = Workflow(
            name="Metered Failed Workflow",
            description="Test",
            workflow_json={"test": "data"},
            input_schema={},
            user_id=mock_user.id,
        )
        db_session.add(workflow)
        await db_session.flush()

        job = Job(
            workflow_id=workflow.id,
            user_id=mock_user.id,
            status=JobStatus.RUNNING.value,
            progress=0.5,
            input_params={},
            queued_at=datetime.now(UTC),
        )
        db_session.add(job)
        await db_session.flush()
        db_session.add(
            CreditLedgerEntry(
                user_id=mock_user.id,
                org_id=mock_user.org_id,
                job_id=job.id,
                amount=-25,
                transaction_type=CreditLedgerType.DEBIT.value,
                reason="gpu-job:social",
                idempotency_key=f"gpu-job:{job.id}:debit",
                ledger_metadata={},
            )
        )
        await db_session.flush()

        response = await async_client.post(
            f"/v1/jobs/{job.id}/outputs/report",
            headers={"X-CEQ-Worker-Token": "test-token"},
            json={"status": "failed", "error": "executor failed", "outputs": []},
        )

        assert response.status_code == status.HTTP_200_OK
        result = await db_session.execute(
            select(CreditLedgerEntry).where(
                CreditLedgerEntry.transaction_type == CreditLedgerType.REFUND.value
            )
        )
        refund = result.scalar_one()
        assert refund.amount == 25
        assert refund.job_id == job.id
        assert refund.idempotency_key == f"gpu-job:{job.id}:refund"

    @pytest.mark.asyncio
    async def test_report_job_outputs_skips_webhook_without_signing_secret(
        self,
        async_client,
        db_session,
        mock_user,
        monkeypatch,
    ):
        """Webhook URLs should not be delivered unsigned."""
        from sqlalchemy import select

        from ceq_api.models.workflow import Workflow
        from ceq_api.routers import jobs as jobs_router
        from ceq_api.services import job_webhooks

        monkeypatch.setattr(
            jobs_router.settings,
            "job_completion_callback_token",
            "test-token",
        )
        monkeypatch.setattr(jobs_router.settings, "job_webhook_secret", "")
        monkeypatch.setattr(job_webhooks, "get_settings", lambda: jobs_router.settings)
        self.FakeWebhookClient.calls = []
        self.FakeWebhookClient.responses = [httpx.Response(204)]
        monkeypatch.setattr(job_webhooks.httpx, "AsyncClient", self.FakeWebhookClient)

        workflow = Workflow(
            name="Test Workflow",
            description="Test",
            workflow_json={"test": "data"},
            input_schema={},
            user_id=mock_user.id,
        )
        db_session.add(workflow)
        await db_session.flush()

        job = Job(
            workflow_id=workflow.id,
            user_id=mock_user.id,
            status=JobStatus.RUNNING.value,
            progress=0.5,
            input_params={},
            queued_at=datetime.now(UTC),
            webhook_url="https://hooks.example.com/ceq",
        )
        db_session.add(job)
        await db_session.commit()

        response = await async_client.post(
            f"/v1/jobs/{job.id}/outputs/report",
            headers={"X-CEQ-Worker-Token": "test-token"},
            json={"status": "completed", "outputs": []},
        )

        assert response.status_code == status.HTTP_200_OK
        assert self.FakeWebhookClient.calls == []
        job_result = await db_session.execute(select(Job).where(Job.id == job.id))
        delivery = job_result.scalar_one().output_metadata["webhook_delivery"]
        assert delivery["status"] == "skipped"
        assert "JOB_WEBHOOK_SECRET" in delivery["last_error"]

    @pytest.mark.asyncio
    async def test_report_job_outputs_records_webhook_transport_failure(
        self,
        async_client,
        db_session,
        mock_user,
        monkeypatch,
    ):
        """Webhook transport errors should retry and persist failure metadata."""
        from sqlalchemy import select

        from ceq_api.models.workflow import Workflow
        from ceq_api.routers import jobs as jobs_router

        monkeypatch.setattr(
            jobs_router.settings,
            "job_completion_callback_token",
            "test-token",
        )
        self._configure_webhook(
            monkeypatch,
            jobs_router,
            [httpx.ConnectTimeout("timed out"), httpx.ConnectTimeout("timed out")],
        )
        monkeypatch.setattr(jobs_router.settings, "job_webhook_max_attempts", 2)

        workflow = Workflow(
            name="Test Workflow",
            description="Test",
            workflow_json={"test": "data"},
            input_schema={},
            user_id=mock_user.id,
        )
        db_session.add(workflow)
        await db_session.flush()

        job = Job(
            workflow_id=workflow.id,
            user_id=mock_user.id,
            status=JobStatus.RUNNING.value,
            progress=0.5,
            input_params={},
            queued_at=datetime.now(UTC),
            webhook_url="https://hooks.example.com/ceq",
        )
        db_session.add(job)
        await db_session.commit()

        response = await async_client.post(
            f"/v1/jobs/{job.id}/outputs/report",
            headers={"X-CEQ-Worker-Token": "test-token"},
            json={"status": "completed", "outputs": []},
        )

        assert response.status_code == status.HTTP_200_OK
        assert len(self.FakeWebhookClient.calls) == 2
        job_result = await db_session.execute(select(Job).where(Job.id == job.id))
        delivery = job_result.scalar_one().output_metadata["webhook_delivery"]
        assert delivery["status"] == "failed"
        assert delivery["attempts"] == 2
        assert "timed out" in delivery["last_error"]

    @pytest.mark.asyncio
    async def test_report_job_outputs_is_idempotent(
        self,
        async_client,
        db_session,
        mock_user,
        monkeypatch,
    ):
        """Repeated callback for the same storage URI should update, not duplicate."""
        from sqlalchemy import select

        from ceq_api.models.output import Output
        from ceq_api.models.workflow import Workflow
        from ceq_api.routers import jobs as jobs_router

        monkeypatch.setattr(
            jobs_router.settings,
            "job_completion_callback_token",
            "test-token",
        )

        workflow = Workflow(
            name="Test Workflow",
            description="Test",
            workflow_json={"test": "data"},
            input_schema={},
            user_id=mock_user.id,
        )
        db_session.add(workflow)
        await db_session.flush()

        job = Job(
            workflow_id=workflow.id,
            user_id=mock_user.id,
            status=JobStatus.RUNNING.value,
            progress=0.5,
            input_params={},
            queued_at=datetime.now(UTC),
        )
        db_session.add(job)
        await db_session.commit()

        payload = {
            "status": "completed",
            "outputs": [
                {
                    "filename": "output.png",
                    "storage_uri": "r2://ceq-assets/outputs/job/output.png",
                    "file_type": "image/png",
                    "file_size_bytes": 1024,
                }
            ],
        }

        for _ in range(2):
            response = await async_client.post(
                f"/v1/jobs/{job.id}/outputs/report",
                headers={"X-CEQ-Worker-Token": "test-token"},
                json=payload,
            )
            assert response.status_code == status.HTTP_200_OK

        output_result = await db_session.execute(
            select(Output).where(Output.job_id == job.id)
        )
        assert len(output_result.scalars().all()) == 1

    @pytest.mark.asyncio
    async def test_report_job_outputs_does_not_override_cancelled_job(
        self,
        async_client,
        db_session,
        mock_user,
        monkeypatch,
    ):
        """Late worker success reports should not overwrite API-side cancellation."""
        from sqlalchemy import select

        from ceq_api.models.output import Output
        from ceq_api.models.workflow import Workflow
        from ceq_api.routers import jobs as jobs_router

        monkeypatch.setattr(
            jobs_router.settings,
            "job_completion_callback_token",
            "test-token",
        )

        workflow = Workflow(
            name="Test Workflow",
            description="Test",
            workflow_json={"test": "data"},
            input_schema={},
            user_id=mock_user.id,
        )
        db_session.add(workflow)
        await db_session.flush()

        job = Job(
            workflow_id=workflow.id,
            user_id=mock_user.id,
            status=JobStatus.CANCELLED.value,
            progress=0.0,
            input_params={},
            queued_at=datetime.now(UTC),
            completed_at=datetime.now(UTC),
        )
        db_session.add(job)
        await db_session.commit()

        response = await async_client.post(
            f"/v1/jobs/{job.id}/outputs/report",
            headers={"X-CEQ-Worker-Token": "test-token"},
            json={
                "status": "completed",
                "outputs": [
                    {
                        "filename": "late.png",
                        "storage_uri": "r2://ceq-assets/outputs/job/late.png",
                        "file_type": "image/png",
                        "file_size_bytes": 1024,
                    }
                ],
            },
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.json()["status"] == JobStatus.CANCELLED.value
        assert response.json()["outputs_persisted"] == 0

        job_result = await db_session.execute(select(Job).where(Job.id == job.id))
        updated_job = job_result.scalar_one()
        assert updated_job.status == JobStatus.CANCELLED.value
        assert updated_job.output_metadata["ignored_worker_report_after_cancel"]["status"] == "completed"

        output_result = await db_session.execute(select(Output).where(Output.job_id == job.id))
        assert output_result.scalars().all() == []

    @pytest.mark.asyncio
    async def test_report_job_outputs_rejects_invalid_token(
        self,
        async_client,
        db_session,
        mock_user,
        monkeypatch,
    ):
        """Worker callback should require the shared token."""
        from ceq_api.models.workflow import Workflow
        from ceq_api.routers import jobs as jobs_router

        monkeypatch.setattr(
            jobs_router.settings,
            "job_completion_callback_token",
            "test-token",
        )

        workflow = Workflow(
            name="Test Workflow",
            description="Test",
            workflow_json={"test": "data"},
            input_schema={},
            user_id=mock_user.id,
        )
        db_session.add(workflow)
        await db_session.flush()

        job = Job(
            workflow_id=workflow.id,
            user_id=mock_user.id,
            status=JobStatus.RUNNING.value,
            progress=0.5,
            input_params={},
            queued_at=datetime.now(UTC),
        )
        db_session.add(job)
        await db_session.commit()

        response = await async_client.post(
            f"/v1/jobs/{job.id}/outputs/report",
            headers={"X-CEQ-Worker-Token": "wrong-token"},
            json={"status": "completed", "outputs": []},
        )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED


class TestListJobOutputs:
    """Tests for GET /v1/jobs/{job_id}/outputs"""

    def test_list_outputs_job_not_found(self, client):
        """Should return 404 for non-existent job."""
        fake_id = uuid4()
        response = client.get(f"/v1/jobs/{fake_id}/outputs")

        assert response.status_code == status.HTTP_404_NOT_FOUND

    @pytest.mark.asyncio
    async def test_list_outputs_empty(self, async_client, db_session, mock_user):
        """Should return empty list when no outputs exist."""
        from ceq_api.models.workflow import Workflow

        workflow = Workflow(
            name="Test Workflow",
            description="Test",
            workflow_json={"test": "data"},
            input_schema={},
            user_id=mock_user.id,
        )
        db_session.add(workflow)
        await db_session.flush()

        job = Job(
            workflow_id=workflow.id,
            user_id=mock_user.id,
            status=JobStatus.COMPLETED.value,
            progress=1.0,
            input_params={},
            queued_at=datetime.now(UTC),
        )
        db_session.add(job)
        await db_session.commit()

        response = await async_client.get(f"/v1/jobs/{job.id}/outputs")

        assert response.status_code == status.HTTP_200_OK
        assert response.json() == []

    @pytest.mark.asyncio
    async def test_list_outputs_with_data(self, async_client, db_session, mock_user):
        """Should return outputs for completed job."""
        from ceq_api.models.output import Output
        from ceq_api.models.workflow import Workflow

        workflow = Workflow(
            name="Test Workflow",
            description="Test",
            workflow_json={"test": "data"},
            input_schema={},
            user_id=mock_user.id,
        )
        db_session.add(workflow)
        await db_session.flush()

        job = Job(
            workflow_id=workflow.id,
            user_id=mock_user.id,
            status=JobStatus.COMPLETED.value,
            progress=1.0,
            input_params={},
            queued_at=datetime.now(UTC),
        )
        db_session.add(job)
        await db_session.flush()

        output = Output(
            job_id=job.id,
            user_id=mock_user.id,
            filename="output.png",
            storage_uri="r2://bucket/output.png",
            file_type="image/png",
            file_size_bytes=1024,
            width=512,
            height=512,
            output_metadata={"seed": 99},
            published_to=[{"channel": "webhook", "url": "https://hooks.example.com", "published_at": "2026-05-14T00:00:02+00:00"}],
        )
        db_session.add(output)
        await db_session.commit()

        response = await async_client.get(f"/v1/jobs/{job.id}/outputs")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert len(data) == 1
        assert data[0]["filename"] == "output.png"
        assert data[0]["metadata"]["seed"] == 99
        assert data[0]["published_to"][0]["channel"] == "webhook"


class TestJobBrandMessages:
    """Tests for brand message generation."""

    def test_queued_message(self):
        """Queued status should have appropriate brand message."""
        from ceq_api.routers.jobs import STATUS_MESSAGES
        assert STATUS_MESSAGES["queued"] == "In the crucible..."

    def test_running_message(self):
        """Running status should have appropriate brand message."""
        from ceq_api.routers.jobs import STATUS_MESSAGES
        assert STATUS_MESSAGES["running"] == "Transmuting latent space..."

    def test_completed_message(self):
        """Completed status should have appropriate brand message."""
        from ceq_api.routers.jobs import STATUS_MESSAGES
        assert "Materialized" in STATUS_MESSAGES["completed"]

    def test_failed_message(self):
        """Failed status should have appropriate brand message."""
        from ceq_api.routers.jobs import STATUS_MESSAGES
        assert "Chaos" in STATUS_MESSAGES["failed"]

    def test_cancelled_message(self):
        """Cancelled status should have appropriate brand message."""
        from ceq_api.routers.jobs import STATUS_MESSAGES
        assert "Entropy" in STATUS_MESSAGES["cancelled"]
