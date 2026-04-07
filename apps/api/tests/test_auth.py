"""Tests for Janua authentication integration.

Covers:
- JanuaUser dataclass
- Local JWKS RS256 validation (primary path)
- Introspection fallback (legacy path)
- JWKS circuit breaker behavior
- FastAPI dependency functions (get_current_user, get_optional_user, etc.)
- Integration tests for auth-protected endpoints
"""

import time
import pytest
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock
from uuid import uuid4, UUID

import httpx
import jwt as pyjwt
from jwt import PyJWKClientError
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization
from fastapi import HTTPException

from ceq_api.auth.janua import (
    JanuaUser,
    JWKSCircuitBreaker,
    validate_token,
    get_current_user,
    get_optional_user,
    require_auth,
    require_admin,
    _validate_token_local,
    _validate_token_introspection,
    _jwks_breaker,
)


# ---------------------------------------------------------------------------
# Fixtures: RSA key pair for signing test JWTs
# ---------------------------------------------------------------------------

@pytest.fixture
def rsa_private_key():
    """Generate an RSA private key for test JWT signing."""
    return rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
    )


@pytest.fixture
def rsa_public_key(rsa_private_key):
    """Get the public key from the test RSA private key."""
    return rsa_private_key.public_key()


@pytest.fixture
def make_test_jwt(rsa_private_key):
    """Factory fixture to create signed RS256 JWTs with custom claims."""
    def _make(
        sub: str | None = None,
        email: str = "test@madfam.io",
        org_id: str | None = None,
        roles: list[str] | None = None,
        iss: str = "https://auth.madfam.io",
        aud: str = "ceq-api",
        exp_offset: int = 3600,
        extra_claims: dict | None = None,
    ) -> str:
        if sub is None:
            sub = str(uuid4())
        payload = {
            "sub": sub,
            "email": email,
            "iss": iss,
            "aud": aud,
            "exp": int(time.time()) + exp_offset,
            "iat": int(time.time()),
        }
        if org_id is not None:
            payload["org_id"] = org_id
        if roles is not None:
            payload["roles"] = roles
        if extra_claims:
            payload.update(extra_claims)

        private_pem = rsa_private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
        return pyjwt.encode(payload, private_pem, algorithm="RS256", headers={"kid": "test-kid-1"})

    return _make


@pytest.fixture(autouse=True)
def reset_jwks_breaker():
    """Reset the module-level JWKS circuit breaker between tests."""
    _jwks_breaker._failure_count = 0
    _jwks_breaker._is_open = False
    _jwks_breaker._last_failure_time = 0.0
    yield
    _jwks_breaker._failure_count = 0
    _jwks_breaker._is_open = False
    _jwks_breaker._last_failure_time = 0.0


# ---------------------------------------------------------------------------
# JanuaUser
# ---------------------------------------------------------------------------

class TestJanuaUser:
    """Tests for JanuaUser dataclass."""

    def test_is_admin_with_admin_role(self):
        """User with admin role should return True for is_admin."""
        user = JanuaUser(
            id=uuid4(),
            email="admin@test.com",
            roles=["admin", "user"],
        )
        assert user.is_admin is True

    def test_is_admin_without_admin_role(self):
        """User without admin role should return False for is_admin."""
        user = JanuaUser(
            id=uuid4(),
            email="user@test.com",
            roles=["user"],
        )
        assert user.is_admin is False

    def test_is_admin_with_none_roles(self):
        """User with None roles should return False for is_admin."""
        user = JanuaUser(
            id=uuid4(),
            email="user@test.com",
            roles=None,
        )
        assert user.is_admin is False


# ---------------------------------------------------------------------------
# JWKS Circuit Breaker
# ---------------------------------------------------------------------------

class TestJWKSCircuitBreaker:
    """Tests for the JWKS-specific circuit breaker."""

    def test_starts_closed(self):
        """New breaker should start in closed state."""
        breaker = JWKSCircuitBreaker(failure_threshold=3, reset_timeout=60.0)
        assert breaker.is_open is False

    def test_opens_after_threshold_failures(self):
        """Breaker should open after reaching failure threshold."""
        breaker = JWKSCircuitBreaker(failure_threshold=3, reset_timeout=60.0)
        breaker.record_failure()
        breaker.record_failure()
        assert breaker.is_open is False  # Below threshold
        breaker.record_failure()
        assert breaker.is_open is True  # At threshold

    def test_success_resets_failure_count(self):
        """Successful operation should reset failure count."""
        breaker = JWKSCircuitBreaker(failure_threshold=3, reset_timeout=60.0)
        breaker.record_failure()
        breaker.record_failure()
        breaker.record_success()
        assert breaker._failure_count == 0
        assert breaker.is_open is False

    def test_auto_resets_after_timeout(self):
        """Breaker should auto-reset to half-open after timeout expires."""
        breaker = JWKSCircuitBreaker(failure_threshold=1, reset_timeout=0.01)
        breaker.record_failure()
        assert breaker.is_open is True
        # Wait for timeout
        time.sleep(0.02)
        assert breaker.is_open is False  # Auto-reset

    def test_stays_open_before_timeout(self):
        """Breaker should stay open before timeout expires."""
        breaker = JWKSCircuitBreaker(failure_threshold=1, reset_timeout=600.0)
        breaker.record_failure()
        assert breaker.is_open is True


# ---------------------------------------------------------------------------
# Local JWKS RS256 Validation
# ---------------------------------------------------------------------------

class TestValidateTokenLocal:
    """Tests for local JWKS RS256 token validation."""

    def test_returns_none_when_jwks_not_configured(self):
        """Should return None when JWKS client is not configured."""
        with patch("ceq_api.auth.janua._get_jwks_client", return_value=None):
            result = _validate_token_local("any-token")
            assert result is None

    def test_valid_token_returns_user(self, rsa_public_key, make_test_jwt):
        """Valid RS256 JWT should be decoded to JanuaUser."""
        user_id = str(uuid4())
        org_id = str(uuid4())
        token = make_test_jwt(
            sub=user_id,
            email="alice@madfam.io",
            org_id=org_id,
            roles=["user", "editor"],
        )

        mock_jwks = MagicMock()
        mock_jwks.get_signing_key.return_value = rsa_public_key

        with patch("ceq_api.auth.janua._get_jwks_client", return_value=mock_jwks):
            with patch("ceq_api.auth.janua.settings") as mock_settings:
                mock_settings.janua_issuer = "https://auth.madfam.io"
                mock_settings.janua_audience = "ceq-api"

                user = _validate_token_local(token)

        assert user is not None
        assert str(user.id) == user_id
        assert user.email == "alice@madfam.io"
        assert str(user.org_id) == org_id
        assert user.roles == ["user", "editor"]

    def test_expired_token_raises(self, rsa_public_key, make_test_jwt):
        """Expired JWT should raise ExpiredSignatureError."""
        token = make_test_jwt(exp_offset=-3600)  # Expired 1 hour ago

        mock_jwks = MagicMock()
        mock_jwks.get_signing_key.return_value = rsa_public_key

        with patch("ceq_api.auth.janua._get_jwks_client", return_value=mock_jwks):
            with patch("ceq_api.auth.janua.settings") as mock_settings:
                mock_settings.janua_issuer = "https://auth.madfam.io"
                mock_settings.janua_audience = "ceq-api"

                with pytest.raises(pyjwt.ExpiredSignatureError):
                    _validate_token_local(token)

    def test_wrong_issuer_raises(self, rsa_public_key, make_test_jwt):
        """JWT with wrong issuer should raise InvalidIssuerError."""
        token = make_test_jwt(iss="https://evil.com")

        mock_jwks = MagicMock()
        mock_jwks.get_signing_key.return_value = rsa_public_key

        with patch("ceq_api.auth.janua._get_jwks_client", return_value=mock_jwks):
            with patch("ceq_api.auth.janua.settings") as mock_settings:
                mock_settings.janua_issuer = "https://auth.madfam.io"
                mock_settings.janua_audience = "ceq-api"

                with pytest.raises(pyjwt.InvalidIssuerError):
                    _validate_token_local(token)

    def test_wrong_audience_raises(self, rsa_public_key, make_test_jwt):
        """JWT with wrong audience should raise InvalidAudienceError."""
        token = make_test_jwt(aud="wrong-audience")

        mock_jwks = MagicMock()
        mock_jwks.get_signing_key.return_value = rsa_public_key

        with patch("ceq_api.auth.janua._get_jwks_client", return_value=mock_jwks):
            with patch("ceq_api.auth.janua.settings") as mock_settings:
                mock_settings.janua_issuer = "https://auth.madfam.io"
                mock_settings.janua_audience = "ceq-api"

                with pytest.raises(pyjwt.InvalidAudienceError):
                    _validate_token_local(token)

    def test_missing_sub_returns_none(self, rsa_public_key, rsa_private_key):
        """JWT without sub claim should return None."""
        private_pem = rsa_private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
        token = pyjwt.encode(
            {"email": "no-sub@test.com", "exp": int(time.time()) + 3600, "iat": int(time.time())},
            private_pem,
            algorithm="RS256",
            headers={"kid": "test-kid-1"},
        )

        mock_jwks = MagicMock()
        mock_jwks.get_signing_key.return_value = rsa_public_key

        with patch("ceq_api.auth.janua._get_jwks_client", return_value=mock_jwks):
            with patch("ceq_api.auth.janua.settings") as mock_settings:
                mock_settings.janua_issuer = ""
                mock_settings.janua_audience = ""

                user = _validate_token_local(token)
                assert user is None

    def test_missing_email_returns_none(self, rsa_public_key, rsa_private_key):
        """JWT without email claim should return None."""
        private_pem = rsa_private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
        token = pyjwt.encode(
            {"sub": str(uuid4()), "exp": int(time.time()) + 3600, "iat": int(time.time())},
            private_pem,
            algorithm="RS256",
            headers={"kid": "test-kid-1"},
        )

        mock_jwks = MagicMock()
        mock_jwks.get_signing_key.return_value = rsa_public_key

        with patch("ceq_api.auth.janua._get_jwks_client", return_value=mock_jwks):
            with patch("ceq_api.auth.janua.settings") as mock_settings:
                mock_settings.janua_issuer = ""
                mock_settings.janua_audience = ""

                user = _validate_token_local(token)
                assert user is None

    def test_jwks_fetch_failure_raises_pyjwkclienterror(self):
        """JWKS endpoint failure should propagate as PyJWKClientError."""
        mock_jwks = MagicMock()
        mock_jwks.get_signing_key.side_effect = PyJWKClientError("JWKS endpoint down")

        with patch("ceq_api.auth.janua._get_jwks_client", return_value=mock_jwks):
            with pytest.raises(PyJWKClientError):
                _validate_token_local("any-token")

    def test_no_issuer_or_audience_validation_when_empty(self, rsa_public_key, make_test_jwt):
        """When issuer/audience not configured, should skip those validations."""
        token = make_test_jwt(iss="any-issuer", aud="any-audience")

        mock_jwks = MagicMock()
        mock_jwks.get_signing_key.return_value = rsa_public_key

        with patch("ceq_api.auth.janua._get_jwks_client", return_value=mock_jwks):
            with patch("ceq_api.auth.janua.settings") as mock_settings:
                mock_settings.janua_issuer = ""
                mock_settings.janua_audience = ""

                user = _validate_token_local(token)
                assert user is not None


# ---------------------------------------------------------------------------
# Introspection Fallback
# ---------------------------------------------------------------------------

class TestValidateTokenIntrospection:
    """Tests for introspection-based token validation (legacy fallback)."""

    @pytest.mark.asyncio
    async def test_introspection_success(self):
        """Valid introspection response should return JanuaUser."""
        user_id = str(uuid4())
        org_id = str(uuid4())

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "id": user_id,
            "email": "valid@test.com",
            "org_id": org_id,
            "roles": ["user"],
        }

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch("ceq_api.auth.janua.get_janua_client", return_value=mock_client):
            user = await _validate_token_introspection("valid-token")

        assert user is not None
        assert user.email == "valid@test.com"
        assert str(user.id) == user_id

    @pytest.mark.asyncio
    async def test_introspection_invalid_status(self):
        """Non-200 status from introspection should return None."""
        mock_response = MagicMock()
        mock_response.status_code = 401

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch("ceq_api.auth.janua.get_janua_client", return_value=mock_client):
            user = await _validate_token_introspection("invalid-token")

        assert user is None


# ---------------------------------------------------------------------------
# Unified validate_token (JWKS -> introspection fallback)
# ---------------------------------------------------------------------------

class TestValidateToken:
    """Tests for the unified token validation with JWKS + fallback."""

    @pytest.mark.asyncio
    async def test_validate_token_disabled(self):
        """When Janua is disabled, should return mock user."""
        with patch("ceq_api.auth.janua.settings") as mock_settings:
            mock_settings.janua_enabled = False

            user = await validate_token("any-token")

            assert user is not None
            assert user.email == "dev@ceq.local"
            assert "user" in user.roles

    @pytest.mark.asyncio
    async def test_jwks_success_skips_introspection(self, rsa_public_key, make_test_jwt):
        """When JWKS validates successfully, introspection should not be called."""
        user_id = str(uuid4())
        token = make_test_jwt(sub=user_id, email="fast@madfam.io", roles=["user"])

        mock_jwks = MagicMock()
        mock_jwks.get_signing_key.return_value = rsa_public_key

        mock_introspection = AsyncMock()

        with patch("ceq_api.auth.janua.settings") as mock_settings:
            mock_settings.janua_enabled = True
            mock_settings.janua_jwks_url = "https://auth.madfam.io/.well-known/jwks.json"
            mock_settings.janua_issuer = "https://auth.madfam.io"
            mock_settings.janua_audience = "ceq-api"

            with patch("ceq_api.auth.janua._get_jwks_client", return_value=mock_jwks):
                with patch(
                    "ceq_api.auth.janua._validate_token_introspection",
                    mock_introspection,
                ):
                    user = await validate_token(token)

        assert user is not None
        assert str(user.id) == user_id
        assert user.email == "fast@madfam.io"
        mock_introspection.assert_not_called()

    @pytest.mark.asyncio
    async def test_jwks_failure_falls_back_to_introspection(self):
        """When JWKS fetch fails, should fall back to introspection."""
        user_id = str(uuid4())

        mock_jwks = MagicMock()
        mock_jwks.get_signing_key.side_effect = PyJWKClientError("JWKS down")

        expected_user = JanuaUser(
            id=UUID(user_id),
            email="fallback@madfam.io",
            roles=["user"],
        )

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "id": user_id,
            "email": "fallback@madfam.io",
            "roles": ["user"],
        }

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch("ceq_api.auth.janua.settings") as mock_settings:
            mock_settings.janua_enabled = True
            mock_settings.janua_jwks_url = "https://auth.madfam.io/.well-known/jwks.json"
            mock_settings.janua_issuer = "https://auth.madfam.io"
            mock_settings.janua_audience = "ceq-api"

            with patch("ceq_api.auth.janua._get_jwks_client", return_value=mock_jwks):
                with patch("ceq_api.auth.janua.get_janua_client", return_value=mock_client):
                    user = await validate_token("some-token")

        assert user is not None
        assert user.email == "fallback@madfam.io"

    @pytest.mark.asyncio
    async def test_expired_token_returns_none_no_fallback(self, rsa_public_key, make_test_jwt):
        """Expired token should return None without falling back to introspection."""
        token = make_test_jwt(exp_offset=-3600)

        mock_jwks = MagicMock()
        mock_jwks.get_signing_key.return_value = rsa_public_key

        mock_introspection = AsyncMock()

        with patch("ceq_api.auth.janua.settings") as mock_settings:
            mock_settings.janua_enabled = True
            mock_settings.janua_jwks_url = "https://auth.madfam.io/.well-known/jwks.json"
            mock_settings.janua_issuer = "https://auth.madfam.io"
            mock_settings.janua_audience = "ceq-api"

            with patch("ceq_api.auth.janua._get_jwks_client", return_value=mock_jwks):
                with patch(
                    "ceq_api.auth.janua._validate_token_introspection",
                    mock_introspection,
                ):
                    user = await validate_token(token)

        assert user is None
        mock_introspection.assert_not_called()

    @pytest.mark.asyncio
    async def test_jwks_not_configured_uses_introspection(self):
        """When JWKS URL is empty, should use introspection as primary path."""
        user_id = str(uuid4())

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "id": user_id,
            "email": "introspection@test.com",
            "roles": ["user"],
        }

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch("ceq_api.auth.janua.settings") as mock_settings:
            mock_settings.janua_enabled = True
            mock_settings.janua_jwks_url = ""

            with patch("ceq_api.auth.janua._get_jwks_client", return_value=None):
                with patch("ceq_api.auth.janua.get_janua_client", return_value=mock_client):
                    user = await validate_token("some-token")

        assert user is not None
        assert user.email == "introspection@test.com"

    @pytest.mark.asyncio
    async def test_circuit_breaker_open_skips_jwks(self):
        """When JWKS circuit breaker is open, should skip JWKS and use introspection."""
        user_id = str(uuid4())

        # Force breaker open
        _jwks_breaker._is_open = True
        _jwks_breaker._last_failure_time = time.monotonic()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "id": user_id,
            "email": "breaker-open@test.com",
            "roles": ["user"],
        }

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)

        mock_local = MagicMock()

        with patch("ceq_api.auth.janua.settings") as mock_settings:
            mock_settings.janua_enabled = True

            with patch("ceq_api.auth.janua._validate_token_local", mock_local):
                with patch("ceq_api.auth.janua.get_janua_client", return_value=mock_client):
                    user = await validate_token("some-token")

        assert user is not None
        assert user.email == "breaker-open@test.com"
        mock_local.assert_not_called()

    @pytest.mark.asyncio
    async def test_introspection_timeout_returns_none(self):
        """When both JWKS and introspection fail, should return None."""
        mock_jwks = MagicMock()
        mock_jwks.get_signing_key.side_effect = PyJWKClientError("JWKS down")

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=httpx.TimeoutException("timeout"))

        with patch("ceq_api.auth.janua.settings") as mock_settings:
            mock_settings.janua_enabled = True
            mock_settings.janua_jwks_url = "https://auth.madfam.io/.well-known/jwks.json"
            mock_settings.janua_issuer = ""
            mock_settings.janua_audience = ""

            with patch("ceq_api.auth.janua._get_jwks_client", return_value=mock_jwks):
                with patch("ceq_api.auth.janua.get_janua_client", return_value=mock_client):
                    user = await validate_token("any-token")

        assert user is None

    @pytest.mark.asyncio
    async def test_introspection_connection_error_returns_none(self):
        """Connection error during introspection fallback should return None."""
        mock_jwks = MagicMock()
        mock_jwks.get_signing_key.side_effect = PyJWKClientError("JWKS unreachable")

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=httpx.ConnectError("connection refused"))

        with patch("ceq_api.auth.janua.settings") as mock_settings:
            mock_settings.janua_enabled = True
            mock_settings.janua_jwks_url = "https://auth.madfam.io/.well-known/jwks.json"
            mock_settings.janua_issuer = ""
            mock_settings.janua_audience = ""

            with patch("ceq_api.auth.janua._get_jwks_client", return_value=mock_jwks):
                with patch("ceq_api.auth.janua.get_janua_client", return_value=mock_client):
                    user = await validate_token("any-token")

        assert user is None

    @pytest.mark.asyncio
    async def test_invalid_claims_with_jwks_configured_no_fallback(
        self, rsa_public_key, rsa_private_key
    ):
        """Token with valid signature but bad claims should not fall back."""
        private_pem = rsa_private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
        # Token with no sub or email
        token = pyjwt.encode(
            {"exp": int(time.time()) + 3600, "iat": int(time.time())},
            private_pem,
            algorithm="RS256",
            headers={"kid": "test-kid-1"},
        )

        mock_jwks = MagicMock()
        mock_jwks.get_signing_key.return_value = rsa_public_key

        mock_introspection = AsyncMock()

        with patch("ceq_api.auth.janua.settings") as mock_settings:
            mock_settings.janua_enabled = True
            mock_settings.janua_jwks_url = "https://auth.madfam.io/.well-known/jwks.json"
            mock_settings.janua_issuer = ""
            mock_settings.janua_audience = ""

            with patch("ceq_api.auth.janua._get_jwks_client", return_value=mock_jwks):
                with patch(
                    "ceq_api.auth.janua._validate_token_introspection",
                    mock_introspection,
                ):
                    user = await validate_token(token)

        assert user is None
        mock_introspection.assert_not_called()


# ---------------------------------------------------------------------------
# FastAPI Dependencies
# ---------------------------------------------------------------------------

class TestGetCurrentUser:
    """Tests for get_current_user dependency."""

    @pytest.mark.asyncio
    async def test_get_current_user_disabled(self):
        """When Janua is disabled, should return mock user."""
        mock_request = MagicMock()

        with patch("ceq_api.auth.janua.settings") as mock_settings:
            mock_settings.janua_enabled = False

            user = await get_current_user(mock_request, None)

            assert user is not None
            assert user.email == "dev@ceq.local"

    @pytest.mark.asyncio
    async def test_get_current_user_no_credentials(self):
        """Missing credentials should raise 401."""
        mock_request = MagicMock()

        with patch("ceq_api.auth.janua.settings") as mock_settings:
            mock_settings.janua_enabled = True

            with pytest.raises(HTTPException) as exc_info:
                await get_current_user(mock_request, None)

            assert exc_info.value.status_code == 401
            assert "Authentication required" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_get_current_user_invalid_token(self):
        """Invalid token should raise 401."""
        mock_request = MagicMock()
        mock_credentials = MagicMock()
        mock_credentials.credentials = "invalid-token"

        with patch("ceq_api.auth.janua.settings") as mock_settings:
            mock_settings.janua_enabled = True
            with patch("ceq_api.auth.janua.validate_token", return_value=None):
                with pytest.raises(HTTPException) as exc_info:
                    await get_current_user(mock_request, mock_credentials)

                assert exc_info.value.status_code == 401
                assert "Invalid credentials" in exc_info.value.detail


class TestGetOptionalUser:
    """Tests for get_optional_user dependency."""

    @pytest.mark.asyncio
    async def test_get_optional_user_no_credentials(self):
        """No credentials should return None."""
        user = await get_optional_user(None)
        assert user is None

    @pytest.mark.asyncio
    async def test_get_optional_user_valid_token(self):
        """Valid token should return user."""
        mock_credentials = MagicMock()
        mock_credentials.credentials = "valid-token"

        expected_user = JanuaUser(
            id=uuid4(),
            email="test@test.com",
            roles=["user"],
        )

        with patch("ceq_api.auth.janua.validate_token", return_value=expected_user):
            user = await get_optional_user(mock_credentials)

            assert user is not None
            assert user.email == expected_user.email


class TestRequireAdmin:
    """Tests for require_admin dependency."""

    def test_require_admin_with_admin_user(self, mock_admin_user):
        """Admin user should pass through."""
        result = require_admin(mock_admin_user)
        assert result == mock_admin_user

    def test_require_admin_with_regular_user(self, mock_user):
        """Regular user should raise 403."""
        with pytest.raises(HTTPException) as exc_info:
            require_admin(mock_user)

        assert exc_info.value.status_code == 403
        assert "Admin access required" in exc_info.value.detail


# ---------------------------------------------------------------------------
# Integration Tests
# ---------------------------------------------------------------------------

class TestAuthEndpoints:
    """Integration tests for auth-protected endpoints."""

    def test_protected_endpoint_without_auth(self, client):
        """Accessing protected endpoint without auth should work when Janua disabled."""
        # In test mode, auth is mocked, so this should work
        response = client.get("/v1/workflows/")
        assert response.status_code == 200

    def test_protected_endpoint_with_mock_user(self, client):
        """Protected endpoint should work with mock user."""
        response = client.get("/v1/workflows/")
        assert response.status_code == 200
        assert "workflows" in response.json()
