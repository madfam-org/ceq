"""Tests for output management endpoints."""

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from fastapi import status

from ceq_api.models.job import Job, JobStatus
from ceq_api.models.output import Output
from ceq_api.models.workflow import Workflow


class TestOutputModel:
    """Tests for Output model."""

    @pytest.mark.asyncio
    async def test_create_output(self, db_session, mock_user):
        """Should create output with all fields."""
        # Create workflow and job first
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
            filename="generated_image.png",
            storage_uri="r2://ceq-assets/outputs/generated_image.png",
            file_type="image/png",
            file_size_bytes=1024 * 512,  # 512KB
            width=1024,
            height=1024,
        )
        db_session.add(output)
        await db_session.commit()

        assert output.id is not None
        assert output.filename == "generated_image.png"
        assert output.width == 1024
        assert output.height == 1024

    @pytest.mark.asyncio
    async def test_create_video_output(self, db_session, mock_user):
        """Should create video output with duration."""
        workflow = Workflow(
            name="Video Workflow",
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
            filename="generated_video.mp4",
            storage_uri="r2://ceq-assets/outputs/generated_video.mp4",
            file_type="video/mp4",
            file_size_bytes=1024 * 1024 * 50,  # 50MB
            width=1920,
            height=1080,
            duration_seconds=10.5,
        )
        db_session.add(output)
        await db_session.commit()

        assert output.duration_seconds == 10.5
        assert output.file_type == "video/mp4"


class TestOutputRetrieval:
    """Tests for retrieving outputs."""

    @pytest.mark.asyncio
    async def test_get_outputs_by_job(self, async_client, db_session, mock_user):
        """Should retrieve all outputs for a job."""
        # Create workflow and job
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

        # Create multiple outputs
        for i in range(3):
            output = Output(
                job_id=job.id,
                user_id=mock_user.id,
                filename=f"output_{i}.png",
                storage_uri=f"r2://ceq-assets/outputs/output_{i}.png",
                file_type="image/png",
                file_size_bytes=1024 * (i + 1),
                width=512,
                height=512,
            )
            db_session.add(output)

        await db_session.commit()

        response = await async_client.get(f"/v1/jobs/{job.id}/outputs")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert len(data) == 3

    @pytest.mark.asyncio
    async def test_outputs_include_preview_url(self, async_client, db_session, mock_user):
        """Outputs should include preview URL if available."""
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
            storage_uri="r2://ceq-assets/outputs/output.png",
            file_type="image/png",
            file_size_bytes=1024,
            width=512,
            height=512,
            preview_url="https://example.com/preview.jpg",
        )
        db_session.add(output)
        await db_session.commit()

        response = await async_client.get(f"/v1/jobs/{job.id}/outputs")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data[0]["preview_url"] == "https://example.com/preview.jpg"


class TestOutputAccessControl:
    """Tests for output access control."""

    @pytest.mark.asyncio
    async def test_cannot_access_other_users_outputs(self, async_client, db_session, mock_user):
        """Should not access outputs from another user's job."""
        other_user_id = uuid4()

        workflow = Workflow(
            name="Other's Workflow",
            description="Test",
            workflow_json={"test": "data"},
            input_schema={},
            user_id=other_user_id,
        )
        db_session.add(workflow)
        await db_session.flush()

        job = Job(
            workflow_id=workflow.id,
            user_id=other_user_id,
            status=JobStatus.COMPLETED.value,
            progress=1.0,
            input_params={},
            queued_at=datetime.now(timezone.utc),
        )
        db_session.add(job)
        await db_session.flush()

        output = Output(
            job_id=job.id,
            user_id=other_user_id,
            filename="secret_output.png",
            storage_uri="r2://ceq-assets/outputs/secret.png",
            file_type="image/png",
            file_size_bytes=1024,
            width=512,
            height=512,
        )
        db_session.add(output)
        await db_session.commit()

        response = await async_client.get(f"/v1/jobs/{job.id}/outputs")

        assert response.status_code == status.HTTP_403_FORBIDDEN


class TestOutputTypes:
    """Tests for different output types."""

    @pytest.mark.asyncio
    async def test_image_output_fields(self, db_session, mock_user):
        """Image outputs should have width and height."""
        workflow = Workflow(
            name="Test",
            description="Test",
            workflow_json={},
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
            filename="image.png",
            storage_uri="r2://bucket/image.png",
            file_type="image/png",
            file_size_bytes=1024,
            width=2048,
            height=2048,
        )
        db_session.add(output)
        await db_session.commit()

        assert output.width == 2048
        assert output.height == 2048
        assert output.duration_seconds is None

    @pytest.mark.asyncio
    async def test_video_output_fields(self, db_session, mock_user):
        """Video outputs should have duration."""
        workflow = Workflow(
            name="Test",
            description="Test",
            workflow_json={},
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
            filename="video.mp4",
            storage_uri="r2://bucket/video.mp4",
            file_type="video/mp4",
            file_size_bytes=1024 * 1024 * 100,
            width=1920,
            height=1080,
            duration_seconds=30.0,
        )
        db_session.add(output)
        await db_session.commit()

        assert output.duration_seconds == 30.0
        assert output.file_type == "video/mp4"

    @pytest.mark.asyncio
    async def test_3d_model_output(self, db_session, mock_user):
        """3D model outputs should work without dimensions."""
        workflow = Workflow(
            name="Test",
            description="Test",
            workflow_json={},
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
            filename="model.glb",
            storage_uri="r2://bucket/model.glb",
            file_type="model/gltf-binary",
            file_size_bytes=1024 * 1024 * 5,
            width=None,
            height=None,
        )
        db_session.add(output)
        await db_session.commit()

        assert output.file_type == "model/gltf-binary"
        assert output.width is None
        assert output.height is None
