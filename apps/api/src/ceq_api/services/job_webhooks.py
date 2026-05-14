"""User-provided job completion webhook delivery."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
from datetime import UTC, datetime
from typing import Any

import httpx

from ceq_api.config import get_settings
from ceq_api.models.job import Job
from ceq_api.models.output import Output
from ceq_api.storage import StorageClient

logger = logging.getLogger(__name__)

TERMINAL_STATUSES = {"completed", "failed", "cancelled"}


def sign_job_webhook_body(body: bytes, secret: str) -> str:
    """Return the HMAC-SHA256 signature for a webhook body."""
    return hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()


def _iso(value: Any) -> str | None:
    """Serialize datetimes while preserving None for optional fields."""
    return value.isoformat() if value else None


def _payload_for(job: Job, outputs: list[Output], storage: StorageClient) -> dict[str, Any]:
    """Build the job webhook payload."""
    return {
        "event": f"job.{job.status}",
        "timestamp": datetime.now(UTC).isoformat(),
        "source": "ceq",
        "job": {
            "id": str(job.id),
            "workflow_id": str(job.workflow_id),
            "status": job.status,
            "progress": job.progress,
            "error": job.error,
            "input_params": job.input_params,
            "metadata": job.output_metadata or {},
            "queued_at": _iso(job.queued_at),
            "started_at": _iso(job.started_at),
            "completed_at": _iso(job.completed_at),
            "worker_id": job.worker_id,
            "gpu_seconds": job.gpu_seconds,
            "cold_start_ms": job.cold_start_ms,
        },
        "outputs": [
            {
                "id": str(output.id),
                "filename": output.filename,
                "storage_uri": output.storage_uri,
                "public_url": storage.get_public_url(output.storage_uri),
                "file_type": output.file_type,
                "file_size_bytes": output.file_size_bytes,
                "width": output.width,
                "height": output.height,
                "duration_seconds": output.duration_seconds,
                "preview_url": output.preview_url,
                "metadata": output.output_metadata,
            }
            for output in outputs
        ],
    }


def _delivery_record(
    *,
    status: str,
    attempts: int,
    event: str,
    payload_sha256: str | None = None,
    last_status_code: int | None = None,
    last_error: str | None = None,
    delivered_at: str | None = None,
) -> dict[str, Any]:
    """Build delivery metadata persisted on Job.output_metadata."""
    record: dict[str, Any] = {
        "status": status,
        "attempts": attempts,
        "event": event,
        "updated_at": datetime.now(UTC).isoformat(),
    }
    if payload_sha256 is not None:
        record["payload_sha256"] = payload_sha256
    if last_status_code is not None:
        record["last_status_code"] = last_status_code
    if last_error is not None:
        record["last_error"] = last_error
    if delivered_at is not None:
        record["delivered_at"] = delivered_at
    return record


async def deliver_job_webhook(
    job: Job,
    outputs: list[Output],
    storage: StorageClient,
) -> dict[str, Any] | None:
    """Deliver a signed user webhook for a terminal job."""
    if not job.webhook_url or job.status not in TERMINAL_STATUSES:
        return None

    metadata = dict(job.output_metadata or {})
    previous_delivery = metadata.get("webhook_delivery")
    if isinstance(previous_delivery, dict) and previous_delivery.get("status") == "delivered":
        return previous_delivery

    settings = get_settings()
    event = f"job.{job.status}"
    secret = settings.job_webhook_secret

    if not secret:
        delivery = _delivery_record(
            status="skipped",
            attempts=0,
            event=event,
            last_error="JOB_WEBHOOK_SECRET is not configured.",
        )
        metadata["webhook_delivery"] = delivery
        job.output_metadata = metadata
        logger.warning("Skipping job webhook for job %s: secret not configured", job.id)
        return delivery

    payload = _payload_for(job, outputs, storage)
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    payload_sha256 = hashlib.sha256(body).hexdigest()
    signature = sign_job_webhook_body(body, secret)
    timestamp = payload["timestamp"]

    headers = {
        "Content-Type": "application/json",
        "User-Agent": "ceq-api/job-webhook",
        "X-CEQ-Event": event,
        "X-CEQ-Job-ID": str(job.id),
        "X-CEQ-Signature": f"sha256={signature}",
        "X-CEQ-Timestamp": timestamp,
    }

    max_attempts = max(1, settings.job_webhook_max_attempts)
    last_status_code: int | None = None
    last_error: str | None = None
    attempts_made = 0

    for attempt in range(1, max_attempts + 1):
        attempts_made = attempt
        try:
            async with httpx.AsyncClient(
                timeout=settings.job_webhook_timeout_seconds
            ) as client:
                response = await client.post(
                    job.webhook_url,
                    content=body,
                    headers=headers,
                )
            last_status_code = response.status_code
            last_error = response.text[:500] if response.status_code >= 400 else None

            if 200 <= response.status_code < 300:
                delivery = _delivery_record(
                    status="delivered",
                    attempts=attempt,
                    event=event,
                    payload_sha256=payload_sha256,
                    last_status_code=response.status_code,
                    delivered_at=datetime.now(UTC).isoformat(),
                )
                metadata["webhook_delivery"] = delivery
                job.output_metadata = metadata
                logger.info("Delivered job webhook for job %s", job.id)
                return delivery

            if 400 <= response.status_code < 500:
                break
        except httpx.HTTPError as exc:
            last_error = str(exc)

        if attempt < max_attempts and settings.job_webhook_retry_backoff_seconds > 0:
            await asyncio.sleep(settings.job_webhook_retry_backoff_seconds * attempt)

    delivery = _delivery_record(
        status="failed",
        attempts=attempts_made,
        event=event,
        payload_sha256=payload_sha256,
        last_status_code=last_status_code,
        last_error=last_error,
    )
    metadata["webhook_delivery"] = delivery
    job.output_metadata = metadata
    logger.warning("Job webhook failed for job %s: %s", job.id, last_error)
    return delivery
