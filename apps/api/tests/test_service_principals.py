"""Tests for Janua ``client_credentials`` service principals.

Covers:
- Token fixtures for BOTH shapes (human authorization_code JWT, machine
  client_credentials JWT) signed with the same RSA key, so the tests exercise
  the real JWKS decode path rather than a mocked validator.
- Claim-shape mapping (``sub: service-account:<client_id>``, ``client_id``,
  ``scope``, ``token_use``, ``actor_type``, ``<product>_tier``).
- The endpoint auth matrix: render/jobs/templates accept service tokens;
  user-specific surfaces reject them.
- Scope enforcement: a machine token without ``ceq:render`` is 403, not 401.
- Rate-limiter bucketing: service principals key on ``client_id`` and never
  collide with the human ``user:<uuid>`` namespace.
"""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import jwt as pyjwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import HTTPException

from ceq_api.auth.janua import (
    SERVICE_PRINCIPAL_NAMESPACE,
    JanuaUser,
    ServicePrincipalRejectedError,
    _is_client_credentials_payload,
    _jwks_breaker,
    _normalize_scopes,
    _service_principal_from_payload,
    _validate_token_local,
    get_current_user,
    get_service_or_user,
    service_principal_id,
    validate_token,
)
from ceq_api.middleware import get_client_identifier
from ceq_api.resilience import CircuitBreakerState, janua_circuit

TEST_AUDIENCE = "ceq-api"
TEST_ISSUER = "https://auth.madfam.io"
TEST_CLIENT_ID = "ceq-batch-driver"
RENDER_SCOPE = "ceq:render"


# ---------------------------------------------------------------------------
# Fixtures — one RSA key, two token shapes
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def rsa_private_key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture
def sign_jwt(rsa_private_key):
    """Sign an arbitrary claim set as an RS256 JWT with a stable kid."""
    private_pem = rsa_private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )

    def _sign(claims: dict) -> str:
        return pyjwt.encode(
            claims, private_pem, algorithm="RS256", headers={"kid": "test-kid-1"}
        )

    return _sign


@pytest.fixture
def user_token(sign_jwt):
    """A HUMAN Janua token (authorization_code grant).

    Shape mirrors janua `_handle_authorization_code_grant`: `sub` is the user's
    UUID and there is no `token_use`/`actor_type` marker.
    """

    def _make(*, sub: str | None = None, **overrides) -> str:
        claims = {
            "sub": sub or str(uuid4()),
            "email": "human@madfam.io",
            "iss": TEST_ISSUER,
            "aud": TEST_AUDIENCE,
            "exp": int(time.time()) + 3600,
            "iat": int(time.time()),
            "client_id": "ceq-studio",
            "scope": "openid profile",
            "roles": ["user"],
            "tier": "community",
        }
        claims.update(overrides)
        return sign_jwt(claims)

    return _make


@pytest.fixture
def service_token(sign_jwt):
    """A MACHINE Janua token (client_credentials grant).

    Shape mirrors janua `_get_client_credentials_claims` +
    `_handle_client_credentials_grant` exactly:
      sub          = "service-account:<client_id>"   (NOT a UUID)
      email        = "<slug>@service.auth.madfam.io"
      token_use    = "client_credentials"
      actor_type   = "service_account"
      roles        = ["service_account"]
      scope        = space-delimited granted scopes
      <product>_tier = "madfam" for each product-namespaced scope
    """

    def _make(
        *,
        client_id: str = TEST_CLIENT_ID,
        scope: str = RENDER_SCOPE,
        aud: str = TEST_AUDIENCE,
        **overrides,
    ) -> str:
        claims = {
            "sub": f"service-account:{client_id}",
            "email": f"{client_id}@service.auth.madfam.io",
            "iss": TEST_ISSUER,
            "aud": aud,
            "exp": int(time.time()) + 3600,
            "iat": int(time.time()),
            "client_id": client_id,
            "scope": scope,
            "token_use": "client_credentials",
            "actor_type": "service_account",
            "roles": ["service_account"],
            "is_admin": False,
            "tier": "community",
            "sub_status": "active",
            "ceq_tier": "madfam",
        }
        claims.update(overrides)
        return sign_jwt(claims)

    return _make


@pytest.fixture
def jwks_decode(rsa_private_key):
    """Point the JWKS client at the in-test public key and set aud/iss config.

    This makes `_validate_token_local` run its REAL decode (signature, issuer
    and audience all verified) against our signed fixtures.
    """
    public_key = rsa_private_key.public_key()
    fake_client = MagicMock()
    fake_client.get_signing_key.return_value = public_key

    with patch("ceq_api.auth.janua._get_jwks_client", return_value=fake_client):
        with patch("ceq_api.auth.janua.settings") as mock_settings:
            mock_settings.janua_enabled = True
            mock_settings.janua_jwks_url = "https://auth.madfam.io/.well-known/jwks.json"
            mock_settings.janua_issuer = TEST_ISSUER
            mock_settings.janua_audience = TEST_AUDIENCE
            mock_settings.service_principals_enabled = True
            mock_settings.service_principal_scope = RENDER_SCOPE
            yield mock_settings


@pytest.fixture(autouse=True)
def reset_breakers():
    """Reset BOTH module-level breakers around every test in this file.

    `_jwks_breaker` guards local validation; `janua_circuit` guards the
    introspection fallback. Both are process-global, so a test here that lets a
    token fall through to introspection would otherwise leave `janua_circuit`
    open and make unrelated fallback tests in test_auth.py fail depending on
    file ordering.
    """

    def _reset():
        _jwks_breaker._failure_count = 0
        _jwks_breaker._is_open = False
        _jwks_breaker._last_failure_time = 0.0
        janua_circuit._state = CircuitBreakerState()

    _reset()
    yield
    _reset()


def _bearer(token: str) -> MagicMock:
    creds = MagicMock()
    creds.credentials = token
    return creds


# ---------------------------------------------------------------------------
# Claim-shape primitives
# ---------------------------------------------------------------------------


class TestClaimShape:
    def test_scope_string_is_split(self):
        assert _normalize_scopes("ceq:render ceq:jobs") == frozenset(
            {"ceq:render", "ceq:jobs"}
        )

    def test_scope_list_is_accepted(self):
        assert _normalize_scopes(["ceq:render"]) == frozenset({"ceq:render"})

    def test_scope_missing_is_empty(self):
        assert _normalize_scopes(None) == frozenset()

    def test_token_use_marks_machine_token(self):
        assert _is_client_credentials_payload({"token_use": "client_credentials"})

    def test_actor_type_alone_marks_machine_token(self):
        """A claim-set tweak upstream must not drop machine tokens to the human
        path, where `UUID(sub)` would blow up on `service-account:<id>`."""
        assert _is_client_credentials_payload({"actor_type": "service_account"})

    def test_human_payload_is_not_machine(self):
        assert not _is_client_credentials_payload(
            {"sub": str(uuid4()), "email": "a@b.c", "scope": "openid"}
        )


class TestServicePrincipalId:
    def test_id_is_deterministic(self):
        """A re-minted token (~hourly) must map to the SAME principal id, or the
        driver's own jobs would vanish from its list after every refresh."""
        assert service_principal_id("abc") == service_principal_id("abc")

    def test_id_differs_per_client(self):
        assert service_principal_id("abc") != service_principal_id("def")

    def test_id_is_uuid5_of_namespace(self):
        from uuid import uuid5

        assert service_principal_id("abc") == uuid5(SERVICE_PRINCIPAL_NAMESPACE, "abc")


# ---------------------------------------------------------------------------
# Local validation — both token shapes through the real decode
# ---------------------------------------------------------------------------


class TestLocalValidation:
    def test_human_token_unchanged(self, jwks_decode, user_token):
        """Additive contract: a human token maps exactly as before."""
        sub = str(uuid4())
        user = _validate_token_local(user_token(sub=sub))

        assert user is not None
        assert user.id == UUID(sub)
        assert user.email == "human@madfam.io"
        assert user.is_service_principal is False
        assert user.client_id is None
        assert user.scopes == frozenset()

    def test_service_token_maps_to_principal(self, jwks_decode, service_token):
        principal = _validate_token_local(service_token())

        assert principal is not None
        assert principal.is_service_principal is True
        assert principal.client_id == TEST_CLIENT_ID
        assert principal.id == service_principal_id(TEST_CLIENT_ID)
        assert principal.has_scope(RENDER_SCOPE)
        assert principal.roles == ["service-account"]

    def test_service_token_sub_is_not_parsed_as_uuid(self, jwks_decode, service_token):
        """`sub` is `service-account:<client_id>` — the human branch would raise."""
        principal = _validate_token_local(service_token())
        assert principal is not None
        assert principal.id != uuid4()

    def test_service_token_wrong_audience_rejected(self, jwks_decode, service_token):
        """Audience binds the machine client to ceq — a yantra4d-audience token
        must never authenticate here."""
        with pytest.raises(pyjwt.InvalidAudienceError):
            _validate_token_local(service_token(aud="yantra4d-api"))

    def test_service_token_org_id_populated(self, jwks_decode, service_token):
        org_id = str(uuid4())
        principal = _validate_token_local(service_token(org_id=org_id))
        assert principal is not None
        assert principal.org_id == UUID(org_id)

    def test_service_token_bad_org_id_is_tolerated(self, jwks_decode, service_token):
        principal = _validate_token_local(service_token(org_id="not-a-uuid"))
        assert principal is not None
        assert principal.org_id is None

    def test_disabled_flag_rejects_machine_token(self, jwks_decode, service_token):
        jwks_decode.service_principals_enabled = False
        with pytest.raises(ServicePrincipalRejectedError):
            _validate_token_local(service_token())

    def test_missing_identity_rejected(self, jwks_decode, sign_jwt):
        token = sign_jwt(
            {
                "sub": "not-a-service-account-sub",
                "iss": TEST_ISSUER,
                "aud": TEST_AUDIENCE,
                "exp": int(time.time()) + 3600,
                "token_use": "client_credentials",
            }
        )
        with pytest.raises(ServicePrincipalRejectedError):
            _validate_token_local(token)

    def test_client_id_recovered_from_sub(self):
        """Identity survives even if the `client_id` claim is absent."""
        principal = _service_principal_from_payload(
            {"sub": "service-account:only-in-sub", "scope": RENDER_SCOPE}
        )
        assert principal is not None
        assert principal.client_id == "only-in-sub"


class TestValidateTokenDoesNotIntrospectMachineTokens:
    @pytest.mark.asyncio
    async def test_rejected_machine_token_skips_introspection(
        self, jwks_decode, service_token
    ):
        """A machine token has no user behind it, so a userinfo round-trip can
        never rescue it — the fallback must not fire."""
        jwks_decode.service_principals_enabled = False

        with patch(
            "ceq_api.auth.janua._validate_token_introspection", new_callable=AsyncMock
        ) as mock_introspect:
            result = await validate_token(service_token())

        assert result is None
        mock_introspect.assert_not_called()

    @pytest.mark.asyncio
    async def test_rejection_does_not_trip_jwks_breaker(
        self, jwks_decode, service_token
    ):
        jwks_decode.service_principals_enabled = False
        await validate_token(service_token())
        assert _jwks_breaker.is_open is False
        assert _jwks_breaker._failure_count == 0


# ---------------------------------------------------------------------------
# Endpoint auth matrix
# ---------------------------------------------------------------------------


class TestEndpointAuthMatrix:
    """`get_current_user` is the human surface; `get_service_or_user` is the
    machine-reachable one (render / jobs / templates)."""

    @pytest.mark.asyncio
    async def test_user_specific_surface_rejects_service_token(
        self, jwks_decode, service_token
    ):
        """Workflows, assets, credits, outputs, operations all depend on
        `get_current_user` — a service token must be 403 there."""
        with pytest.raises(HTTPException) as exc:
            await get_current_user(MagicMock(), _bearer(service_token()))

        assert exc.value.status_code == 403
        assert "Service credentials" in exc.value.detail

    @pytest.mark.asyncio
    async def test_user_specific_surface_still_accepts_humans(
        self, jwks_decode, user_token
    ):
        sub = str(uuid4())
        user = await get_current_user(MagicMock(), _bearer(user_token(sub=sub)))
        assert user.id == UUID(sub)
        assert user.is_service_principal is False

    @pytest.mark.asyncio
    async def test_machine_surface_accepts_service_token(
        self, jwks_decode, service_token
    ):
        request = MagicMock()
        request.state = MagicMock()

        principal = await get_service_or_user(request, _bearer(service_token()))

        assert principal.is_service_principal is True
        assert principal.client_id == TEST_CLIENT_ID
        assert request.state.service_client_id == TEST_CLIENT_ID

    @pytest.mark.asyncio
    async def test_machine_surface_accepts_humans_unchanged(
        self, jwks_decode, user_token
    ):
        sub = str(uuid4())
        request = MagicMock()
        request.state = MagicMock()

        user = await get_service_or_user(request, _bearer(user_token(sub=sub)))

        assert user.id == UUID(sub)
        assert user.is_service_principal is False

    @pytest.mark.asyncio
    async def test_optional_auth_treats_service_token_as_anonymous(
        self, jwks_decode, service_token
    ):
        """An optional-auth endpoint personalizing on "is there a user?" must
        not start personalizing for a machine client."""
        from ceq_api.auth.janua import get_optional_user

        assert await get_optional_user(_bearer(service_token())) is None

    @pytest.mark.asyncio
    async def test_optional_auth_still_returns_humans(self, jwks_decode, user_token):
        from ceq_api.auth.janua import get_optional_user

        user = await get_optional_user(_bearer(user_token()))
        assert user is not None
        assert user.is_service_principal is False

    @pytest.mark.asyncio
    async def test_machine_surface_requires_credentials(self, jwks_decode):
        with pytest.raises(HTTPException) as exc:
            await get_service_or_user(MagicMock(), None)
        assert exc.value.status_code == 401

    @pytest.mark.asyncio
    async def test_machine_surface_rejects_invalid_token(self, jwks_decode):
        with pytest.raises(HTTPException) as exc:
            await get_service_or_user(MagicMock(), _bearer("not-a-jwt"))
        assert exc.value.status_code == 401

    def test_render_router_uses_machine_dependency(self):
        """Guard against a future edit silently dropping machine callers."""
        import inspect

        from ceq_api.routers import render as render_router

        source = inspect.getsource(render_router)
        assert "Depends(get_service_or_user)" in source
        assert "Depends(get_current_user)" not in source

    def test_jobs_router_uses_machine_dependency(self):
        import inspect

        from ceq_api.routers import jobs as jobs_router

        source = inspect.getsource(jobs_router)
        assert "Depends(get_service_or_user)" in source
        assert "Depends(get_current_user)" not in source

    def test_user_specific_routers_keep_human_dependency(self):
        """Workflows/assets/credits/outputs must NOT have been widened."""
        import inspect

        from ceq_api.routers import assets, credits, outputs, workflows

        for module in (workflows, assets, credits, outputs):
            source = inspect.getsource(module)
            assert (
                "Depends(get_service_or_user)" not in source
            ), f"{module.__name__} was widened to machine callers"


# ---------------------------------------------------------------------------
# Scope enforcement
# ---------------------------------------------------------------------------


class TestScopeEnforcement:
    @pytest.mark.asyncio
    async def test_missing_scope_is_403_not_401(self, jwks_decode, service_token):
        """The token authenticated fine — it is simply not authorized here."""
        request = MagicMock()
        request.state = MagicMock()

        with pytest.raises(HTTPException) as exc:
            await get_service_or_user(
                request, _bearer(service_token(scope="ceq:readonly"))
            )

        assert exc.value.status_code == 403
        assert RENDER_SCOPE in exc.value.detail

    @pytest.mark.asyncio
    async def test_empty_scope_is_403(self, jwks_decode, service_token):
        with pytest.raises(HTTPException) as exc:
            await get_service_or_user(MagicMock(), _bearer(service_token(scope="")))
        assert exc.value.status_code == 403

    @pytest.mark.asyncio
    async def test_scope_among_several_is_accepted(self, jwks_decode, service_token):
        request = MagicMock()
        request.state = MagicMock()

        principal = await get_service_or_user(
            request, _bearer(service_token(scope=f"ceq:jobs {RENDER_SCOPE} openid"))
        )
        assert principal.is_service_principal is True

    @pytest.mark.asyncio
    async def test_required_scope_is_configurable(self, jwks_decode, service_token):
        jwks_decode.service_principal_scope = "ceq:batch"
        request = MagicMock()
        request.state = MagicMock()

        # The default scope is now insufficient...
        with pytest.raises(HTTPException) as exc:
            await get_service_or_user(request, _bearer(service_token()))
        assert exc.value.status_code == 403

        # ...and the configured one is what unlocks it.
        principal = await get_service_or_user(
            request, _bearer(service_token(scope="ceq:batch"))
        )
        assert principal.is_service_principal is True

    @pytest.mark.asyncio
    async def test_humans_are_never_scope_gated(self, jwks_decode, user_token):
        """A human token carrying no ceq:render scope must still pass."""
        request = MagicMock()
        request.state = MagicMock()

        user = await get_service_or_user(
            request, _bearer(user_token(scope="openid profile"))
        )
        assert user.is_service_principal is False

    def test_has_scope_is_false_for_humans(self):
        user = JanuaUser(id=uuid4(), email="a@b.c", roles=["user"])
        assert user.has_scope(RENDER_SCOPE) is False


# ---------------------------------------------------------------------------
# Rate-limiter bucketing
# ---------------------------------------------------------------------------


class TestLimiterBucketing:
    def _request(self, **state) -> MagicMock:
        request = MagicMock()
        request.state = MagicMock(spec=list(state) or [])
        for key, value in state.items():
            setattr(request.state, key, value)
        request.headers = {}
        return request

    def test_service_principal_gets_own_bucket(self):
        key = get_client_identifier(self._request(service_client_id=TEST_CLIENT_ID))
        assert key == f"service:{TEST_CLIENT_ID}"

    def test_service_bucket_is_disjoint_from_user_bucket(self):
        """The whole point: a backfill cannot evict humans from their bucket."""
        user_id = uuid4()
        service_key = get_client_identifier(
            self._request(service_client_id=TEST_CLIENT_ID)
        )
        user_key = get_client_identifier(self._request(user_id=user_id))

        assert service_key != user_key
        assert service_key.startswith("service:")
        assert user_key.startswith("user:")

    def test_distinct_clients_get_distinct_buckets(self):
        a = get_client_identifier(self._request(service_client_id="driver-a"))
        b = get_client_identifier(self._request(service_client_id="driver-b"))
        assert a != b

    def test_service_identity_wins_over_user_identity(self):
        """Belt and braces — if both were somehow set, the machine key wins so
        the service call is never billed to a human's bucket."""
        key = get_client_identifier(
            self._request(service_client_id=TEST_CLIENT_ID, user_id=uuid4())
        )
        assert key == f"service:{TEST_CLIENT_ID}"

    def test_human_bucketing_unchanged(self):
        user_id = uuid4()
        assert get_client_identifier(self._request(user_id=user_id)) == f"user:{user_id}"

    def test_falls_back_to_forwarded_for(self):
        request = MagicMock()
        request.state = MagicMock(spec=[])
        request.headers = {"X-Forwarded-For": "203.0.113.7, 10.0.0.1"}
        assert get_client_identifier(request) == "203.0.113.7"

    def test_principal_key_matches_limiter_key(self):
        """`JanuaUser.principal_key` and the limiter key function must agree, or
        logs and buckets would disagree about who a caller is."""
        principal = JanuaUser(
            id=service_principal_id(TEST_CLIENT_ID),
            email="svc@service.auth.madfam.io",
            client_id=TEST_CLIENT_ID,
            is_service_principal=True,
        )
        request = MagicMock()
        request.state = MagicMock(spec=["service_client_id"])
        request.state.service_client_id = TEST_CLIENT_ID
        request.headers = {}

        assert principal.principal_key == get_client_identifier(request)

    def test_service_bucket_limit_is_configurable(self):
        from ceq_api.config import Settings
        from ceq_api.middleware import service_principal_rate_limit

        assert Settings().rate_limit_service_principal == "100/minute"

        with patch("ceq_api.middleware.get_settings") as mock_get:
            mock_get.return_value.rate_limit_service_principal = "500/minute"
            assert service_principal_rate_limit() == "500/minute"
