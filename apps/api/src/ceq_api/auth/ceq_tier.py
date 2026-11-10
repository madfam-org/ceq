"""Resolve a Janua principal's CEQ tier from CEQ's OWN entitlement claims.

Janua mints a per-product claim, ``ceq_tier``, from CEQ's catalog purchase
(the org's ``product_tiers`` or a per-user grant), and ``ceq_tier = "madfam"``
for MADFAM operator clients. It also lists ``ceq:<tier>`` in
``madfam_entitled_products``.

The generic ``tier`` / ``plan`` / ``subscription_tier`` claims are never read.
They summarize whatever product the organization pays for, so reading them
would hand CEQ's paid templates and quotas to buyers of other products.

Order: the ``ceq_tier`` claim; else a ``ceq:<tier>`` entry in
``madfam_entitled_products``; else the free tier. An unknown or malformed
value also resolves to the free tier: the claim fails closed.
"""

from __future__ import annotations

from typing import Any

CEQ_TIER_CLAIM = "ceq_tier"
CEQ_ENTITLEMENT_PREFIX = "ceq:"
ENTITLED_PRODUCTS_CLAIM = "madfam_entitled_products"

# The free, signed-in tier (Dhanam catalog `ceq` tier `creator`).
CEQ_FREE_TIER = "creator"
# MADFAM operators and service accounts.
CEQ_OPERATOR_TIER = "madfam"

# Values a CEQ entitlement claim may carry, mapped to the tier CEQ gates on.
# The paid tiers are exactly the Dhanam catalog slugs for product `ceq`
# (`ceq_pro_artist`, `ceq_studio`). Anything else (another product's tier
# name, a typo, a non-string) is read as the free tier.
CEQ_CLAIM_TIERS: dict[str, str] = {
    "creator": CEQ_FREE_TIER,
    "free": CEQ_FREE_TIER,
    "community": CEQ_FREE_TIER,
    "essentials": CEQ_FREE_TIER,
    "pro_artist": "pro_artist",
    "studio": "studio",
    "madfam": CEQ_OPERATOR_TIER,
    "internal": CEQ_OPERATOR_TIER,
}

# The entitlement tokens each tier contributes to ``JanuaUser.entitlements``.
# They use the normalized (`_` -> `-`) form the template and quota gates read:
# `ceq:pro-artist` expands to `pro` and `ceq:studio` is matched as-is.
#
# `ceq:madfam` marks a MADFAM operator principal. No gate grants anything for
# it today, so operator service clients keep the free tier's template access
# and job cap (README «Service principals»); widening that is a spend decision.
CEQ_TIER_ENTITLEMENTS: dict[str, list[str]] = {
    CEQ_FREE_TIER: [],
    "pro_artist": ["ceq:pro-artist"],
    "studio": ["ceq:studio"],
    CEQ_OPERATOR_TIER: ["ceq:madfam"],
}


def _map_claim_tier(value: Any) -> str:
    if not isinstance(value, str):
        return CEQ_FREE_TIER
    return CEQ_CLAIM_TIERS.get(value.strip().lower().replace("-", "_"), CEQ_FREE_TIER)


def resolve_ceq_tier(claims: Any) -> str:
    """CEQ tier for a token payload or userinfo response (see module docstring)."""
    if not isinstance(claims, dict):
        return CEQ_FREE_TIER

    own = claims.get(CEQ_TIER_CLAIM)
    if own is not None:
        return _map_claim_tier(own)

    entitled = claims.get(ENTITLED_PRODUCTS_CLAIM)
    if isinstance(entitled, list):
        for entry in entitled:
            if isinstance(entry, str) and entry.startswith(CEQ_ENTITLEMENT_PREFIX):
                return _map_claim_tier(entry[len(CEQ_ENTITLEMENT_PREFIX) :])

    return CEQ_FREE_TIER


def ceq_entitlements_from_claims(claims: Any) -> list[str] | None:
    """``JanuaUser.entitlements`` for a payload: the resolved tier's tokens, or None."""
    entitlements = CEQ_TIER_ENTITLEMENTS.get(resolve_ceq_tier(claims), [])
    return list(entitlements) or None
