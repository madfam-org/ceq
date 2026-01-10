"""Tests for workflow endpoints."""

import pytest
from uuid import uuid4

import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from ceq_api.models import Workflow


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
        assert workflow.is_deleted == True

    @pytest.mark.asyncio
    async def test_create_workflow_validation(self, async_client: AsyncClient):
        """Test workflow creation validation."""
        # Missing required fields
        response = await async_client.post(
            "/v1/workflows/",
            json={"description": "No name"},
        )
        assert response.status_code == 422
