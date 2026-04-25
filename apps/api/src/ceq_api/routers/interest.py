"""POST /v1/interest/ — feature-interest capture (InterestGate backend).

Public, unauthenticated, rate-limited. Stands in for paywall/checkout while
the studio is in the WTP-discovery phase. Captures email + feature_key (+ an
optional wishlist) so we can build a warm waitlist before flipping the gate
to real billing.

Idempotent on (email, feature_key):
- New row    -> 201 Created   {status: "registered"}
- Duplicate  -> 200 OK        {status: "already_registered"}
- CRM dispatch is enqueued only on the first registration.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Annotated, Any

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    HTTPException,
    Request,
    status,
)
from pydantic import BaseModel, EmailStr, Field, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ceq_api.config import get_settings
from ceq_api.db import get_db
from ceq_api.middleware import limiter
from ceq_api.models import FeatureInterest
from ceq_api.services.crm_sync import dispatch_interest_to_crm

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/interest", tags=["interest"])


# Allowed feature_key values. Kept narrow on purpose — every key here should
# correspond to something the studio actually gates today. Add new keys when
# you wire up new gates; reject unknown keys with 422.
ALLOWED_FEATURES: frozenset[str] = frozenset(
    {
        "premium_render",   # Pro render templates / quotas
        "training_access",  # Custom model training
        "team_seats",       # Multi-seat collaboration
        "early_access",     # Generic waitlist
    }
)

MAX_WISHLIST_TEXT_CHARS = 2000


# === Schemas ===


class InterestRequest(BaseModel):
    """Request body for POST /v1/interest/."""

    email: EmailStr
    feature_key: str = Field(..., min_length=1, max_length=64)
    wishlist: Any | None = Field(
        default=None,
        description=(
            "Optional structured or free-text wishlist. Accepts: a string "
            "(treated as raw text, capped at 2000 chars), a list of strings, "
            "or a small object. Stored as JSONB."
        ),
    )
    janua_user_id: str | None = Field(default=None, max_length=64)
    source_page: str | None = Field(default=None, max_length=255)

    @field_validator("feature_key")
    @classmethod
    def _validate_feature_key(cls, v: str) -> str:
        v = v.strip()
        if v not in ALLOWED_FEATURES:
            allowed = ", ".join(sorted(ALLOWED_FEATURES))
            raise ValueError(f"feature_key must be one of: {allowed}")
        return v

    @field_validator("wishlist")
    @classmethod
    def _normalize_wishlist(cls, v: Any | None) -> Any | None:
        if v is None:
            return None
        if isinstance(v, str):
            text = v.strip()
            if not text:
                return None
            return {"text": text[:MAX_WISHLIST_TEXT_CHARS]}
        # list / dict — let JSONB handle it. We don't deep-validate here.
        return v


class InterestResponse(BaseModel):
    """Response payload — matches tezca's shape so the frontend port is 1:1."""

    status: str = Field(..., description="'registered' (new) or 'already_registered'.")


# === Endpoint ===


@router.post(
    "/",
    response_model=InterestResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register interest in a gated feature (InterestGate backend)",
    description=(
        "Public, rate-limited endpoint. Captures email + feature_key for "
        "pre-monetization WTP signal. Idempotent on (email, feature_key): "
        "returns 201 on first registration, 200 if already registered."
    ),
)
@limiter.limit("10/hour")
async def register_interest(
    request: Request,  # required by slowapi for keying
    payload: InterestRequest,
    background_tasks: BackgroundTasks,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Any:
    """Register interest in a gated feature."""
    settings = get_settings()
    if not settings.interest_enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Interest capture is disabled.",
        )

    email = payload.email.lower().strip()
    feature_key = payload.feature_key
    wishlist = payload.wishlist
    janua_user_id = (payload.janua_user_id or "").strip() or None
    source_page = (payload.source_page or "").strip() or None

    # Look up an existing (email, feature_key) row first — the index makes this cheap.
    existing_q = select(FeatureInterest).where(
        FeatureInterest.email == email,
        FeatureInterest.feature_key == feature_key,
    )
    existing = (await db.execute(existing_q)).scalar_one_or_none()

    if existing is not None:
        # Backfill missing supplementary fields if the user provided them this time.
        # We don't overwrite non-null values — first capture wins for those.
        dirty = False
        if wishlist is not None and not existing.wishlist:
            existing.wishlist = wishlist
            dirty = True
        if janua_user_id and not existing.janua_user_id:
            existing.janua_user_id = janua_user_id
            dirty = True
        if source_page and not existing.source_page:
            existing.source_page = source_page
            dirty = True
        if dirty:
            await db.flush()
        # Return 200 on duplicate. FastAPI defaults to 201 from the decorator,
        # so we override via the Response model + raise.
        # Cleanest path: return a JSONResponse with the desired status.
        from fastapi.responses import JSONResponse

        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={"status": "already_registered"},
        )

    # New registration.
    record = FeatureInterest(
        email=email,
        feature_key=feature_key,
        wishlist=wishlist,
        janua_user_id=janua_user_id,
        source_page=source_page,
    )
    db.add(record)
    await db.flush()
    await db.refresh(record)

    # Fire-and-forget CRM push. No-ops when CRM_WEBHOOK_URL is unset.
    background_tasks.add_task(
        dispatch_interest_to_crm,
        {
            "email": record.email,
            "feature_key": record.feature_key,
            "wishlist": record.wishlist,
            "janua_user_id": record.janua_user_id,
            "source_page": record.source_page,
            "created_at": (
                record.created_at.isoformat()
                if isinstance(record.created_at, datetime)
                else None
            ),
        },
    )

    logger.info(
        "interest registered: feature_key=%s source_page=%s authed=%s",
        feature_key,
        source_page or "-",
        bool(janua_user_id),
    )

    return InterestResponse(status="registered")
