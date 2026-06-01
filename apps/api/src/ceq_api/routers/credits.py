"""Credit ledger endpoints for commercial metering."""

from datetime import datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ceq_api.auth import JanuaUser, get_current_user, require_admin
from ceq_api.credit_ledger import get_credit_balance as compute_credit_balance
from ceq_api.db import get_db
from ceq_api.models import CreditLedgerEntry, CreditLedgerType

router = APIRouter()


class CreditLedgerEntryResponse(BaseModel):
    """Single credit ledger entry."""

    id: UUID
    user_id: UUID
    org_id: UUID | None
    job_id: UUID | None
    output_id: UUID | None
    amount: int
    transaction_type: str
    reason: str
    idempotency_key: str
    ledger_metadata: dict[str, Any]
    created_at: datetime

    class Config:
        from_attributes = True


class CreditBalanceResponse(BaseModel):
    """Current credit balance for the authenticated user."""

    user_id: UUID
    org_id: UUID | None
    balance: int


class CreditLedgerListResponse(BaseModel):
    """Paginated credit ledger response."""

    entries: list[CreditLedgerEntryResponse]
    total: int
    skip: int
    limit: int


class CreditGrantRequest(BaseModel):
    """Admin request to grant credits to a user."""

    user_id: UUID
    org_id: UUID | None = None
    amount: int = Field(..., gt=0, le=1_000_000)
    reason: str = Field(..., min_length=3, max_length=255)
    idempotency_key: str = Field(..., min_length=8, max_length=255)
    metadata: dict[str, Any] = Field(default_factory=dict)


@router.get("/balance", response_model=CreditBalanceResponse)
async def get_credit_balance(
    user: Annotated[JanuaUser, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> CreditBalanceResponse:
    """Return the authenticated user's current credit balance."""
    balance = await compute_credit_balance(db, user.id)
    return CreditBalanceResponse(user_id=user.id, org_id=user.org_id, balance=balance)


@router.get("/ledger", response_model=CreditLedgerListResponse)
async def list_credit_ledger(
    user: Annotated[JanuaUser, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
) -> CreditLedgerListResponse:
    """List the authenticated user's credit ledger entries."""
    base_query = select(CreditLedgerEntry).where(CreditLedgerEntry.user_id == user.id)
    total = await db.scalar(select(func.count()).select_from(base_query.subquery())) or 0

    result = await db.execute(
        base_query.order_by(CreditLedgerEntry.created_at.desc(), CreditLedgerEntry.id.desc())
        .offset(skip)
        .limit(limit)
    )
    entries = list(result.scalars().all())

    return CreditLedgerListResponse(
        entries=[CreditLedgerEntryResponse.model_validate(entry) for entry in entries],
        total=total,
        skip=skip,
        limit=limit,
    )


@router.post(
    "/grants",
    response_model=CreditLedgerEntryResponse,
    status_code=status.HTTP_201_CREATED,
)
async def grant_credits(
    data: CreditGrantRequest,
    _admin: Annotated[JanuaUser, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> CreditLedgerEntryResponse:
    """Grant credits to a user with an idempotency key."""
    existing = await db.scalar(
        select(CreditLedgerEntry).where(
            CreditLedgerEntry.idempotency_key == data.idempotency_key
        )
    )
    if existing is not None:
        _assert_idempotent_grant_matches(existing, data)
        return CreditLedgerEntryResponse.model_validate(existing)

    entry = CreditLedgerEntry(
        user_id=data.user_id,
        org_id=data.org_id,
        amount=data.amount,
        transaction_type=CreditLedgerType.GRANT.value,
        reason=data.reason,
        idempotency_key=data.idempotency_key,
        ledger_metadata=data.metadata,
    )
    db.add(entry)
    await db.flush()
    await db.refresh(entry)

    return CreditLedgerEntryResponse.model_validate(entry)


def _assert_idempotent_grant_matches(
    existing: CreditLedgerEntry,
    data: CreditGrantRequest,
) -> None:
    """Reject idempotency-key reuse for a different grant payload."""
    if (
        existing.transaction_type == CreditLedgerType.GRANT.value
        and existing.user_id == data.user_id
        and existing.org_id == data.org_id
        and existing.amount == data.amount
        and existing.reason == data.reason
    ):
        return

    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail="Idempotency key already exists for a different credit ledger entry.",
    )
