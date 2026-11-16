"""Quota helpers for GPU job submission."""

from typing import Any
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ceq_api.auth import JanuaUser
from ceq_api.models import Job, JobStatus

ACTIVE_JOB_STATUSES = (JobStatus.QUEUED.value, JobStatus.RUNNING.value)
# Quota classes come ONLY from `JanuaUser.entitlements`, which
# `ceq_entitlements_from_claims` fills from the verified `ceq_tier` claim
# (see `auth/ceq_tier.py`). The `roles` claim is never read here: it carries
# organization membership roles and application-role grants, neither of which
# is a CEQ purchase.
PRO_QUOTA_ENTITLEMENTS = frozenset({"ceq:pro-artist"})
STUDIO_QUOTA_ENTITLEMENTS = frozenset({"ceq:studio"})


def active_job_limit_for_user(user: JanuaUser, settings: Any) -> int:
    """Resolve the active-job cap from the verified CEQ tier entitlement."""
    if user.is_admin:
        return int(settings.max_active_jobs_admin)
    entitlements = set(getattr(user, "entitlements", None) or [])
    if entitlements & STUDIO_QUOTA_ENTITLEMENTS:
        return int(settings.max_active_jobs_studio)
    if entitlements & PRO_QUOTA_ENTITLEMENTS:
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
