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
PAID_TEMPLATE_ROLES = {"admin", "paid", "pro", "premium", "studio"}
PAID_TEMPLATE_ENTITLEMENTS = PAID_TEMPLATE_ROLES | {
    "ceq-admin",
    "ceq:admin",
    "ceq-paid",
    "ceq-pro",
    "ceq-premium",
    "ceq-studio",
    "ceq:pro",
    "ceq:premium",
    "ceq:studio",
    "plan:paid",
    "plan:pro",
    "plan:premium",
    "plan:studio",
    "plan-paid",
    "plan-pro",
    "plan-premium",
    "plan-studio",
    "tier:paid",
    "tier:pro",
    "tier-pro",
    "tier-paid",
}


def _expand_entitlement_values(values: Iterable[object] | None) -> set[str]:
    normalized = _normalize(values)
    expanded = set(normalized)

    for value in normalized:
        if value.startswith("ceq-") or value.startswith("ceq:"):
            expanded.add(value.removeprefix("ceq:").removeprefix("ceq-"))
        if value.startswith("plan:") or value.startswith("plan-"):
            expanded.add(value.split(":", 1)[1] if ":" in value else value.split("-", 1)[1])
        if value.startswith("tier:") or value.startswith("tier-"):
            expanded.add(value.split(":", 1)[1] if ":" in value else value.split("-", 1)[1])

        if value.endswith("-artist"):
            expanded.add(value.removesuffix("-artist"))

    return expanded


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
    capability_tokens = _expand_entitlement_values(
        _normalize(user.roles) | _normalize(getattr(user, "entitlements", None))
    )
    return user.is_admin or bool(capability_tokens & PAID_TEMPLATE_ENTITLEMENTS)


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
