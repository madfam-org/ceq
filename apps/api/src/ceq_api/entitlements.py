"""Commercial entitlement helpers for CEQ API surfaces.

Studio can hide premium templates, but commercial GA requires the API to
fail closed when callers bypass the UI. This module keeps the initial policy
intentionally small: template tags declare the gated surface; the verified
``ceq_tier`` entitlement declares whether the user can use it.
"""

from collections.abc import Iterable

from fastapi import HTTPException, status

from ceq_api.auth import JanuaUser
from ceq_api.models import Template

PREMIUM_TEMPLATE_TAGS = {"pro", "premium"}
# Paid-template access comes ONLY from `JanuaUser.entitlements`, which
# `ceq_entitlements_from_claims` fills from the verified `ceq_tier` claim
# (see `auth/ceq_tier.py`). The `roles` claim is never read here: it carries
# organization membership roles and application-role grants, neither of which
# is a CEQ purchase.
PAID_TEMPLATE_ENTITLEMENTS = frozenset({"ceq:pro-artist", "ceq:studio"})


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
    """Return true when the verified CEQ tier entitlement grants paid templates."""
    entitlements = set(getattr(user, "entitlements", None) or [])
    return user.is_admin or bool(entitlements & PAID_TEMPLATE_ENTITLEMENTS)


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
