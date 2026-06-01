"""Credit ledger helpers shared by commercial API surfaces."""

from typing import Any
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ceq_api.models import CreditLedgerEntry, CreditLedgerType


async def get_credit_balance(db: AsyncSession, user_id: UUID) -> int:
    """Compute current balance from the append-only ledger."""
    balance = await db.scalar(
        select(func.coalesce(func.sum(CreditLedgerEntry.amount), 0)).where(
            CreditLedgerEntry.user_id == user_id
        )
    )
    return int(balance or 0)


async def require_credit_balance(
    db: AsyncSession,
    *,
    user_id: UUID,
    amount: int,
    idempotency_key: str,
) -> None:
    """Fail closed when a new debit would exceed the current balance."""
    if amount <= 0:
        return

    existing = await db.scalar(
        select(CreditLedgerEntry).where(
            CreditLedgerEntry.idempotency_key == idempotency_key
        )
    )
    if existing is not None:
        return

    balance = await get_credit_balance(db, user_id)
    if balance >= amount:
        return

    raise HTTPException(
        status_code=status.HTTP_402_PAYMENT_REQUIRED,
        detail={
            "message": "Insufficient CEQ credits.",
            "required_credits": amount,
            "available_credits": balance,
        },
    )


async def debit_credits(
    db: AsyncSession,
    *,
    user_id: UUID,
    org_id: UUID | None,
    job_id: UUID | None = None,
    output_id: UUID | None = None,
    amount: int,
    reason: str,
    idempotency_key: str,
    metadata: dict[str, Any],
) -> CreditLedgerEntry | None:
    """Append an idempotent debit entry after successful billable work."""
    if amount <= 0:
        return None

    existing = await db.scalar(
        select(CreditLedgerEntry).where(
            CreditLedgerEntry.idempotency_key == idempotency_key
        )
    )
    if existing is not None:
        _assert_idempotent_debit_matches(existing, user_id, amount, reason)
        return existing

    await require_credit_balance(
        db,
        user_id=user_id,
        amount=amount,
        idempotency_key=idempotency_key,
    )

    entry = CreditLedgerEntry(
        user_id=user_id,
        org_id=org_id,
        job_id=job_id,
        output_id=output_id,
        amount=-amount,
        transaction_type=CreditLedgerType.DEBIT.value,
        reason=reason,
        idempotency_key=idempotency_key,
        ledger_metadata=metadata,
    )
    db.add(entry)
    await db.flush()
    await db.refresh(entry)
    return entry


async def refund_credits_for_debit(
    db: AsyncSession,
    *,
    debit_idempotency_key: str,
    refund_idempotency_key: str,
    reason: str,
    metadata: dict[str, Any],
) -> CreditLedgerEntry | None:
    """Refund an existing debit once, keyed by the original debit."""
    debit = await db.scalar(
        select(CreditLedgerEntry).where(
            CreditLedgerEntry.idempotency_key == debit_idempotency_key
        )
    )
    if debit is None or debit.transaction_type != CreditLedgerType.DEBIT.value:
        return None

    refund_amount = abs(debit.amount)
    if refund_amount <= 0:
        return None

    existing = await db.scalar(
        select(CreditLedgerEntry).where(
            CreditLedgerEntry.idempotency_key == refund_idempotency_key
        )
    )
    if existing is not None:
        _assert_idempotent_refund_matches(existing, debit, refund_amount)
        return existing

    entry = CreditLedgerEntry(
        user_id=debit.user_id,
        org_id=debit.org_id,
        job_id=debit.job_id,
        output_id=debit.output_id,
        amount=refund_amount,
        transaction_type=CreditLedgerType.REFUND.value,
        reason=reason,
        idempotency_key=refund_idempotency_key,
        ledger_metadata={
            **metadata,
            "debit_idempotency_key": debit_idempotency_key,
        },
    )
    db.add(entry)
    await db.flush()
    await db.refresh(entry)
    return entry


def _assert_idempotent_debit_matches(
    existing: CreditLedgerEntry,
    user_id: UUID,
    amount: int,
    reason: str,
) -> None:
    if (
        existing.transaction_type == CreditLedgerType.DEBIT.value
        and existing.user_id == user_id
        and existing.amount == -amount
        and existing.reason == reason
    ):
        return

    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail="Idempotency key already exists for a different credit ledger entry.",
    )


def _assert_idempotent_refund_matches(
    existing: CreditLedgerEntry,
    debit: CreditLedgerEntry,
    refund_amount: int,
) -> None:
    if (
        existing.transaction_type == CreditLedgerType.REFUND.value
        and existing.user_id == debit.user_id
        and existing.org_id == debit.org_id
        and existing.job_id == debit.job_id
        and existing.output_id == debit.output_id
        and existing.amount == refund_amount
    ):
        return

    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail="Idempotency key already exists for a different credit ledger entry.",
    )
