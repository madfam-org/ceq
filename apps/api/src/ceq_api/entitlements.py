"""Commercial entitlement helpers for CEQ API surfaces.

Studio can hide premium templates, but commercial GA requires the API to
fail closed when callers bypass the UI. This module keeps the initial policy
intentionally small: template tags declare the gated surface; Janua roles
declare whether the user can use it.
"""

from collections.abc import Iterable

from fastapi import HTTPException, status

from ceq_api.auth import JanuaUser
from ceq_api.models import Template

PREMIUM_TEMPLATE_TAGS = {"pro", "premium"}
PAID_TEMPLATE_ROLES = {
    "admin",
    "ceq-admin",
    "ceq:admin",
    "paid",
    "pro",
    "premium",
    "studio",
    "ceq-pro",
    "ceq-premium",
    "ceq-studio",
    "ceq:pro",
    "ceq:premium",
    "ceq:studio",
    "plan-pro",
    "plan-premium",
    "plan-studio",
    "plan:pro",
    "plan:premium",
    "plan:studio",
    "tier-pro",
    "tier-premium",
    "tier-studio",
    "tier:pro",
    "tier:premium",
    "tier:studio",
}


def _normalize(values: Iterable[object] | None) -> set[str]:
    """Normalize tags/roles while preserving common role namespace separators."""
    return {
        str(value).strip().lower().replace("_", "-")
        for value in values or []
        if str(value).strip()
    }


def template_requires_paid_entitlement(template: Template) -> bool:
    """Return true when a template is tagged as a paid/commercial surface."""
    return bool(_normalize(template.tags) & PREMIUM_TEMPLATE_TAGS)


def user_can_use_paid_templates(user: JanuaUser) -> bool:
    """Return true when Janua roles grant paid-template access."""
    return user.is_admin or bool(_normalize(user.roles) & PAID_TEMPLATE_ROLES)


def require_template_entitlement(template: Template, user: JanuaUser) -> None:
    """Raise when a user attempts to use a gated template without entitlement."""
    if not template_requires_paid_entitlement(template):
        return

    if user_can_use_paid_templates(user):
        return

    raise HTTPException(
        status_code=status.HTTP_402_PAYMENT_REQUIRED,
        detail={
            "message": "Template requires Pro or Studio access.",
            "required_entitlement": "paid_template",
            "template_id": str(template.id),
            "template_tags": sorted(_normalize(template.tags)),
        },
    )
