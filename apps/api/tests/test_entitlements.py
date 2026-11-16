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


_SETTINGS = SimpleNamespace(
    max_active_jobs_admin=30,
    max_active_jobs_studio=12,
    max_active_jobs_pro=7,
    max_active_jobs_per_user=4,
)


@pytest.mark.parametrize(
    "roles",
    [
        ["Pro"],
        ["studio"],
        ["premium"],
        ["admin"],
        ["ceq:pro"],
        ["ceq:studio"],
        ["ceq:admin"],
        ["plan:pro"],
    ],
)
def test_roles_never_grant_paid_templates_or_quota(roles) -> None:
    """Organization roles and app-role grants are not a CEQ purchase."""
    user = JanuaUser(
        id="00000000-0000-0000-0000-000000000001",
        email="org-role@example.com",
        roles=roles,
    )
    assert not user_can_use_paid_templates(user)
    assert active_job_limit_for_user(user, _SETTINGS) == 4


@pytest.mark.parametrize("token", ["ceq:pro-artist", "ceq:studio"])
def test_paid_template_entitlement_via_ceq_tier(token) -> None:
    """The verified ceq_tier entitlement grants paid-template access."""
    user = JanuaUser(
        id="00000000-0000-0000-0000-000000000001",
        email="tier@example.com",
        entitlements=[token],
    )
    assert user_can_use_paid_templates(user)


def test_platform_admin_claim_keeps_admin_access() -> None:
    user = JanuaUser(
        id="00000000-0000-0000-0000-000000000001",
        email="platform-admin@example.com",
        platform_admin=True,
    )
    assert user_can_use_paid_templates(user)
    assert active_job_limit_for_user(user, _SETTINGS) == 30


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


def test_active_job_quota_uses_ceq_tier_entitlements() -> None:
    """The CEQ tier entitlement maps into quota classes."""
    studio = JanuaUser(
        id="00000000-0000-0000-0000-000000000001",
        email="studio@example.com",
        entitlements=["ceq:studio"],
    )
    pro = JanuaUser(
        id="00000000-0000-0000-0000-000000000002",
        email="pro@example.com",
        entitlements=["ceq:pro-artist"],
    )
    assert active_job_limit_for_user(studio, _SETTINGS) == 12
    assert active_job_limit_for_user(pro, _SETTINGS) == 7


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
        entitlements=["ceq:studio"],
    )

    require_template_entitlement(template, user)

    assert "premium" in PREMIUM_TEMPLATE_TAGS
    assert "ceq:studio" in PAID_TEMPLATE_ENTITLEMENTS
