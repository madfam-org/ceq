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

    def test_create_workflow(self, sample_workflow_json, sample_input_schema):
        """Test creating a workflow."""
        workflow = Workflow(
            name="Test Workflow",
            description="Test description",
            workflow_json=sample_workflow_json,
            input_schema=sample_input_schema,
            tags=["test"],
            user_id=uuid4(),
            is_public=False,
        )
        assert workflow.name == "Test Workflow"
        assert workflow.is_deleted == False
        assert workflow.tags == ["test"]

    def test_workflow_defaults(self, sample_workflow_json):
        """Test workflow default values."""
        workflow = Workflow(
            name="Minimal",
            workflow_json=sample_workflow_json,
            user_id=uuid4(),
        )
        assert workflow.input_schema == {}
        assert workflow.tags == []
        assert workflow.is_public == False
        assert workflow.is_deleted == False


class TestTemplateModel:
    """Test Template model."""

    def test_create_template(self, sample_workflow_json, sample_input_schema):
        """Test creating a template."""
        template = Template(
            name="Test Template",
            description="Test description",
            category="utility",
            workflow_json=sample_workflow_json,
            input_schema=sample_input_schema,
            tags=["test"],
            vram_requirement_gb=16,
        )
        assert template.name == "Test Template"
        assert template.category == "utility"
        assert template.fork_count == 0
        assert template.run_count == 0

    def test_template_defaults(self, sample_workflow_json, sample_input_schema):
        """Test template default values."""
        template = Template(
            name="Minimal",
            category="utility",
            workflow_json=sample_workflow_json,
            input_schema=sample_input_schema,
        )
        assert template.tags == []
        assert template.preview_urls == []
        assert template.model_requirements == []
        assert template.vram_requirement_gb == 16


class TestJobModel:
    """Test Job model."""

    def test_create_job(self):
        """Test creating a job."""
        now = datetime.now(timezone.utc)
        job = Job(
            workflow_id=uuid4(),
            user_id=uuid4(),
            status=JobStatus.QUEUED.value,
            input_params={"prompt": "test"},
            queued_at=now,
        )
        assert job.status == "queued"
        assert job.progress == 0.0
        assert job.gpu_seconds == 0.0

    def test_job_status_enum(self):
        """Test JobStatus enum values."""
        assert JobStatus.QUEUED.value == "queued"
        assert JobStatus.RUNNING.value == "running"
        assert JobStatus.COMPLETED.value == "completed"
        assert JobStatus.FAILED.value == "failed"
        assert JobStatus.CANCELLED.value == "cancelled"


class TestOutputModel:
    """Test Output model."""

    def test_create_output(self):
        """Test creating an output."""
        output = Output(
            job_id=uuid4(),
            user_id=uuid4(),
            output_type="image",
            storage_uri="r2://ceq-assets/outputs/test.png",
            output_metadata={"width": 1024, "height": 1024},
        )
        assert output.output_type == "image"
        assert output.published_to == []

    def test_output_defaults(self):
        """Test output default values."""
        output = Output(
            job_id=uuid4(),
            user_id=uuid4(),
            output_type="image",
            storage_uri="r2://test",
        )
        assert output.output_metadata == {}
        assert output.published_to == []
        assert output.thumbnail_uri is None


class TestAssetModel:
    """Test Asset model."""

    def test_create_asset(self):
        """Test creating an asset."""
        asset = Asset(
            name="test-model.safetensors",
            asset_type="checkpoint",
            storage_uri="r2://ceq-assets/models/test.safetensors",
            size_bytes=1024 * 1024 * 1024,  # 1GB
            user_id=uuid4(),
        )
        assert asset.name == "test-model.safetensors"
        assert asset.asset_type == "checkpoint"
        assert asset.is_public == False
        assert asset.is_deleted == False

    def test_asset_types(self):
        """Test valid asset types."""
        valid_types = ["checkpoint", "lora", "vae", "embedding", "controlnet"]
        for asset_type in valid_types:
            asset = Asset(
                name=f"test-{asset_type}",
                asset_type=asset_type,
                storage_uri="r2://test",
                size_bytes=1024,
                user_id=uuid4(),
            )
            assert asset.asset_type == asset_type
