"""Commercial entitlement tests."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from ceq_api.auth import JanuaUser
from ceq_api.entitlements import (
    PAID_TEMPLATE_ENTITLEMENTS,
    PREMIUM_TEMPLATE_TAGS,
    require_template_entitlement,
    user_can_use_paid_templates,
)
from ceq_api.models import Template
from ceq_api.quotas import active_job_limit_for_user


def test_paid_template_entitlement_via_roles() -> None:
    """Role tokens continue to grant paid-template access."""
    user = JanuaUser(
        id="00000000-0000-0000-0000-000000000001",
        email="pro@example.com",
        roles=["free", "Pro"],
    )
    assert user_can_use_paid_templates(user)


def test_paid_template_entitlement_via_plan_claim() -> None:
    """Plan claim tokens should grant paid-template access."""
    user = JanuaUser(
        id="00000000-0000-0000-0000-000000000001",
        email="plan@example.com",
        entitlements=["plan:pro"],
    )
    assert user_can_use_paid_templates(user)


def test_paid_template_entitlement_via_plan_alias() -> None:
    """Alias-style entitlement claims should map to quota/template tokens."""
    user = JanuaUser(
        id="00000000-0000-0000-0000-000000000001",
        email="planalias@example.com",
        entitlements=["pro-artist"],
    )
    assert user_can_use_paid_templates(user)


def test_premium_template_entitlement_gate() -> None:
    """Un-entitled users cannot run premium templates."""
    template = Template(
        name="Premium Surface",
        category="utility",
        workflow_json={},
        input_schema={},
        tags=["premium"],
    )
    user = JanuaUser(
        id="00000000-0000-0000-0000-000000000001",
        email="free@example.com",
        roles=["creator"],
    )

    with pytest.raises(HTTPException):
        require_template_entitlement(template, user)


def test_active_job_quota_uses_plan_entitlements() -> None:
    """Plan-style entitlements should map into quota classes."""
    user = JanuaUser(
        id="00000000-0000-0000-0000-000000000001",
        email="plan-user@example.com",
        entitlements=["plan_studio"],
    )
    settings = SimpleNamespace(
        max_active_jobs_admin=30,
        max_active_jobs_studio=12,
        max_active_jobs_pro=7,
        max_active_jobs_per_user=4,
    )
    assert active_job_limit_for_user(user, settings) == 12


def test_template_entitlement_metadata_includes_normalized_tokens() -> None:
    """Metadata returns normalized template tags and entitlement details."""
    template = Template(
        name="Premium Template",
        category="social",
        workflow_json={},
        input_schema={},
        tags=["  PRo", "Premium", "creative"],
    )
    user = JanuaUser(
        id="00000000-0000-0000-0000-000000000001",
        email="basic@example.com",
        roles=["guest"],
        entitlements=["ceq:premium"],
    )

    require_template_entitlement(template, user)

    assert "premium" in PREMIUM_TEMPLATE_TAGS
    assert "ceq:premium" in PAID_TEMPLATE_ENTITLEMENTS
