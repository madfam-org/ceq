"""CEQ gates only on its OWN Janua tier claim.

Janua's generic `tier` / `plan` claims describe whatever product the org pays
for. Reading them would hand CEQ's paid templates and job caps to buyers of
other products, so CEQ reads `ceq_tier`, else `ceq:<tier>` in
`madfam_entitled_products`, else the free `creator` tier.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from ceq_api.auth.ceq_tier import (
    CEQ_FREE_TIER,
    ceq_entitlements_from_claims,
    resolve_ceq_tier,
)
from ceq_api.auth.janua import (
    JanuaUser,
    _service_principal_from_payload,
    _validate_token_introspection,
    _validate_token_local,
)
from ceq_api.entitlements import user_can_use_paid_templates
from ceq_api.quotas import active_job_limit_for_user

QUOTA_SETTINGS = SimpleNamespace(
    max_active_jobs_per_user=5,
    max_active_jobs_pro=10,
    max_active_jobs_studio=25,
    max_active_jobs_admin=0,
)

# Every generic claim a non-CEQ purchase could put on a token.
FOREIGN_PAID_CLAIMS = {
    "tier": "premium",
    "plan": "studio",
    "plan_id": "pro",
    "subscription": "pro",
    "subscription_tier": "enterprise",
    "entitlements": ["pro", "studio", "ceq:studio"],
    "plans": ["studio"],
    "tezca_tier": "academic",
    "madfam_entitled_products": ["tezca:academic", "rondelio:developer"],
}


def _user(entitlements: list[str] | None) -> JanuaUser:
    return JanuaUser(id=uuid4(), email="u@example.com", roles=["user"], entitlements=entitlements)


class TestResolveCeqTier:
    @pytest.mark.parametrize(
        ("claims", "expected"),
        [
            ({"ceq_tier": "pro_artist"}, "pro_artist"),
            ({"ceq_tier": "studio"}, "studio"),
            ({"ceq_tier": "Pro-Artist"}, "pro_artist"),
            ({"ceq_tier": " STUDIO "}, "studio"),
            ({"ceq_tier": "creator"}, CEQ_FREE_TIER),
            ({"ceq_tier": "madfam"}, "madfam"),
            ({"ceq_tier": "internal"}, "madfam"),
            ({"madfam_entitled_products": ["tezca:academic", "ceq:studio"]}, "studio"),
            ({"madfam_entitled_products": ["ceq:pro_artist"]}, "pro_artist"),
        ],
    )
    def test_reads_own_claims(self, claims, expected):
        assert resolve_ceq_tier(claims) == expected

    def test_own_claim_wins_over_entitled_products(self):
        claims = {"ceq_tier": "pro_artist", "madfam_entitled_products": ["ceq:studio"]}
        assert resolve_ceq_tier(claims) == "pro_artist"

    def test_present_but_unknown_own_claim_does_not_fall_through(self):
        claims = {"ceq_tier": "enterprise", "madfam_entitled_products": ["ceq:studio"]}
        assert resolve_ceq_tier(claims) == CEQ_FREE_TIER

    def test_generic_claims_are_never_read(self):
        assert resolve_ceq_tier(FOREIGN_PAID_CLAIMS) == CEQ_FREE_TIER
        assert ceq_entitlements_from_claims(FOREIGN_PAID_CLAIMS) is None

    @pytest.mark.parametrize(
        "claims",
        [
            None,
            "studio",
            [],
            {},
            {"ceq_tier": None},
            {"ceq_tier": 3},
            {"ceq_tier": ["studio"]},
            {"ceq_tier": "premium"},
            {"ceq_tier": "pro"},
            {"ceq_tier": ""},
            {"madfam_entitled_products": "ceq:studio"},
            {"madfam_entitled_products": [None, 7, "ceq:gold"]},
        ],
    )
    def test_fails_closed(self, claims):
        assert resolve_ceq_tier(claims) == CEQ_FREE_TIER

    @pytest.mark.parametrize(
        ("tier", "entitlements"),
        [
            ("pro_artist", ["ceq:pro-artist"]),
            ("studio", ["ceq:studio"]),
            ("madfam", ["ceq:madfam"]),
            ("creator", None),
        ],
    )
    def test_entitlement_tokens(self, tier, entitlements):
        assert ceq_entitlements_from_claims({"ceq_tier": tier}) == entitlements


class TestGatesReadTheResolvedTier:
    def test_pro_artist_unlocks_pro(self):
        user = _user(ceq_entitlements_from_claims({"ceq_tier": "pro_artist"}))
        assert user_can_use_paid_templates(user) is True
        assert active_job_limit_for_user(user, QUOTA_SETTINGS) == 10

    def test_studio_unlocks_studio(self):
        user = _user(ceq_entitlements_from_claims({"ceq_tier": "studio"}))
        assert user_can_use_paid_templates(user) is True
        assert active_job_limit_for_user(user, QUOTA_SETTINGS) == 25

    def test_operator_tier_grants_nothing_extra(self):
        user = _user(ceq_entitlements_from_claims({"ceq_tier": "madfam"}))
        assert user_can_use_paid_templates(user) is False
        assert active_job_limit_for_user(user, QUOTA_SETTINGS) == 5

    def test_foreign_purchase_stays_free(self):
        user = _user(ceq_entitlements_from_claims(FOREIGN_PAID_CLAIMS))
        assert user_can_use_paid_templates(user) is False
        assert active_job_limit_for_user(user, QUOTA_SETTINGS) == 5


def _patched_settings():
    settings = MagicMock()
    settings.janua_issuer = ""
    settings.janua_audience = ""
    settings.service_principals_enabled = True
    return settings


class TestTokenPaths:
    """Every validation path uses the same resolver."""

    def _decode(self, payload):
        jwks = MagicMock()
        jwks.get_signing_key.return_value = MagicMock(key="k")
        return (
            patch("ceq_api.auth.janua._get_jwks_client", return_value=jwks),
            patch("ceq_api.auth.janua.jwt.decode", return_value=payload),
            patch("ceq_api.auth.janua.settings", _patched_settings()),
        )

    def _local(self, payload):
        a, b, c = self._decode(payload)
        with a, b, c:
            return _validate_token_local("token")

    def test_human_token_ignores_generic_claims(self):
        payload = {"sub": str(uuid4()), "email": "h@example.com", **FOREIGN_PAID_CLAIMS}
        user = self._local(payload)
        assert user is not None
        assert user.entitlements is None

    def test_human_token_reads_ceq_tier(self):
        payload = {
            "sub": str(uuid4()),
            "email": "h@example.com",
            **FOREIGN_PAID_CLAIMS,
            "ceq_tier": "studio",
        }
        assert self._local(payload).entitlements == ["ceq:studio"]

    def test_human_token_reads_entitled_products(self):
        payload = {
            "sub": str(uuid4()),
            "email": "h@example.com",
            "madfam_entitled_products": ["ceq:pro_artist"],
        }
        assert self._local(payload).entitlements == ["ceq:pro-artist"]

    def test_service_principal_ignores_org_generic_tier(self):
        payload = {
            "sub": "service-account:batch",
            "client_id": "batch",
            "token_use": "client_credentials",
            "actor_type": "service_account",
            "scope": "ceq:render",
            "roles": ["service_account"],
            "tier": "premium",
            "entitlements": ["studio"],
        }
        with patch("ceq_api.auth.janua.settings", _patched_settings()):
            principal = _service_principal_from_payload(payload)
        assert principal is not None
        assert principal.entitlements is None
        assert user_can_use_paid_templates(principal) is False
        assert active_job_limit_for_user(principal, QUOTA_SETTINGS) == 5

    def test_service_principal_operator_tier(self):
        payload = {
            "sub": "service-account:batch",
            "client_id": "batch",
            "token_use": "client_credentials",
            "scope": "ceq:render",
            "tier": "community",
            "ceq_tier": "madfam",
        }
        with patch("ceq_api.auth.janua.settings", _patched_settings()):
            principal = _service_principal_from_payload(payload)
        assert principal.entitlements == ["ceq:madfam"]

    def test_service_principal_org_bought_ceq(self):
        payload = {
            "sub": "service-account:batch",
            "client_id": "batch",
            "token_use": "client_credentials",
            "scope": "ceq:render",
            "tier": "community",
            "ceq_tier": "pro_artist",
        }
        with patch("ceq_api.auth.janua.settings", _patched_settings()):
            principal = _service_principal_from_payload(payload)
        assert principal.entitlements == ["ceq:pro-artist"]

    @pytest.mark.asyncio
    async def test_introspection_ignores_generic_claims(self):
        response = MagicMock(status_code=200)
        response.json.return_value = {
            "id": str(uuid4()),
            "email": "i@example.com",
            **FOREIGN_PAID_CLAIMS,
        }
        client = AsyncMock()
        client.get = AsyncMock(return_value=response)
        with patch("ceq_api.auth.janua.get_janua_client", return_value=client):
            user = await _validate_token_introspection("token")
        assert user is not None
        assert user.entitlements is None

    @pytest.mark.asyncio
    async def test_introspection_reads_ceq_tier(self):
        response = MagicMock(status_code=200)
        response.json.return_value = {
            "id": str(uuid4()),
            "email": "i@example.com",
            "ceq_tier": "pro_artist",
        }
        client = AsyncMock()
        client.get = AsyncMock(return_value=response)
        with patch("ceq_api.auth.janua.get_janua_client", return_value=client):
            user = await _validate_token_introspection("token")
        assert user.entitlements == ["ceq:pro-artist"]
