"""Tests for template endpoints."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import status
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from ceq_api.auth import get_current_user
from ceq_api.auth.janua import JanuaUser
from ceq_api.models import CreditLedgerEntry, CreditLedgerType, Job, Template, Workflow


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
    async def test_fork_premium_template_requires_paid_role(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        sample_workflow_json,
        sample_input_schema,
    ):
        """UI-only InterestGate must not be bypassable through direct API calls."""
        template = Template(
            name="Premium Fork",
            category="utility",
            workflow_json=sample_workflow_json,
            input_schema=sample_input_schema,
            tags=["premium"],
        )
        db_session.add(template)
        await db_session.flush()
        await db_session.refresh(template)

        response = await async_client.post(
            f"/v1/templates/{template.id}/fork",
            json={"name": "Bypass Attempt"},
        )

        assert response.status_code == status.HTTP_402_PAYMENT_REQUIRED
        assert response.json()["detail"]["required_entitlement"] == "paid_template"

    @pytest.mark.asyncio
    async def test_run_premium_template_requires_paid_role(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        sample_workflow_json,
        sample_input_schema,
    ):
        """Premium-tagged templates require API-side entitlement at run time."""
        template = Template(
            name="Premium Run",
            category="utility",
            workflow_json=sample_workflow_json,
            input_schema=sample_input_schema,
            tags=["pro"],
        )
        db_session.add(template)
        await db_session.flush()
        await db_session.refresh(template)

        response = await async_client.post(
            f"/v1/templates/{template.id}/run",
            json={"params": {"prompt": "commercial smoke"}},
        )

        assert response.status_code == status.HTTP_402_PAYMENT_REQUIRED
        assert response.json()["detail"]["template_id"] == str(template.id)

    @pytest.mark.asyncio
    async def test_run_template_respects_active_job_quota(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        mock_user,
        monkeypatch,
        sample_workflow_json,
        sample_input_schema,
    ):
        """Users cannot keep queueing GPU work after hitting active-job quota."""
        from ceq_api.routers import templates as templates_router

        monkeypatch.setattr(templates_router.settings, "max_active_jobs_per_user", 2)

        source_workflow = Workflow(
            name="Active Job Source",
            workflow_json=sample_workflow_json,
            input_schema=sample_input_schema,
            user_id=mock_user.id,
            org_id=mock_user.org_id,
        )
        template = Template(
            name="Quota Template",
            category="utility",
            workflow_json=sample_workflow_json,
            input_schema=sample_input_schema,
        )
        db_session.add_all([source_workflow, template])
        await db_session.flush()
        await db_session.refresh(source_workflow)
        await db_session.refresh(template)

        now = datetime.now(UTC)
        db_session.add_all(
            [
                Job(
                    workflow_id=source_workflow.id,
                    user_id=mock_user.id,
                    status="queued",
                    input_params={},
                    queued_at=now,
                ),
                Job(
                    workflow_id=source_workflow.id,
                    user_id=mock_user.id,
                    status="running",
                    input_params={},
                    queued_at=now,
                ),
            ]
        )
        await db_session.flush()

        response = await async_client.post(
            f"/v1/templates/{template.id}/run",
            json={"params": {"prompt": "over quota"}},
        )

        assert response.status_code == status.HTTP_429_TOO_MANY_REQUESTS
        assert response.json()["detail"]["max_active_jobs"] == 2

    @pytest.mark.asyncio
    async def test_run_template_uses_plan_aware_active_job_quota(
        self,
        app,
        async_client: AsyncClient,
        db_session: AsyncSession,
        mock_user,
        monkeypatch,
        sample_workflow_json,
        sample_input_schema,
    ):
        """Paid roles use their higher active-job cap instead of the free cap."""
        from ceq_api.routers import templates as templates_router

        paid_user = JanuaUser(
            id=mock_user.id,
            email=mock_user.email,
            org_id=mock_user.org_id,
            roles=["user", "pro"],
        )

        async def override_paid_user():
            return paid_user

        app.dependency_overrides[get_current_user] = override_paid_user
        monkeypatch.setattr(templates_router.settings, "max_active_jobs_per_user", 1)
        monkeypatch.setattr(templates_router.settings, "max_active_jobs_pro", 2)
        monkeypatch.setattr(templates_router, "enqueue_job", AsyncMock())

        source_workflow = Workflow(
            name="Paid Quota Source",
            workflow_json=sample_workflow_json,
            input_schema=sample_input_schema,
            user_id=mock_user.id,
            org_id=mock_user.org_id,
        )
        template = Template(
            name="Paid Quota Template",
            category="utility",
            workflow_json=sample_workflow_json,
            input_schema=sample_input_schema,
        )
        db_session.add_all([source_workflow, template])
        await db_session.flush()
        await db_session.refresh(source_workflow)
        await db_session.refresh(template)

        db_session.add(
            Job(
                workflow_id=source_workflow.id,
                user_id=mock_user.id,
                status="queued",
                input_params={},
                queued_at=datetime.now(UTC),
            )
        )
        await db_session.flush()

        response = await async_client.post(
            f"/v1/templates/{template.id}/run",
            json={"params": {"prompt": "within paid quota"}},
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.json()["status"] == "queued"

    @pytest.mark.asyncio
    async def test_run_template_debits_gpu_job_credits_when_enabled(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        mock_user,
        monkeypatch,
        sample_workflow_json,
        sample_input_schema,
    ):
        """GPU template submissions can be metered with an idempotent debit."""
        from sqlalchemy import select

        from ceq_api.routers import templates as templates_router

        monkeypatch.setattr(templates_router.settings, "gpu_job_credit_debits_enabled", True)
        monkeypatch.setattr(templates_router.settings, "gpu_job_credit_cost_image", 25)
        monkeypatch.setattr(templates_router, "enqueue_job", AsyncMock())

        db_session.add(
            CreditLedgerEntry(
                user_id=mock_user.id,
                org_id=mock_user.org_id,
                amount=30,
                transaction_type=CreditLedgerType.GRANT.value,
                reason="test grant",
                idempotency_key="gpu-job-template-grant",
                ledger_metadata={},
            )
        )
        template = Template(
            name="Billable Image Template",
            category="social",
            workflow_json=sample_workflow_json,
            input_schema=sample_input_schema,
        )
        db_session.add(template)
        await db_session.flush()
        await db_session.refresh(template)

        response = await async_client.post(
            f"/v1/templates/{template.id}/run",
            json={"params": {"prompt": "billable"}},
        )

        assert response.status_code == status.HTTP_200_OK, response.text
        job_id = response.json()["job_id"]
        result = await db_session.execute(
            select(CreditLedgerEntry).where(
                CreditLedgerEntry.transaction_type == CreditLedgerType.DEBIT.value
            )
        )
        debit = result.scalar_one()
        assert debit.amount == -25
        assert str(debit.job_id) == job_id
        assert debit.idempotency_key == f"gpu-job:{job_id}:debit"

    @pytest.mark.asyncio
    async def test_run_template_rejects_gpu_job_when_credits_are_insufficient(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        monkeypatch,
        sample_workflow_json,
        sample_input_schema,
    ):
        """Commercial GPU metering fails closed before enqueue when balance is low."""
        from ceq_api.routers import templates as templates_router

        enqueue = AsyncMock()
        monkeypatch.setattr(templates_router.settings, "gpu_job_credit_debits_enabled", True)
        monkeypatch.setattr(templates_router.settings, "gpu_job_credit_cost_image", 25)
        monkeypatch.setattr(templates_router, "enqueue_job", enqueue)

        template = Template(
            name="Unfunded Image Template",
            category="social",
            workflow_json=sample_workflow_json,
            input_schema=sample_input_schema,
        )
        db_session.add(template)
        await db_session.flush()
        await db_session.refresh(template)

        response = await async_client.post(
            f"/v1/templates/{template.id}/run",
            json={"params": {"prompt": "unfunded"}},
        )

        assert response.status_code == status.HTTP_402_PAYMENT_REQUIRED
        assert response.json()["detail"]["message"] == "Insufficient CEQ credits."
        enqueue.assert_not_called()

    @pytest.mark.asyncio
    async def test_paid_role_can_run_premium_template(
        self,
        app,
        async_client: AsyncClient,
        db_session: AsyncSession,
        mock_user,
        monkeypatch,
        sample_workflow_json,
        sample_input_schema,
    ):
        """A paid Janua role can run premium templates."""
        from ceq_api.routers import templates as templates_router

        paid_user = JanuaUser(
            id=mock_user.id,
            email=mock_user.email,
            org_id=mock_user.org_id,
            roles=["user", "pro"],
        )

        async def override_paid_user():
            return paid_user

        app.dependency_overrides[get_current_user] = override_paid_user
        monkeypatch.setattr(templates_router, "enqueue_job", AsyncMock())

        template = Template(
            name="Paid Premium Run",
            category="utility",
            workflow_json=sample_workflow_json,
            input_schema=sample_input_schema,
            tags=["premium"],
        )
        db_session.add(template)
        await db_session.flush()
        await db_session.refresh(template)

        response = await async_client.post(
            f"/v1/templates/{template.id}/run",
            json={"params": {"prompt": "commercial smoke"}},
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.json()["status"] == "queued"

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
