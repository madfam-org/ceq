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
from collections.abc import Iterable
from dataclasses import dataclass
from functools import lru_cache
from typing import Annotated, Any
from uuid import UUID, uuid5

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

# Namespace for deriving a stable synthetic principal id from a Janua client_id.
# A service principal has NO row in any user table, but `JanuaUser.id` is written
# to `jobs.user_id` / `outputs.user_id` / credit-ledger rows, so it must be a UUID
# and it must be STABLE across token re-mints — otherwise a batch driver's own
# jobs would become invisible to it after each ~1h token refresh. UUIDv5 over the
# client_id gives exactly that: deterministic, collision-free, and never colliding
# with a Janua-issued human user id (different namespace, random v4).
SERVICE_PRINCIPAL_NAMESPACE = UUID("ce900000-0000-5ce9-9ce9-000000000001")


@dataclass
class JanuaUser:
    """Authenticated principal from Janua.

    Two shapes flow through this type:

    - **Human user** — an authorization_code token. ``id`` is the Janua user
      UUID (``sub``); ``client_id``/``scopes`` are None/empty.
    - **Service principal** — a ``client_credentials`` token (machine-to-machine,
      no browser session). ``is_service_principal`` is True, ``client_id`` holds
      the Janua confidential-client id, ``scopes`` holds the granted scopes, and
      ``id`` is a deterministic UUIDv5 derived from ``client_id`` (there is no
      user row behind it — see ``SERVICE_PRINCIPAL_NAMESPACE``).

    Everything user-shaped (``email``, ``org_id``, ``roles``) is still populated
    for service principals from the token's own claims, so existing code paths
    that read them keep working unchanged.
    """

    id: UUID
    email: str
    org_id: UUID | None = None
    roles: list[str] | None = None
    entitlements: list[str] | None = None
    # Service-principal fields. Absent/empty for human users — the additive
    # contract is that nothing about a human token's mapping changed.
    client_id: str | None = None
    scopes: frozenset[str] = frozenset()
    is_service_principal: bool = False

    @property
    def is_admin(self) -> bool:
        """Check if user has admin role."""
        return self.roles is not None and "admin" in self.roles

    @property
    def principal_key(self) -> str:
        """Stable rate-limiter / logging identity for this principal.

        Service principals key on ``client_id`` so they land in their own
        limiter bucket rather than sharing the human-user bucket namespace.
        """
        if self.is_service_principal and self.client_id:
            return f"service:{self.client_id}"
        return f"user:{self.id}"

    def has_scope(self, scope: str) -> bool:
        """Whether this principal was granted ``scope``.

        Human users are not scope-gated by this helper (they authorize through
        roles/entitlements), so this only ever returns True for a scope the
        token actually carries.
        """
        return scope in self.scopes


def service_principal_id(client_id: str) -> UUID:
    """Deterministic synthetic principal UUID for a Janua machine client."""
    return uuid5(SERVICE_PRINCIPAL_NAMESPACE, client_id)


def _normalize_scopes(value: Any) -> frozenset[str]:
    """Normalize an OAuth ``scope`` claim into a set.

    Janua emits a space-delimited string (RFC 6749 §3.3); some issuers emit a
    list. Both are accepted.
    """
    if value is None:
        return frozenset()
    if isinstance(value, str):
        return frozenset(part for part in value.split() if part)
    if isinstance(value, Iterable) and not isinstance(value, (bytes, bytearray, dict)):
        return frozenset(str(part).strip() for part in value if str(part).strip())
    return frozenset()


def _is_client_credentials_payload(payload: dict[str, Any]) -> bool:
    """Whether a decoded Janua JWT is a machine (client_credentials) token.

    Janua's ``_get_client_credentials_claims`` stamps BOTH ``token_use`` and
    ``actor_type``; we accept either marker so a claim-set tweak upstream does
    not silently drop machine callers to the human path (where ``UUID(sub)``
    would blow up on ``service-account:<client_id>``).
    """
    return (
        payload.get("token_use") == "client_credentials"
        or payload.get("actor_type") == "service_account"
    )


def _normalize_roles(value: Any) -> list[str] | None:
    """Normalize user roles from token claims into a list of strings."""
    if value is None:
        return None

    if isinstance(value, str):
        values = [value]
    elif isinstance(value, Iterable) and not isinstance(value, (bytes, bytearray, dict)):
        values = list(value)
    else:
        values = [value]

    roles = [
        str(role).strip().lower().replace("_", "-")
        for role in values
        if isinstance(role, (str, UUID, int, float)) and not isinstance(role, dict)
    ]
    return roles if roles else None


def _normalize_entitlements(value: Any) -> list[str] | None:
    """Normalize entitlement claims from token payloads into a list of strings."""
    if value is None:
        return None

    values = value

    if isinstance(value, dict):
        nested = value.get("id") or value.get("slug") or value.get("name")
        if nested is None:
            return None
        values = nested

    if isinstance(value, str):
        values = [value]
    elif isinstance(value, Iterable) and not isinstance(value, (bytes, bytearray, dict)):
        values = list(value)
    else:
        values = [value]

    entitlements = [
        str(entitlement).strip().lower().replace("_", "-")
        for entitlement in values
        if isinstance(entitlement, (str, UUID, int, float))
        and not isinstance(entitlement, dict)
        and str(entitlement).strip()
    ]
    return entitlements if entitlements else None


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
    """Validate token via Janua userinfo/introspection endpoints.

    Janua-compatible behavior is to expose user details at
    ``/api/v1/oauth/userinfo``. ``/api/v1/auth/me`` is retained as a
    compatibility fallback for environments still emitting the legacy endpoint.

    This fallback is network-bound (~50-200ms), so it only runs when JWKS is
    unavailable.
    """
    client = get_janua_client()
    headers = {"Authorization": f"Bearer {token}"}
    endpoints = ("/api/v1/oauth/userinfo", "/api/v1/auth/me")

    for endpoint in endpoints:
        response = await client.get(endpoint, headers=headers)
        if response.status_code != 200:
            logger.debug(
                "Introspection endpoint %s returned status %s", endpoint, response.status_code
            )
            continue

        data = response.json()
        user_id = data.get("id") or data.get("sub")
        email = data.get("email")
        if not user_id or not email:
            logger.debug("Introspection response missing required fields: %s", data)
            return None

        roles_raw = data.get("roles")
        if roles_raw is None:
            roles_raw = data.get("role")

        entitlements = _normalize_entitlements(
            data.get("entitlements")
            or data.get("plan")
            or data.get("plan_id")
            or data.get("subscription")
            or data.get("subscription_tier")
        )
        if entitlements is None:
            plans = data.get("plans")
            if isinstance(plans, list):
                entitlements = _normalize_entitlements(plans)

        user = JanuaUser(
            id=UUID(user_id),
            email=email,
            org_id=UUID(data["org_id"]) if data.get("org_id") else None,
            roles=_normalize_roles(roles_raw),
            entitlements=entitlements,
        )
        logger.debug("Token validated via introspection for user %s", user.email)
        return user

    logger.debug("Token introspection did not validate against any endpoint")
    return None


# ---------------------------------------------------------------------------
# Local JWKS RS256 validation (primary, <1ms)
# ---------------------------------------------------------------------------

class ServicePrincipalRejectedError(Exception):
    """A verified client_credentials token could not be accepted.

    Terminal: there is no user behind a machine token, so falling back to
    introspection (a *userinfo* lookup) can never rescue it.
    """


def _service_principal_from_payload(payload: dict[str, Any]) -> JanuaUser | None:
    """Map a verified Janua ``client_credentials`` payload to a service principal.

    The token's signature, issuer and **audience** were already verified by the
    caller's ``jwt.decode`` — audience is what binds the machine client to ceq
    specifically, so a token minted for another product's audience never gets
    this far.

    Returns None (-> 401) when the machine path is disabled or the claim set is
    unusable. Scope authorization is deliberately NOT done here: a valid machine
    token *authenticates*, and the per-endpoint dependency
    (``get_service_or_user``) decides *authorization* — so a scope miss surfaces
    as a 403 rather than a 401.
    """
    if not settings.service_principals_enabled:
        logger.warning(
            "Rejected client_credentials token: service principals disabled "
            "(SERVICE_PRINCIPALS_ENABLED=false)"
        )
        return None

    client_id = payload.get("client_id")
    if not client_id:
        # Fall back to the `service-account:<client_id>` sub form.
        sub = str(payload.get("sub") or "")
        if sub.startswith("service-account:"):
            client_id = sub.split(":", 1)[1]
    if not client_id:
        logger.warning("client_credentials token missing client_id/sub identity")
        return None

    client_id = str(client_id)
    org_id_raw = payload.get("org_id") or payload.get("tenant_id")
    org_id: UUID | None = None
    if org_id_raw:
        try:
            org_id = UUID(str(org_id_raw))
        except (ValueError, AttributeError, TypeError):
            logger.debug("client_credentials token carried non-UUID org_id %r", org_id_raw)

    principal = JanuaUser(
        id=service_principal_id(client_id),
        email=str(payload.get("email") or f"{client_id}@service.auth.madfam.io"),
        org_id=org_id,
        roles=_normalize_roles(payload.get("roles")),
        entitlements=_normalize_entitlements(
            payload.get("entitlements") or payload.get("tier")
        ),
        client_id=client_id,
        scopes=_normalize_scopes(payload.get("scope")),
        is_service_principal=True,
    )
    logger.debug(
        "Token validated locally (JWKS) for service principal %s (scopes=%s)",
        client_id,
        sorted(principal.scopes),
    )
    return principal


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

    # --- Service principal (client_credentials) branch -------------------
    # Machine tokens carry `sub: "service-account:<client_id>"`, which is not a
    # UUID; they must never reach the human mapping below. This branch is
    # TERMINAL: a machine token that this branch rejects raises
    # ServicePrincipalRejectedError rather than returning None, so `validate_token`
    # does not waste an introspection round-trip asking Janua's *userinfo*
    # endpoint about a token that has no user behind it.
    if _is_client_credentials_payload(payload):
        principal = _service_principal_from_payload(payload)
        if principal is None:
            raise ServicePrincipalRejectedError
        return principal

    # Extract user from JWT claims
    sub = payload.get("sub")
    email = payload.get("email")

    if not sub or not email:
        logger.warning("JWT missing required claims (sub, email)")
        return None

    entitlements = _normalize_entitlements(
        payload.get("entitlements")
        or payload.get("plan")
        or payload.get("plan_id")
        or payload.get("subscription")
        or payload.get("subscription_tier")
    )
    if entitlements is None:
        plans = payload.get("plans")
        if isinstance(plans, list):
            entitlements = _normalize_entitlements(plans)

    user = JanuaUser(
        id=UUID(sub),
        email=email,
        org_id=UUID(payload["org_id"]) if payload.get("org_id") else None,
        roles=_normalize_roles(payload.get("roles")) or _normalize_roles(payload.get("role")),
        entitlements=entitlements,
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
         Used when JWKS is unavailable, circuit breaker is open, or local
         validation produces no usable user payload.

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
            # JWKS was configured and decoded token but did not produce a user.
            # Fall through to introspection for claim-shape or identity
            # normalization fallback.
        except ServicePrincipalRejectedError:
            # Terminal by construction — a machine token has no user to look up.
            # Not a JWKS failure, so the breaker is untouched.
            _jwks_breaker.record_success()
            return None
        except jwt.ExpiredSignatureError:
            logger.debug("JWT expired (local validation)")
            return None
        except (jwt.InvalidAudienceError, jwt.InvalidIssuerError):
            logger.debug("JWT claim mismatch (local validation)")
        except jwt.InvalidTokenError as e:
            # Covers DecodeError, InvalidSignatureError, etc.
            logger.debug(f"JWT invalid for local validation; falling back to introspection: {e}")
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

    # A machine token authenticates, but `get_current_user` is the *human*
    # dependency: it backs user-specific surfaces (workflows, assets, credits,
    # outputs, operations) where "the current user" means a person with a row.
    # Service principals must opt in per-endpoint via `get_service_or_user`
    # so that adding the machine path never silently widens an existing route.
    if user.is_service_principal:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "Service credentials are not accepted on this endpoint. "
                "Machine callers are limited to the render, jobs, and template "
                "surfaces."
            ),
        )

    return user


async def get_service_or_user(
    request: Request,
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Depends(bearer_scheme),
    ] = None,
) -> JanuaUser:
    """Authenticate a human user **or** a Janua service principal.

    This is the dependency for the machine-reachable surface (render, jobs,
    templates). Behavior:

    - Human token -> identical to ``get_current_user`` (no change at all).
    - ``client_credentials`` token -> accepted only when it carries the
      configured scope (``SERVICE_PRINCIPAL_SCOPE``, default ``ceq:render``).
      A valid token without that scope is a **403**, not a 401: it authenticated
      fine, it just is not authorized here.

    Audience is enforced upstream in the JWKS decode (``JANUA_AUDIENCE``), so a
    machine token minted for a different product never reaches this check.
    """
    # Dev-mode / no-credentials / invalid-token handling is identical to the
    # human path, so reuse it — but bypass its service-principal rejection.
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

    principal = await validate_token(credentials.credentials)

    if principal is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials. Signal corrupted.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if principal.is_service_principal:
        required = settings.service_principal_scope
        if required and not principal.has_scope(required):
            logger.warning(
                "Service principal %s denied: missing scope %r (has %s)",
                principal.client_id,
                required,
                sorted(principal.scopes),
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"Service credentials lack the required scope {required!r}."
                ),
            )
        # Surface the machine identity to the limiter key function and request
        # logs. `request.state.user_id` stays unset for service principals so
        # they never share the human-user limiter bucket.
        request.state.service_client_id = principal.client_id

    return principal


async def get_optional_user(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Depends(bearer_scheme),
    ] = None,
) -> JanuaUser | None:
    """
    Get the current **human** user if authenticated, None otherwise.

    Used for endpoints that work with or without auth. Service principals are
    treated as anonymous here rather than as a user: an optional-auth endpoint
    that personalizes on "is there a user?" must not start personalizing for a
    machine client. Machine callers use ``get_service_or_user`` instead.
    """
    if credentials is None:
        return None

    principal = await validate_token(credentials.credentials)
    if principal is not None and principal.is_service_principal:
        return None
    return principal


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
