"""Janua authentication integration for ceq-api.

Validates JWTs issued by Janua (auth.madfam.io) using RS256 asymmetric keys
via local JWKS validation. Falls back to introspection (GET /api/v1/auth/me)
when JWKS is unavailable, providing sub-millisecond auth in the common case
while maintaining reliability through circuit breaker patterns.

Migration: PR-1E (introspection -> local JWKS RS256 validation)
"""

import logging
import threading
import time
from dataclasses import dataclass
from functools import lru_cache
from typing import Annotated, Any
from uuid import UUID

import httpx
import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWKClient, PyJWKClientError

from ceq_api.config import get_settings
from ceq_api.resilience import (
    JANUA_RETRY_CONFIG,
    CircuitBreakerError,
    janua_circuit,
    retry_with_backoff,
)

logger = logging.getLogger(__name__)
settings = get_settings()

# Security scheme
bearer_scheme = HTTPBearer(auto_error=False)


# ---------------------------------------------------------------------------
# JWKS Client with circuit breaker for key fetching
# ---------------------------------------------------------------------------

class JWKSCircuitBreaker:
    """Lightweight circuit breaker specifically for JWKS key fetch failures.

    When JWKS endpoint is unreachable, the breaker opens and validation
    falls back to the existing introspection method. The breaker auto-resets
    after ``reset_timeout`` seconds to re-attempt local validation.
    """

    def __init__(self, failure_threshold: int = 3, reset_timeout: float = 60.0):
        self._failure_threshold = failure_threshold
        self._reset_timeout = reset_timeout
        self._failure_count = 0
        self._last_failure_time: float = 0.0
        self._is_open = False
        self._lock = threading.Lock()

    @property
    def is_open(self) -> bool:
        """Check if breaker is open (JWKS unavailable)."""
        if not self._is_open:
            return False
        # Check if enough time has passed to try again (half-open)
        elapsed = time.monotonic() - self._last_failure_time
        if elapsed >= self._reset_timeout:
            with self._lock:
                self._is_open = False
                self._failure_count = 0
            logger.info("JWKS circuit breaker reset -> attempting local validation again")
            return False
        return True

    def record_failure(self) -> None:
        """Record a JWKS fetch failure."""
        with self._lock:
            self._failure_count += 1
            self._last_failure_time = time.monotonic()
            if self._failure_count >= self._failure_threshold:
                if not self._is_open:
                    logger.warning(
                        f"JWKS circuit breaker OPEN after {self._failure_count} failures. "
                        f"Falling back to introspection for {self._reset_timeout}s."
                    )
                self._is_open = True

    def record_success(self) -> None:
        """Record a successful JWKS operation, resetting failure count."""
        with self._lock:
            if self._failure_count > 0:
                logger.info("JWKS circuit breaker reset after successful key fetch")
            self._failure_count = 0
            self._is_open = False


# Module-level JWKS circuit breaker instance
_jwks_breaker = JWKSCircuitBreaker(failure_threshold=3, reset_timeout=60.0)


class CachedJWKSClient:
    """Thread-safe JWKS client with 1-hour key cache.

    Wraps PyJWT's ``PyJWKClient`` and adds a TTL cache for the signing key
    to avoid hitting the JWKS endpoint on every request. The JWKS endpoint
    is only contacted when:
      - No cached key exists
      - The cached key has expired (default 1 hour)
      - The ``kid`` in the incoming token doesn't match the cached key

    Performance target: <1ms for cached key lookup (local crypto only).
    """

    def __init__(
        self,
        jwks_url: str,
        cache_ttl: int = 3600,
        lifespan: int = 3600,
    ):
        self._jwks_url = jwks_url
        self._cache_ttl = cache_ttl
        self._client = PyJWKClient(
            uri=jwks_url,
            cache_jwk_set=True,
            lifespan=lifespan,
        )
        self._cached_keys: dict[str, tuple[Any, float]] = {}
        self._lock = threading.Lock()

    def get_signing_key(self, token: str) -> Any:
        """Get the signing key for a token, using cache when possible.

        Args:
            token: The raw JWT string.

        Returns:
            The RSA public key for verification.

        Raises:
            PyJWKClientError: If JWKS endpoint is unreachable or kid not found.
            jwt.DecodeError: If the token header cannot be parsed.
        """
        # Decode header to get kid without verifying signature
        header = jwt.get_unverified_header(token)
        kid = header.get("kid")

        if kid:
            with self._lock:
                cached = self._cached_keys.get(kid)
                if cached is not None:
                    key, cached_at = cached
                    if (time.monotonic() - cached_at) < self._cache_ttl:
                        return key

        # Fetch from JWKS endpoint
        signing_key = self._client.get_signing_key_from_jwt(token)
        key = signing_key.key

        if kid:
            with self._lock:
                self._cached_keys[kid] = (key, time.monotonic())

        return key


@lru_cache
def _get_jwks_client() -> CachedJWKSClient | None:
    """Get the JWKS client singleton, or None if JWKS is not configured."""
    jwks_url = settings.janua_jwks_url
    if not jwks_url:
        logger.info("JANUA_JWKS_URL not configured - using introspection only")
        return None
    logger.info(f"JWKS client initialized: {jwks_url}")
    return CachedJWKSClient(jwks_url=jwks_url)


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Introspection client (legacy, used as fallback)
# ---------------------------------------------------------------------------

@lru_cache
def get_janua_client() -> httpx.AsyncClient:
    """Get cached HTTP client for Janua API."""
    return httpx.AsyncClient(
        base_url=settings.janua_api_url,
        timeout=10.0,
    )


async def _validate_token_introspection(token: str) -> JanuaUser | None:
    """Validate token via Janua introspection endpoint (GET /api/v1/auth/me).

    This is the legacy validation method. It makes a network call on every
    request (~50-200ms). Kept as a fallback when JWKS is unavailable.
    """
    client = get_janua_client()
    response = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )

    if response.status_code != 200:
        logger.debug(f"Introspection validation failed: status {response.status_code}")
        return None

    data = response.json()
    user = JanuaUser(
        id=UUID(data["id"]),
        email=data["email"],
        org_id=UUID(data["org_id"]) if data.get("org_id") else None,
        roles=data.get("roles"),
    )
    logger.debug(f"Token validated via introspection for user {user.email}")
    return user


# ---------------------------------------------------------------------------
# Local JWKS RS256 validation (primary, <1ms)
# ---------------------------------------------------------------------------

def _validate_token_local(token: str) -> JanuaUser | None:
    """Validate token locally using JWKS RS256 public keys.

    Decodes and verifies the JWT signature using the public key from the
    JWKS endpoint (cached). This is purely a local crypto operation after
    the initial key fetch, completing in <1ms.

    Returns:
        JanuaUser if the token is valid, None if the token is invalid
        (expired, bad signature, missing claims).

    Raises:
        PyJWKClientError: If the JWKS endpoint cannot be reached (triggers
        circuit breaker fallback to introspection).
    """
    jwks_client = _get_jwks_client()
    if jwks_client is None:
        return None  # JWKS not configured, caller should use introspection

    # Get signing key - may raise PyJWKClientError on network failure
    key = jwks_client.get_signing_key(token)

    # Build decode kwargs
    decode_kwargs: dict[str, Any] = {
        "algorithms": ["RS256"],
    }
    options: dict[str, Any] = {}

    # Add issuer validation if configured
    if settings.janua_issuer:
        decode_kwargs["issuer"] = settings.janua_issuer
    else:
        options["verify_iss"] = False

    # Add audience validation if configured
    if settings.janua_audience:
        decode_kwargs["audience"] = settings.janua_audience
    else:
        options["verify_aud"] = False

    if options:
        decode_kwargs["options"] = options

    payload = jwt.decode(
        token,
        key,
        **decode_kwargs,
    )

    # Extract user from JWT claims
    sub = payload.get("sub")
    email = payload.get("email")

    if not sub or not email:
        logger.warning("JWT missing required claims (sub, email)")
        return None

    user = JanuaUser(
        id=UUID(sub),
        email=email,
        org_id=UUID(payload["org_id"]) if payload.get("org_id") else None,
        roles=payload.get("roles"),
    )
    logger.debug(f"Token validated locally (JWKS) for user {user.email}")
    return user


# ---------------------------------------------------------------------------
# Unified validation with fallback
# ---------------------------------------------------------------------------

async def validate_token(token: str) -> JanuaUser | None:
    """
    Validate a JWT token issued by Janua.

    Strategy (ordered by preference):
      1. Local JWKS RS256 validation (<1ms, no network call)
      2. Introspection fallback (GET /api/v1/auth/me, ~50-200ms)
         Used when JWKS is unavailable or circuit breaker is open.

    The JWKS circuit breaker opens after 3 consecutive JWKS fetch failures
    and resets after 60 seconds, at which point local validation is retried.

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

    # --- Attempt 1: Local JWKS validation (fast path) ---
    if not _jwks_breaker.is_open:
        try:
            user = _validate_token_local(token)
            if user is not None:
                _jwks_breaker.record_success()
                return user
            # user is None means either JWKS not configured or invalid claims.
            # If JWKS is configured, the token itself was invalid (bad claims).
            jwks_client = _get_jwks_client()
            if jwks_client is not None:
                # JWKS is configured and token decoded but claims were bad
                # -> don't fallback to introspection, the token is genuinely invalid
                return None
            # JWKS not configured -> fall through to introspection
        except jwt.ExpiredSignatureError:
            logger.debug("JWT expired (local validation)")
            return None
        except jwt.InvalidAudienceError:
            logger.debug("JWT audience mismatch (local validation)")
            return None
        except jwt.InvalidIssuerError:
            logger.debug("JWT issuer mismatch (local validation)")
            return None
        except jwt.InvalidTokenError as e:
            # Covers InvalidSignatureError, DecodeError, etc.
            logger.debug(f"JWT invalid (local validation): {e}")
            return None
        except PyJWKClientError as e:
            # JWKS endpoint unreachable - trigger circuit breaker
            logger.warning(f"JWKS fetch failed, falling back to introspection: {e}")
            _jwks_breaker.record_failure()
        except Exception as e:
            # Unexpected error in local validation - log and fallback
            logger.warning(f"Unexpected error in local JWKS validation: {e}")
            _jwks_breaker.record_failure()
    else:
        logger.debug("JWKS circuit breaker open - using introspection fallback")

    # --- Attempt 2: Introspection fallback (slow path) ---
    try:
        async def do_introspection():
            return await retry_with_backoff(
                _validate_token_introspection,
                JANUA_RETRY_CONFIG,
                token,
            )

        return await janua_circuit.call(do_introspection)

    except CircuitBreakerError as e:
        logger.warning(f"Janua circuit breaker open: {e}")
        return None
    except httpx.TimeoutException:
        logger.error("Janua API timeout during introspection fallback")
        return None
    except httpx.ConnectError as e:
        logger.error(f"Failed to connect to Janua API: {e}")
        return None
    except ValueError as e:
        logger.warning(f"Invalid response data from Janua: {e}")
        return None
    except Exception as e:
        logger.exception(f"Unexpected error during introspection fallback: {e}")
        return None


# ---------------------------------------------------------------------------
# FastAPI dependencies (unchanged public API)
# ---------------------------------------------------------------------------

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
