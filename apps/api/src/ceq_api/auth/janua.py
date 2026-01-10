"""Janua authentication integration for ceq-api."""

import logging
from dataclasses import dataclass
from functools import lru_cache
from typing import Annotated
from uuid import UUID

import httpx
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from ceq_api.config import get_settings
from ceq_api.resilience import (
    CircuitBreakerError,
    janua_circuit,
    retry_with_backoff,
    JANUA_RETRY_CONFIG,
)

logger = logging.getLogger(__name__)
settings = get_settings()

# Security scheme
bearer_scheme = HTTPBearer(auto_error=False)


@dataclass
class JanuaUser:
    """Authenticated user from Janua."""

    id: UUID
    email: str
    org_id: UUID | None = None
    roles: list[str] | None = None

    @property
    def is_admin(self) -> bool:
        """Check if user has admin role."""
        return self.roles is not None and "admin" in self.roles


@lru_cache
def get_janua_client() -> httpx.AsyncClient:
    """Get cached HTTP client for Janua API."""
    return httpx.AsyncClient(
        base_url=settings.janua_api_url,
        timeout=10.0,
    )


async def _validate_token_impl(token: str) -> JanuaUser | None:
    """Internal token validation with retry support."""
    client = get_janua_client()
    response = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )

    if response.status_code != 200:
        logger.debug(f"Token validation failed: status {response.status_code}")
        return None

    data = response.json()
    user = JanuaUser(
        id=UUID(data["id"]),
        email=data["email"],
        org_id=UUID(data["org_id"]) if data.get("org_id") else None,
        roles=data.get("roles"),
    )
    logger.debug(f"Token validated for user {user.email}")
    return user


async def validate_token(token: str) -> JanuaUser | None:
    """
    Validate a JWT token with Janua.

    Uses circuit breaker and retry logic for reliability.
    Returns the user if valid, None if invalid.
    """
    if not settings.janua_enabled:
        # Development mode - return a mock user
        logger.debug("Auth disabled - returning mock user")
        return JanuaUser(
            id=UUID("00000000-0000-0000-0000-000000000001"),
            email="dev@ceq.local",
            org_id=None,
            roles=["user"],
        )

    try:
        # Use circuit breaker with retry
        async def do_validate():
            return await retry_with_backoff(
                _validate_token_impl,
                JANUA_RETRY_CONFIG,
                token,
            )

        return await janua_circuit.call(do_validate)

    except CircuitBreakerError as e:
        logger.warning(f"Janua circuit breaker open: {e}")
        return None
    except httpx.TimeoutException:
        logger.error("Janua API timeout during token validation")
        return None
    except httpx.ConnectError as e:
        logger.error(f"Failed to connect to Janua API: {e}")
        return None
    except ValueError as e:
        logger.warning(f"Invalid response data from Janua: {e}")
        return None
    except Exception as e:
        logger.exception(f"Unexpected error during token validation: {e}")
        return None


async def get_current_user(
    request: Request,
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Depends(bearer_scheme),
    ] = None,
) -> JanuaUser:
    """
    Get the current authenticated user.

    Used as a FastAPI dependency:

        @router.get("/me")
        async def get_me(user: JanuaUser = Depends(get_current_user)):
            return {"id": user.id, "email": user.email}
    """
    # Development mode - bypass auth with mock user
    if not settings.janua_enabled:
        return JanuaUser(
            id=UUID("00000000-0000-0000-0000-000000000001"),
            email="dev@ceq.local",
            org_id=None,
            roles=["user"],
        )

    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Signal lost. Authentication required.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = await validate_token(credentials.credentials)

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials. Signal corrupted.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user


async def get_optional_user(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Depends(bearer_scheme),
    ] = None,
) -> JanuaUser | None:
    """
    Get the current user if authenticated, None otherwise.
    
    Used for endpoints that work with or without auth.
    """
    if credentials is None:
        return None

    return await validate_token(credentials.credentials)


def require_auth(user: Annotated[JanuaUser, Depends(get_current_user)]) -> JanuaUser:
    """
    Require authentication (alias for get_current_user).
    
    More explicit dependency for protected endpoints:
    
        @router.post("/workflows")
        async def create_workflow(user: JanuaUser = Depends(require_auth)):
            ...
    """
    return user


def require_admin(user: Annotated[JanuaUser, Depends(get_current_user)]) -> JanuaUser:
    """
    Require admin role.
    
        @router.delete("/templates/{id}")
        async def delete_template(user: JanuaUser = Depends(require_admin)):
            ...
    """
    if not user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions. Admin access required.",
        )
    return user
