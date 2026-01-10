"""Tests for SQLAlchemy models."""

import pytest
from datetime import datetime, timezone
from uuid import uuid4

from ceq_api.models import (
    Asset,
    Job,
    JobStatus,
    Output,
    Template,
    Workflow,
)


class TestWorkflowModel:
    """Test Workflow model."""

    @pytest.mark.asyncio
    async def test_create_workflow(self, db_session, sample_workflow_json, sample_input_schema):
        """Test creating a workflow in database."""
        workflow = Workflow(
            name="Test Workflow",
            description="Test description",
            workflow_json=sample_workflow_json,
            input_schema=sample_input_schema,
            tags=["test"],
            user_id=uuid4(),
            is_public=False,
            is_deleted=False,
        )
        db_session.add(workflow)
        await db_session.flush()

        assert workflow.name == "Test Workflow"
        assert workflow.is_deleted == False
        assert workflow.tags == ["test"]
        assert workflow.id is not None

    @pytest.mark.asyncio
    async def test_workflow_defaults(self, db_session, sample_workflow_json):
        """Test workflow default values when saved to database."""
        workflow = Workflow(
            name="Minimal",
            workflow_json=sample_workflow_json,
            input_schema={},
            tags=[],
            user_id=uuid4(),
            is_public=False,
            is_deleted=False,
        )
        db_session.add(workflow)
        await db_session.flush()

        assert workflow.input_schema == {}
        assert workflow.tags == []
        assert workflow.is_public == False
        assert workflow.is_deleted == False


class TestTemplateModel:
    """Test Template model."""

    @pytest.mark.asyncio
    async def test_create_template(self, db_session, sample_workflow_json, sample_input_schema):
        """Test creating a template in database."""
        template = Template(
            name="Test Template",
            description="Test description",
            category="utility",
            workflow_json=sample_workflow_json,
            input_schema=sample_input_schema,
            tags=["test"],
            vram_requirement_gb=16,
            model_requirements=[],
            preview_urls=[],
            fork_count=0,
            run_count=0,
        )
        db_session.add(template)
        await db_session.flush()

        assert template.name == "Test Template"
        assert template.category == "utility"
        assert template.fork_count == 0
        assert template.run_count == 0

    @pytest.mark.asyncio
    async def test_template_defaults(self, db_session, sample_workflow_json, sample_input_schema):
        """Test template default values."""
        template = Template(
            name="Minimal",
            category="utility",
            workflow_json=sample_workflow_json,
            input_schema=sample_input_schema,
            tags=[],
            preview_urls=[],
            model_requirements=[],
            vram_requirement_gb=16,
            fork_count=0,
            run_count=0,
        )
        db_session.add(template)
        await db_session.flush()

        assert template.tags == []
        assert template.preview_urls == []
        assert template.model_requirements == []
        assert template.vram_requirement_gb == 16


class TestJobModel:
    """Test Job model."""

    @pytest.mark.asyncio
    async def test_create_job(self, db_session, sample_workflow_json):
        """Test creating a job in database."""
        # First create a workflow
        workflow = Workflow(
            name="Test Workflow",
            workflow_json=sample_workflow_json,
            input_schema={},
            tags=[],
            user_id=uuid4(),
            is_public=False,
            is_deleted=False,
        )
        db_session.add(workflow)
        await db_session.flush()

        now = datetime.now(timezone.utc)
        job = Job(
            workflow_id=workflow.id,
            user_id=workflow.user_id,
            status=JobStatus.QUEUED.value,
            progress=0.0,
            input_params={"prompt": "test"},
            output_metadata={},
            priority=0,
            queued_at=now,
            gpu_seconds=0.0,
            cold_start_ms=0,
        )
        db_session.add(job)
        await db_session.flush()

        assert job.status == "queued"
        assert job.progress == 0.0
        assert job.gpu_seconds == 0.0
        assert job.id is not None

    def test_job_status_enum(self):
        """Test JobStatus enum values."""
        assert JobStatus.QUEUED.value == "queued"
        assert JobStatus.RUNNING.value == "running"
        assert JobStatus.COMPLETED.value == "completed"
        assert JobStatus.FAILED.value == "failed"
        assert JobStatus.CANCELLED.value == "cancelled"


class TestOutputModel:
    """Test Output model."""

    @pytest.mark.asyncio
    async def test_create_output(self, db_session, sample_workflow_json):
        """Test creating an output in database."""
        # Create workflow first
        workflow = Workflow(
            name="Test Workflow",
            workflow_json=sample_workflow_json,
            input_schema={},
            tags=[],
            user_id=uuid4(),
            is_public=False,
            is_deleted=False,
        )
        db_session.add(workflow)
        await db_session.flush()

        # Create job
        job = Job(
            workflow_id=workflow.id,
            user_id=workflow.user_id,
            status=JobStatus.QUEUED.value,
            progress=0.0,
            input_params={},
            output_metadata={},
            priority=0,
            queued_at=datetime.now(timezone.utc),
            gpu_seconds=0.0,
            cold_start_ms=0,
        )
        db_session.add(job)
        await db_session.flush()

        # Create output
        output = Output(
            job_id=job.id,
            user_id=workflow.user_id,
            filename="output.png",
            file_type="image/png",
            file_size_bytes=1024,
            storage_uri="r2://ceq-assets/outputs/test.png",
            output_metadata={"width": 1024, "height": 1024},
            published_to=[],
        )
        db_session.add(output)
        await db_session.flush()

        assert output.file_type == "image/png"
        assert output.published_to == []

    @pytest.mark.asyncio
    async def test_output_defaults(self, db_session, sample_workflow_json):
        """Test output default values."""
        # Create workflow first
        workflow = Workflow(
            name="Test Workflow",
            workflow_json=sample_workflow_json,
            input_schema={},
            tags=[],
            user_id=uuid4(),
            is_public=False,
            is_deleted=False,
        )
        db_session.add(workflow)
        await db_session.flush()

        # Create job
        job = Job(
            workflow_id=workflow.id,
            user_id=workflow.user_id,
            status=JobStatus.QUEUED.value,
            progress=0.0,
            input_params={},
            output_metadata={},
            priority=0,
            queued_at=datetime.now(timezone.utc),
            gpu_seconds=0.0,
            cold_start_ms=0,
        )
        db_session.add(job)
        await db_session.flush()

        output = Output(
            job_id=job.id,
            user_id=workflow.user_id,
            filename="test.png",
            file_type="image/png",
            file_size_bytes=1024,
            storage_uri="r2://test",
            output_metadata={},
            published_to=[],
        )
        db_session.add(output)
        await db_session.flush()

        assert output.output_metadata == {}
        assert output.published_to == []
        assert output.preview_url is None


class TestAssetModel:
    """Test Asset model."""

    @pytest.mark.asyncio
    async def test_create_asset(self, db_session):
        """Test creating an asset in database."""
        asset = Asset(
            name="test-model.safetensors",
            asset_type="checkpoint",
            storage_uri="r2://ceq-assets/models/test.safetensors",
            size_bytes=1024 * 1024 * 1024,
            user_id=uuid4(),
            is_public=False,
            is_deleted=False,
            tags=[],
            asset_metadata={},
        )
        db_session.add(asset)
        await db_session.flush()

        assert asset.name == "test-model.safetensors"
        assert asset.asset_type == "checkpoint"
        assert asset.is_public == False
        assert asset.is_deleted == False

    def test_asset_types(self):
        """Test valid asset types can be set."""
        valid_types = ["checkpoint", "lora", "vae", "embedding", "controlnet"]
        for asset_type in valid_types:
            asset = Asset(
                name=f"test-{asset_type}",
                asset_type=asset_type,
                storage_uri="r2://test",
                size_bytes=1024,
                user_id=uuid4(),
                is_public=False,
                is_deleted=False,
                tags=[],
                asset_metadata={},
            )
            assert asset.asset_type == asset_type
