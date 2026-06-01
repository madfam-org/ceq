"""Quota helpers for GPU job submission."""

from collections.abc import Iterable
from typing import Any
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ceq_api.auth import JanuaUser
from ceq_api.models import Job, JobStatus

ACTIVE_JOB_STATUSES = (JobStatus.QUEUED.value, JobStatus.RUNNING.value)
PRO_QUOTA_ROLES = {
    "paid",
    "pro",
    "premium",
    "ceq-pro",
    "ceq-premium",
    "ceq:pro",
    "ceq:premium",
    "plan-pro",
    "plan-premium",
    "plan:pro",
    "plan:premium",
    "tier-pro",
    "tier-premium",
    "tier:pro",
    "tier:premium",
}
STUDIO_QUOTA_ROLES = {
    "studio",
    "ceq-studio",
    "ceq:studio",
    "plan-studio",
    "plan:studio",
    "tier-studio",
    "tier:studio",
}


def _normalize(values: Iterable[object] | None) -> set[str]:
    return {
        str(value).strip().lower().replace("_", "-")
        for value in values or []
        if str(value).strip()
    }


def active_job_limit_for_user(user: JanuaUser, settings: Any) -> int:
    """Resolve the active-job cap for the user's current plan/role."""
    roles = _normalize(user.roles)
    if user.is_admin:
        return int(settings.max_active_jobs_admin)
    if roles & STUDIO_QUOTA_ROLES:
        return int(settings.max_active_jobs_studio)
    if roles & PRO_QUOTA_ROLES:
        return int(settings.max_active_jobs_pro)
    return int(settings.max_active_jobs_per_user)


async def require_active_job_quota(
    db: AsyncSession,
    *,
    user_id: UUID,
    max_active_jobs: int,
) -> None:
    """Raise when a user has reached the configured queued/running job cap."""
    if max_active_jobs <= 0:
        return

    active_jobs = await db.scalar(
        select(func.count())
        .select_from(Job)
        .where(
            Job.user_id == user_id,
            Job.status.in_(ACTIVE_JOB_STATUSES),
        )
    )
    active_count = int(active_jobs or 0)

    if active_count < max_active_jobs:
        return

    raise HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail={
            "message": "Active job limit reached. Wait for a job to finish before starting another.",
            "max_active_jobs": max_active_jobs,
            "active_jobs": active_count,
        },
    )
