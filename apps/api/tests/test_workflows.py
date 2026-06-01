"""Tests for workflow endpoints."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import status
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from ceq_api.auth import get_current_user
from ceq_api.auth.janua import JanuaUser
from ceq_api.models import Job, Template, Workflow


class TestWorkflowEndpoints:
    """Test workflow CRUD endpoints."""

    @pytest.mark.asyncio
    async def test_create_workflow(
        self,
        async_client: AsyncClient,
        sample_workflow_data: dict,
    ):
        """Test creating a new workflow."""
        response = await async_client.post(
            "/v1/workflows/",
            json=sample_workflow_data,
        )
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == sample_workflow_data["name"]
        assert "id" in data

    @pytest.mark.asyncio
    async def test_list_workflows(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        mock_user,
        sample_workflow_json,
    ):
        """Test listing workflows."""
        # Create a workflow first
        workflow = Workflow(
            name="Test List",
            workflow_json=sample_workflow_json,
            user_id=mock_user.id,
        )
        db_session.add(workflow)
        await db_session.flush()

        response = await async_client.get("/v1/workflows/")
        assert response.status_code == 200
        data = response.json()
        assert "workflows" in data
        assert "total" in data

    @pytest.mark.asyncio
    async def test_get_workflow(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        mock_user,
        sample_workflow_json,
    ):
        """Test getting a specific workflow."""
        # Create a workflow
        workflow = Workflow(
            name="Test Get",
            workflow_json=sample_workflow_json,
            user_id=mock_user.id,
        )
        db_session.add(workflow)
        await db_session.flush()
        await db_session.refresh(workflow)

        response = await async_client.get(f"/v1/workflows/{workflow.id}")
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Test Get"

    @pytest.mark.asyncio
    async def test_get_workflow_not_found(self, async_client: AsyncClient):
        """Test getting non-existent workflow."""
        fake_id = uuid4()
        response = await async_client.get(f"/v1/workflows/{fake_id}")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_update_workflow(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        mock_user,
        sample_workflow_json,
    ):
        """Test updating a workflow."""
        # Create a workflow
        workflow = Workflow(
            name="Before Update",
            workflow_json=sample_workflow_json,
            user_id=mock_user.id,
        )
        db_session.add(workflow)
        await db_session.flush()
        await db_session.refresh(workflow)

        response = await async_client.put(
            f"/v1/workflows/{workflow.id}",
            json={"name": "After Update"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "After Update"

    @pytest.mark.asyncio
    async def test_delete_workflow(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        mock_user,
        sample_workflow_json,
    ):
        """Test deleting a workflow (soft delete)."""
        # Create a workflow
        workflow = Workflow(
            name="To Delete",
            workflow_json=sample_workflow_json,
            user_id=mock_user.id,
        )
        db_session.add(workflow)
        await db_session.flush()
        await db_session.refresh(workflow)

        response = await async_client.delete(f"/v1/workflows/{workflow.id}")
        assert response.status_code == 204

        # Verify it's soft deleted
        await db_session.refresh(workflow)
        assert workflow.is_deleted

    @pytest.mark.asyncio
    async def test_create_workflow_validation(self, async_client: AsyncClient):
        """Test workflow creation validation."""
        # Missing required fields
        response = await async_client.post(
            "/v1/workflows/",
            json={"description": "No name"},
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_run_workflow_from_premium_template_requires_paid_role(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        mock_user,
        sample_workflow_json,
        sample_input_schema,
    ):
        """Fork-then-run cannot bypass premium template entitlements."""
        template = Template(
            name="Premium Origin",
            category="utility",
            workflow_json=sample_workflow_json,
            input_schema=sample_input_schema,
            tags=["premium"],
        )
        db_session.add(template)
        await db_session.flush()
        await db_session.refresh(template)

        workflow = Workflow(
            name="Forked Premium Workflow",
            workflow_json=sample_workflow_json,
            input_schema=sample_input_schema,
            tags=["premium"],
            user_id=mock_user.id,
            org_id=mock_user.org_id,
            template_id=template.id,
        )
        db_session.add(workflow)
        await db_session.flush()
        await db_session.refresh(workflow)

        response = await async_client.post(
            f"/v1/workflows/{workflow.id}/run",
            json={"params": {"prompt": "bypass attempt"}},
        )

        assert response.status_code == status.HTTP_402_PAYMENT_REQUIRED
        assert response.json()["detail"]["required_entitlement"] == "paid_template"

    @pytest.mark.asyncio
    async def test_run_workflow_respects_active_job_quota(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        mock_user,
        monkeypatch,
        sample_workflow_json,
        sample_input_schema,
    ):
        """Workflow execution must stop before users exceed active job quota."""
        from ceq_api.routers import workflows as workflows_router

        monkeypatch.setattr(workflows_router.settings, "max_active_jobs_per_user", 1)

        workflow = Workflow(
            name="Quota Workflow",
            workflow_json=sample_workflow_json,
            input_schema=sample_input_schema,
            user_id=mock_user.id,
            org_id=mock_user.org_id,
        )
        db_session.add(workflow)
        await db_session.flush()
        await db_session.refresh(workflow)

        db_session.add(
            Job(
                workflow_id=workflow.id,
                user_id=mock_user.id,
                status="queued",
                input_params={},
                queued_at=datetime.now(UTC),
            )
        )
        await db_session.flush()

        response = await async_client.post(
            f"/v1/workflows/{workflow.id}/run",
            json={"params": {"prompt": "over quota"}},
        )

        assert response.status_code == status.HTTP_429_TOO_MANY_REQUESTS
        assert response.json()["detail"]["active_jobs"] == 1

    @pytest.mark.asyncio
    async def test_run_workflow_uses_studio_active_job_quota(
        self,
        app,
        async_client: AsyncClient,
        db_session: AsyncSession,
        mock_user,
        monkeypatch,
        sample_workflow_json,
        sample_input_schema,
    ):
        """Studio plan roles use the Studio active-job cap."""
        from ceq_api.routers import workflows as workflows_router

        studio_user = JanuaUser(
            id=mock_user.id,
            email=mock_user.email,
            org_id=mock_user.org_id,
            roles=["user", "studio"],
        )

        async def override_studio_user():
            return studio_user

        app.dependency_overrides[get_current_user] = override_studio_user
        monkeypatch.setattr(workflows_router.settings, "max_active_jobs_per_user", 1)
        monkeypatch.setattr(workflows_router.settings, "max_active_jobs_pro", 2)
        monkeypatch.setattr(workflows_router.settings, "max_active_jobs_studio", 3)
        monkeypatch.setattr(workflows_router, "enqueue_job", AsyncMock())

        workflow = Workflow(
            name="Studio Quota Workflow",
            workflow_json=sample_workflow_json,
            input_schema=sample_input_schema,
            user_id=mock_user.id,
            org_id=mock_user.org_id,
        )
        db_session.add(workflow)
        await db_session.flush()
        await db_session.refresh(workflow)

        now = datetime.now(UTC)
        db_session.add_all(
            [
                Job(
                    workflow_id=workflow.id,
                    user_id=mock_user.id,
                    status="queued",
                    input_params={},
                    queued_at=now,
                ),
                Job(
                    workflow_id=workflow.id,
                    user_id=mock_user.id,
                    status="running",
                    input_params={},
                    queued_at=now,
                ),
            ]
        )
        await db_session.flush()

        response = await async_client.post(
            f"/v1/workflows/{workflow.id}/run",
            json={"params": {"prompt": "within studio quota"}},
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.json()["status"] == "queued"

    @pytest.mark.asyncio
    async def test_paid_role_can_run_workflow_from_premium_template(
        self,
        app,
        async_client: AsyncClient,
        db_session: AsyncSession,
        mock_user,
        monkeypatch,
        sample_workflow_json,
        sample_input_schema,
    ):
        """Paid roles preserve access to workflows derived from premium templates."""
        from ceq_api.routers import workflows as workflows_router

        paid_user = JanuaUser(
            id=mock_user.id,
            email=mock_user.email,
            org_id=mock_user.org_id,
            roles=["user", "studio"],
        )

        async def override_paid_user():
            return paid_user

        app.dependency_overrides[get_current_user] = override_paid_user
        monkeypatch.setattr(workflows_router, "enqueue_job", AsyncMock())

        template = Template(
            name="Studio Origin",
            category="utility",
            workflow_json=sample_workflow_json,
            input_schema=sample_input_schema,
            tags=["premium"],
        )
        db_session.add(template)
        await db_session.flush()
        await db_session.refresh(template)

        workflow = Workflow(
            name="Studio Workflow",
            workflow_json=sample_workflow_json,
            input_schema=sample_input_schema,
            tags=["premium"],
            user_id=mock_user.id,
            org_id=mock_user.org_id,
            template_id=template.id,
        )
        db_session.add(workflow)
        await db_session.flush()
        await db_session.refresh(workflow)

        response = await async_client.post(
            f"/v1/workflows/{workflow.id}/run",
            json={"params": {"prompt": "paid access"}},
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.json()["status"] == "queued"
