"""Feature-flagged billing helpers for GPU jobs."""

from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from ceq_api.auth import JanuaUser
from ceq_api.credit_ledger import debit_credits, refund_credits_for_debit
from ceq_api.models import CreditLedgerEntry, Job


def gpu_job_credit_debit_key(job_id: UUID) -> str:
    return f"gpu-job:{job_id}:debit"


def gpu_job_credit_refund_key(job_id: UUID) -> str:
    return f"gpu-job:{job_id}:refund"


def gpu_job_credit_cost(settings: Any, category: str | None) -> int:
    normalized = (category or "").strip().lower()
    if normalized == "video":
        return int(settings.gpu_job_credit_cost_video)
    if normalized == "3d":
        return int(settings.gpu_job_credit_cost_3d)
    if normalized in {"social", "image"}:
        return int(settings.gpu_job_credit_cost_image)
    return int(settings.gpu_job_credit_cost_default)


async def debit_gpu_job_credits(
    db: AsyncSession,
    settings: Any,
    job: Job,
    user: JanuaUser,
    *,
    category: str | None,
    template_id: UUID | None = None,
) -> CreditLedgerEntry | None:
    """Debit credits for an accepted GPU job when commercial metering is enabled."""
    if not settings.gpu_job_credit_debits_enabled:
        return None

    cost = gpu_job_credit_cost(settings, category)
    entry = await debit_credits(
        db,
        user_id=user.id,
        org_id=user.org_id,
        job_id=job.id,
        amount=cost,
        reason=f"gpu-job:{category or 'default'}",
        idempotency_key=gpu_job_credit_debit_key(job.id),
        metadata={
            "category": category or "default",
            "template_id": str(template_id) if template_id else None,
        },
    )
    if entry is not None:
        job.output_metadata = {
            **(job.output_metadata or {}),
            "credit_debit": {
                "amount": cost,
                "idempotency_key": entry.idempotency_key,
                "ledger_entry_id": str(entry.id),
            },
        }
    return entry


async def refund_gpu_job_credits(
    db: AsyncSession,
    settings: Any,
    job: Job,
    *,
    reason: str,
) -> CreditLedgerEntry | None:
    """Refund a previously debited GPU job once when it fails or is cancelled."""
    entry = await refund_credits_for_debit(
        db,
        debit_idempotency_key=gpu_job_credit_debit_key(job.id),
        refund_idempotency_key=gpu_job_credit_refund_key(job.id),
        reason=f"gpu-job-refund:{reason}",
        metadata={
            "job_status": job.status,
            "refund_reason": reason,
        },
    )
    if entry is not None:
        job.output_metadata = {
            **(job.output_metadata or {}),
            "credit_refund": {
                "amount": entry.amount,
                "idempotency_key": entry.idempotency_key,
                "ledger_entry_id": str(entry.id),
                "reason": reason,
            },
        }
    return entry
