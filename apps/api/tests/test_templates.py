"""Tests for template endpoints."""

import pytest
from uuid import uuid4

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from ceq_api.models import Template, Workflow


class TestTemplateEndpoints:
    """Test template endpoints."""

    @pytest.mark.asyncio
    async def test_list_templates(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        sample_workflow_json,
        sample_input_schema,
    ):
        """Test listing templates."""
        # Create a template
        template = Template(
            name="Test Template",
            category="utility",
            workflow_json=sample_workflow_json,
            input_schema=sample_input_schema,
        )
        db_session.add(template)
        await db_session.flush()

        response = await async_client.get("/v1/templates/")
        assert response.status_code == 200
        data = response.json()
        assert "templates" in data
        assert "total" in data

    @pytest.mark.asyncio
    async def test_list_templates_by_category(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        sample_workflow_json,
        sample_input_schema,
    ):
        """Test filtering templates by category."""
        # Create templates in different categories
        for category in ["social", "video", "utility"]:
            template = Template(
                name=f"Test {category}",
                category=category,
                workflow_json=sample_workflow_json,
                input_schema=sample_input_schema,
            )
            db_session.add(template)
        await db_session.flush()

        response = await async_client.get("/v1/templates/?category=utility")
        assert response.status_code == 200
        data = response.json()
        for template in data["templates"]:
            assert template["category"] == "utility"

    @pytest.mark.asyncio
    async def test_get_template(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        sample_workflow_json,
        sample_input_schema,
    ):
        """Test getting a specific template."""
        template = Template(
            name="Test Get",
            category="utility",
            workflow_json=sample_workflow_json,
            input_schema=sample_input_schema,
        )
        db_session.add(template)
        await db_session.flush()
        await db_session.refresh(template)

        response = await async_client.get(f"/v1/templates/{template.id}")
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Test Get"

    @pytest.mark.asyncio
    async def test_get_template_not_found(self, async_client: AsyncClient):
        """Test getting non-existent template."""
        fake_id = uuid4()
        response = await async_client.get(f"/v1/templates/{fake_id}")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_fork_template(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        mock_user,
        sample_workflow_json,
        sample_input_schema,
    ):
        """Test forking a template to create a workflow."""
        template = Template(
            name="Test Fork",
            category="utility",
            workflow_json=sample_workflow_json,
            input_schema=sample_input_schema,
        )
        db_session.add(template)
        await db_session.flush()
        await db_session.refresh(template)

        response = await async_client.post(
            f"/v1/templates/{template.id}/fork",
            json={"name": "My Forked Workflow"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "workflow_id" in data
        assert data["name"] == "My Forked Workflow"

        # Verify fork count incremented
        await db_session.refresh(template)
        assert template.fork_count == 1

    @pytest.mark.asyncio
    async def test_list_categories(self, async_client: AsyncClient):
        """Test listing template categories."""
        response = await async_client.get("/v1/templates/categories")
        assert response.status_code == 200
        data = response.json()
        assert "categories" in data
        categories = data["categories"]
        assert "social" in categories
        assert "video" in categories
        assert "3d" in categories
        assert "utility" in categories

    @pytest.mark.asyncio
    async def test_invalid_category_filter(self, async_client: AsyncClient):
        """Test filtering by invalid category."""
        response = await async_client.get("/v1/templates/?category=invalid")
        assert response.status_code == 400
