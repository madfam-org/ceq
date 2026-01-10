"""Tests for Janua authentication integration."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import httpx
from fastapi import HTTPException

from ceq_api.auth.janua import (
    JanuaUser,
    validate_token,
    get_current_user,
    get_optional_user,
    require_auth,
    require_admin,
)


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


class TestValidateToken:
    """Tests for token validation."""

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
    async def test_validate_token_success(self):
        """Valid token should return user data."""
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

        with patch("ceq_api.auth.janua.settings") as mock_settings:
            mock_settings.janua_enabled = True
            with patch("ceq_api.auth.janua.get_janua_client", return_value=mock_client):
                user = await validate_token("valid-token")

                assert user is not None
                assert user.email == "valid@test.com"
                assert str(user.id) == user_id

    @pytest.mark.asyncio
    async def test_validate_token_invalid(self):
        """Invalid token should return None."""
        mock_response = MagicMock()
        mock_response.status_code = 401

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch("ceq_api.auth.janua.settings") as mock_settings:
            mock_settings.janua_enabled = True
            with patch("ceq_api.auth.janua.get_janua_client", return_value=mock_client):
                user = await validate_token("invalid-token")

                assert user is None

    @pytest.mark.asyncio
    async def test_validate_token_timeout(self):
        """Timeout should return None and log error."""
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=httpx.TimeoutException("timeout"))

        with patch("ceq_api.auth.janua.settings") as mock_settings:
            mock_settings.janua_enabled = True
            with patch("ceq_api.auth.janua.get_janua_client", return_value=mock_client):
                user = await validate_token("any-token")

                assert user is None

    @pytest.mark.asyncio
    async def test_validate_token_connection_error(self):
        """Connection error should return None and log error."""
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=httpx.ConnectError("connection failed"))

        with patch("ceq_api.auth.janua.settings") as mock_settings:
            mock_settings.janua_enabled = True
            with patch("ceq_api.auth.janua.get_janua_client", return_value=mock_client):
                user = await validate_token("any-token")

                assert user is None

    @pytest.mark.asyncio
    async def test_validate_token_invalid_response_data(self):
        """Invalid response data should return None."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"invalid": "data"}  # Missing required fields

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch("ceq_api.auth.janua.settings") as mock_settings:
            mock_settings.janua_enabled = True
            with patch("ceq_api.auth.janua.get_janua_client", return_value=mock_client):
                user = await validate_token("any-token")

                assert user is None


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
