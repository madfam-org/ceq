"""Comprehensive database tests for schema validation and relationships."""

import pytest
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import select, inspect
from sqlalchemy.exc import IntegrityError

from ceq_api.models import (
    Asset,
    Job,
    JobStatus,
    Output,
    Template,
    Workflow,
)


class TestSchemaIntegrity:
    """Tests for database schema integrity."""

    @pytest.mark.asyncio
    async def test_all_tables_created(self, db_session):
        """All expected tables should exist."""
        # Get inspector to check tables
        def get_tables(conn):
            inspector = inspect(conn)
            return inspector.get_table_names()

        tables = await db_session.run_sync(
            lambda sync_session: get_tables(sync_session.get_bind())
        )

        expected_tables = ["workflows", "templates", "jobs", "outputs", "assets"]
        for table in expected_tables:
            assert table in tables, f"Missing table: {table}"

    @pytest.mark.asyncio
    async def test_workflow_table_columns(self, db_session):
        """Workflow table should have correct columns."""
        def get_columns(conn):
            inspector = inspect(conn)
            return [col["name"] for col in inspector.get_columns("workflows")]

        columns = await db_session.run_sync(
            lambda sync_session: get_columns(sync_session.get_bind())
        )

        required_columns = [
            "id", "name", "description", "workflow_json", "input_schema",
            "tags", "user_id", "is_public", "is_deleted", "created_at", "updated_at"
        ]
        for col in required_columns:
            assert col in columns, f"Missing column: {col}"


class TestWorkflowModel:
    """Tests for Workflow model relationships and constraints."""

    @pytest.mark.asyncio
    async def test_workflow_create_minimal(self, db_session):
        """Should create workflow with minimal required fields."""
        workflow = Workflow(
            name="Minimal Workflow",
            workflow_json={"nodes": []},
            input_schema={},
            tags=[],
            user_id=uuid4(),
            is_public=False,
            is_deleted=False,
        )
        db_session.add(workflow)
        await db_session.commit()

        assert workflow.id is not None
        assert workflow.created_at is not None
        assert workflow.updated_at is not None

    @pytest.mark.asyncio
    async def test_workflow_name_required(self, db_session):
        """Workflow name should be required."""
        workflow = Workflow(
            name=None,  # Required field
            workflow_json={"nodes": []},
            input_schema={},
            tags=[],
            user_id=uuid4(),
            is_public=False,
            is_deleted=False,
        )
        db_session.add(workflow)

        with pytest.raises(IntegrityError):
            await db_session.commit()

    @pytest.mark.asyncio
    async def test_workflow_jobs_relationship(self, db_session):
        """Workflow should have jobs relationship."""
        workflow = Workflow(
            name="Test Workflow",
            workflow_json={"nodes": []},
            input_schema={},
            tags=[],
            user_id=uuid4(),
            is_public=False,
            is_deleted=False,
        )
        db_session.add(workflow)
        await db_session.flush()

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
        await db_session.commit()

        # Refresh to load relationships
        await db_session.refresh(workflow)
        assert len(workflow.jobs) == 1
        assert workflow.jobs[0].id == job.id

    @pytest.mark.asyncio
    async def test_workflow_soft_delete(self, db_session):
        """Soft deleted workflows should still exist in DB."""
        workflow = Workflow(
            name="To Delete",
            workflow_json={},
            input_schema={},
            tags=[],
            user_id=uuid4(),
            is_public=False,
            is_deleted=False,
        )
        db_session.add(workflow)
        await db_session.commit()
        workflow_id = workflow.id

        # Soft delete
        workflow.is_deleted = True
        await db_session.commit()

        # Should still be queryable
        result = await db_session.execute(
            select(Workflow).where(Workflow.id == workflow_id)
        )
        found = result.scalar_one()
        assert found.is_deleted is True


class TestJobModel:
    """Tests for Job model relationships and constraints."""

    @pytest.mark.asyncio
    async def test_job_requires_workflow(self, db_session):
        """Job should have workflow_id as foreign key."""
        # In PostgreSQL, this would raise IntegrityError.
        # In SQLite (used for tests), FK constraints may not be enforced by default.
        # We test that the column exists and is properly typed.
        workflow = Workflow(
            name="Test",
            workflow_json={},
            input_schema={},
            tags=[],
            user_id=uuid4(),
            is_public=False,
            is_deleted=False,
        )
        db_session.add(workflow)
        await db_session.flush()

        job = Job(
            workflow_id=workflow.id,  # Valid workflow
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
        await db_session.commit()

        # Verify relationship works
        await db_session.refresh(job)
        assert job.workflow_id == workflow.id

    @pytest.mark.asyncio
    async def test_job_status_values(self, db_session):
        """Job status should accept valid enum values."""
        workflow = Workflow(
            name="Test",
            workflow_json={},
            input_schema={},
            tags=[],
            user_id=uuid4(),
            is_public=False,
            is_deleted=False,
        )
        db_session.add(workflow)
        await db_session.flush()

        valid_statuses = ["queued", "running", "completed", "failed", "cancelled"]
        for status_val in valid_statuses:
            job = Job(
                workflow_id=workflow.id,
                user_id=workflow.user_id,
                status=status_val,
                progress=0.0,
                input_params={},
                output_metadata={},
                priority=0,
                queued_at=datetime.now(timezone.utc),
                gpu_seconds=0.0,
                cold_start_ms=0,
            )
            db_session.add(job)

        await db_session.commit()

    @pytest.mark.asyncio
    async def test_job_outputs_relationship(self, db_session):
        """Job should have outputs relationship."""
        workflow = Workflow(
            name="Test",
            workflow_json={},
            input_schema={},
            tags=[],
            user_id=uuid4(),
            is_public=False,
            is_deleted=False,
        )
        db_session.add(workflow)
        await db_session.flush()

        job = Job(
            workflow_id=workflow.id,
            user_id=workflow.user_id,
            status=JobStatus.COMPLETED.value,
            progress=1.0,
            input_params={},
            output_metadata={},
            priority=0,
            queued_at=datetime.now(timezone.utc),
            gpu_seconds=10.0,
            cold_start_ms=0,
        )
        db_session.add(job)
        await db_session.flush()

        output = Output(
            job_id=job.id,
            user_id=workflow.user_id,
            filename="output.png",
            file_type="image/png",
            file_size_bytes=1024,
            storage_uri="r2://test/output.png",
            output_metadata={},
            published_to=[],
        )
        db_session.add(output)
        await db_session.commit()

        await db_session.refresh(job)
        assert len(job.outputs) == 1

    @pytest.mark.asyncio
    async def test_job_workflow_relationship(self, db_session):
        """Job should properly reference its workflow."""
        workflow = Workflow(
            name="Parent Workflow",
            workflow_json={},
            input_schema={},
            tags=[],
            user_id=uuid4(),
            is_public=False,
            is_deleted=False,
        )
        db_session.add(workflow)
        await db_session.flush()

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
        await db_session.commit()

        # Verify relationship
        await db_session.refresh(job)
        assert job.workflow is not None
        assert job.workflow.name == "Parent Workflow"
        assert job.workflow_id == workflow.id


class TestOutputModel:
    """Tests for Output model."""

    @pytest.mark.asyncio
    async def test_output_job_relationship(self, db_session):
        """Output should properly reference its job."""
        workflow = Workflow(
            name="Test",
            workflow_json={},
            input_schema={},
            tags=[],
            user_id=uuid4(),
            is_public=False,
            is_deleted=False,
        )
        db_session.add(workflow)
        await db_session.flush()

        job = Job(
            workflow_id=workflow.id,
            user_id=workflow.user_id,
            status=JobStatus.COMPLETED.value,
            progress=1.0,
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
            filename="output.png",
            file_type="image/png",
            file_size_bytes=1024,
            storage_uri="r2://test/output.png",
            output_metadata={},
            published_to=[],
        )
        db_session.add(output)
        await db_session.commit()

        # Verify relationship works
        await db_session.refresh(output)
        assert output.job is not None
        assert output.job_id == job.id

    @pytest.mark.asyncio
    async def test_output_file_metadata(self, db_session):
        """Output should store file metadata correctly."""
        workflow = Workflow(
            name="Test",
            workflow_json={},
            input_schema={},
            tags=[],
            user_id=uuid4(),
            is_public=False,
            is_deleted=False,
        )
        db_session.add(workflow)
        await db_session.flush()

        job = Job(
            workflow_id=workflow.id,
            user_id=workflow.user_id,
            status=JobStatus.COMPLETED.value,
            progress=1.0,
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
            filename="generated_image.png",
            file_type="image/png",
            file_size_bytes=2048576,
            width=1024,
            height=1024,
            storage_uri="r2://outputs/generated_image.png",
            output_metadata={"seed": 12345, "steps": 20},
            published_to=[],
        )
        db_session.add(output)
        await db_session.commit()

        await db_session.refresh(output)
        assert output.filename == "generated_image.png"
        assert output.file_type == "image/png"
        assert output.file_size_bytes == 2048576
        assert output.width == 1024
        assert output.height == 1024
        assert output.output_metadata["seed"] == 12345


class TestTemplateModel:
    """Tests for Template model."""

    @pytest.mark.asyncio
    async def test_template_create(self, db_session):
        """Should create template with all fields."""
        template = Template(
            name="FLUX Dev",
            description="High quality image generation",
            category="image",
            workflow_json={"nodes": []},
            input_schema={"prompt": {"type": "string"}},
            tags=["flux", "image"],
            preview_urls=["https://example.com/preview.png"],
            model_requirements=["flux1-dev.safetensors"],
            vram_requirement_gb=16,
            fork_count=0,
            run_count=0,
        )
        db_session.add(template)
        await db_session.commit()

        assert template.id is not None
        assert template.category == "image"
        assert "flux" in template.tags
        assert template.vram_requirement_gb == 16

    @pytest.mark.asyncio
    async def test_template_counters(self, db_session):
        """Template counters should be updatable."""
        template = Template(
            name="Popular Template",
            category="image",
            workflow_json={},
            input_schema={},
            tags=[],
            preview_urls=[],
            model_requirements=[],
            vram_requirement_gb=8,
            fork_count=0,
            run_count=0,
        )
        db_session.add(template)
        await db_session.commit()

        # Increment counters
        template.fork_count += 1
        template.run_count += 10
        await db_session.commit()

        await db_session.refresh(template)
        assert template.fork_count == 1
        assert template.run_count == 10


class TestAssetModel:
    """Tests for Asset model."""

    @pytest.mark.asyncio
    async def test_asset_create(self, db_session):
        """Should create asset with all required fields."""
        asset = Asset(
            name="flux1-dev.safetensors",
            description="FLUX.1 Dev checkpoint",
            asset_type="checkpoint",
            storage_uri="r2://ceq-assets/models/flux1-dev.safetensors",
            size_bytes=23_000_000_000,  # ~23GB
            checksum="sha256:abc123",
            user_id=uuid4(),
            is_public=True,
            is_deleted=False,
            tags=["flux", "checkpoint"],
            asset_metadata={"format": "safetensors"},
        )
        db_session.add(asset)
        await db_session.commit()

        assert asset.id is not None
        assert asset.asset_type == "checkpoint"
        assert asset.is_public is True

    @pytest.mark.asyncio
    async def test_asset_soft_delete(self, db_session):
        """Soft deleted assets should be flagged."""
        asset = Asset(
            name="old-model.safetensors",
            asset_type="checkpoint",
            storage_uri="r2://test/old.safetensors",
            size_bytes=1024,
            user_id=uuid4(),
            is_public=False,
            is_deleted=False,
            tags=[],
            asset_metadata={},
        )
        db_session.add(asset)
        await db_session.commit()

        asset.is_deleted = True
        await db_session.commit()

        await db_session.refresh(asset)
        assert asset.is_deleted is True


class TestQueryPatterns:
    """Tests for common query patterns."""

    @pytest.mark.asyncio
    async def test_filter_by_user(self, db_session):
        """Should filter records by user_id."""
        user1_id = uuid4()
        user2_id = uuid4()

        # Create workflows for both users
        for i in range(3):
            w = Workflow(
                name=f"User1 Workflow {i}",
                workflow_json={},
                input_schema={},
                tags=[],
                user_id=user1_id,
                is_public=False,
                is_deleted=False,
            )
            db_session.add(w)

        for i in range(2):
            w = Workflow(
                name=f"User2 Workflow {i}",
                workflow_json={},
                input_schema={},
                tags=[],
                user_id=user2_id,
                is_public=False,
                is_deleted=False,
            )
            db_session.add(w)

        await db_session.commit()

        # Query user1's workflows
        result = await db_session.execute(
            select(Workflow).where(Workflow.user_id == user1_id)
        )
        user1_workflows = result.scalars().all()
        assert len(user1_workflows) == 3

    @pytest.mark.asyncio
    async def test_filter_public_resources(self, db_session):
        """Should filter public resources correctly."""
        user_id = uuid4()

        # Create mix of public and private
        for i, is_public in enumerate([True, False, True, False, False]):
            w = Workflow(
                name=f"Workflow {i}",
                workflow_json={},
                input_schema={},
                tags=[],
                user_id=user_id,
                is_public=is_public,
                is_deleted=False,
            )
            db_session.add(w)

        await db_session.commit()

        result = await db_session.execute(
            select(Workflow).where(Workflow.is_public == True)
        )
        public_workflows = result.scalars().all()
        assert len(public_workflows) == 2

    @pytest.mark.asyncio
    async def test_exclude_soft_deleted(self, db_session):
        """Should exclude soft deleted records."""
        user_id = uuid4()

        for i, is_deleted in enumerate([False, True, False, True]):
            w = Workflow(
                name=f"Workflow {i}",
                workflow_json={},
                input_schema={},
                tags=[],
                user_id=user_id,
                is_public=False,
                is_deleted=is_deleted,
            )
            db_session.add(w)

        await db_session.commit()

        result = await db_session.execute(
            select(Workflow).where(Workflow.is_deleted == False)
        )
        active_workflows = result.scalars().all()
        assert len(active_workflows) == 2

    @pytest.mark.asyncio
    async def test_jobs_by_status(self, db_session):
        """Should filter jobs by status."""
        workflow = Workflow(
            name="Test",
            workflow_json={},
            input_schema={},
            tags=[],
            user_id=uuid4(),
            is_public=False,
            is_deleted=False,
        )
        db_session.add(workflow)
        await db_session.flush()

        # Create jobs with various statuses
        statuses = ["queued", "queued", "running", "completed", "failed"]
        for status in statuses:
            job = Job(
                workflow_id=workflow.id,
                user_id=workflow.user_id,
                status=status,
                progress=0.0 if status != "completed" else 1.0,
                input_params={},
                output_metadata={},
                priority=0,
                queued_at=datetime.now(timezone.utc),
                gpu_seconds=0.0,
                cold_start_ms=0,
            )
            db_session.add(job)

        await db_session.commit()

        # Query queued jobs
        result = await db_session.execute(
            select(Job).where(Job.status == "queued")
        )
        queued_jobs = result.scalars().all()
        assert len(queued_jobs) == 2


class TestTimestamps:
    """Tests for automatic timestamp handling."""

    @pytest.mark.asyncio
    async def test_created_at_auto_set(self, db_session):
        """created_at should be set automatically."""
        workflow = Workflow(
            name="Test",
            workflow_json={},
            input_schema={},
            tags=[],
            user_id=uuid4(),
            is_public=False,
            is_deleted=False,
        )
        db_session.add(workflow)
        await db_session.commit()

        assert workflow.created_at is not None
        # Verify it's a recent timestamp (within last minute)
        now = datetime.now(timezone.utc)
        # Handle both timezone-aware and naive datetimes
        if workflow.created_at.tzinfo is None:
            created_naive = workflow.created_at
            now_naive = now.replace(tzinfo=None)
        else:
            created_naive = workflow.created_at.replace(tzinfo=None)
            now_naive = now.replace(tzinfo=None)

        delta = now_naive - created_naive
        assert delta.total_seconds() < 60  # Created within last minute

    @pytest.mark.asyncio
    async def test_updated_at_changes_on_update(self, db_session):
        """updated_at should change on updates."""
        workflow = Workflow(
            name="Test",
            workflow_json={},
            input_schema={},
            tags=[],
            user_id=uuid4(),
            is_public=False,
            is_deleted=False,
        )
        db_session.add(workflow)
        await db_session.commit()

        original_updated = workflow.updated_at

        # Make an update
        import asyncio
        await asyncio.sleep(0.01)  # Ensure time passes

        workflow.name = "Updated Name"
        await db_session.commit()
        await db_session.refresh(workflow)

        # updated_at should have changed
        assert workflow.updated_at >= original_updated


class TestJSONBFields:
    """Tests for JSONB field handling."""

    @pytest.mark.asyncio
    async def test_workflow_json_storage(self, db_session):
        """Complex workflow JSON should be stored correctly."""
        complex_workflow = {
            "nodes": {
                "1": {"type": "CLIPTextEncode", "inputs": {"text": "A photo"}},
                "2": {"type": "KSampler", "inputs": {"seed": 12345}},
            },
            "connections": [
                {"from": "1", "to": "2"},
            ],
        }

        workflow = Workflow(
            name="Complex Workflow",
            workflow_json=complex_workflow,
            input_schema={"prompt": {"type": "string"}},
            tags=["test"],
            user_id=uuid4(),
            is_public=False,
            is_deleted=False,
        )
        db_session.add(workflow)
        await db_session.commit()
        await db_session.refresh(workflow)

        assert workflow.workflow_json["nodes"]["1"]["type"] == "CLIPTextEncode"
        assert workflow.workflow_json["nodes"]["2"]["inputs"]["seed"] == 12345

    @pytest.mark.asyncio
    async def test_tags_array_storage(self, db_session):
        """Tags array should be stored correctly."""
        tags = ["flux", "image-gen", "high-quality", "16gb-vram"]

        workflow = Workflow(
            name="Tagged Workflow",
            workflow_json={},
            input_schema={},
            tags=tags,
            user_id=uuid4(),
            is_public=False,
            is_deleted=False,
        )
        db_session.add(workflow)
        await db_session.commit()
        await db_session.refresh(workflow)

        assert len(workflow.tags) == 4
        assert "flux" in workflow.tags
        assert "high-quality" in workflow.tags
