"""Tests for job management endpoints."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import status

from ceq_api.models.job import Job, JobStatus


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
            queued_at=datetime.now(timezone.utc),
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
            queued_at=datetime.now(timezone.utc),
        )
        db_session.add(job)
        await db_session.commit()

        response = await async_client.get(f"/v1/jobs/{job.id}")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["status"] == "running"
        assert data["progress"] == 0.5
        assert data["current_node"] == "KSampler"
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
            queued_at=datetime.now(timezone.utc),
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
            queued_at=datetime.now(timezone.utc),
        )
        db_session.add(job)
        await db_session.commit()

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
            queued_at=datetime.now(timezone.utc),
        )
        db_session.add(job)
        await db_session.commit()

        response = await async_client.delete(f"/v1/jobs/{job.id}")

        assert response.status_code == status.HTTP_204_NO_CONTENT

        # Verify job was cancelled
        await db_session.refresh(job)
        assert job.status == JobStatus.CANCELLED.value

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
            queued_at=datetime.now(timezone.utc),
            completed_at=datetime.now(timezone.utc),
        )
        db_session.add(job)
        await db_session.commit()

        response = await async_client.delete(f"/v1/jobs/{job.id}")

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "Cannot cancel" in response.json()["detail"]


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
            queued_at=datetime.now(timezone.utc),
        )
        db_session.add(job)
        await db_session.commit()

        response = await async_client.get(f"/v1/jobs/{job.id}/outputs")

        assert response.status_code == status.HTTP_200_OK
        assert response.json() == []

    @pytest.mark.asyncio
    async def test_list_outputs_with_data(self, async_client, db_session, mock_user):
        """Should return outputs for completed job."""
        from ceq_api.models.workflow import Workflow
        from ceq_api.models.output import Output

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
            queued_at=datetime.now(timezone.utc),
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
        )
        db_session.add(output)
        await db_session.commit()

        response = await async_client.get(f"/v1/jobs/{job.id}/outputs")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert len(data) == 1
        assert data[0]["filename"] == "output.png"


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
