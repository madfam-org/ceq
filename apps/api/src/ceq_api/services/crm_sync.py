"""CRM webhook dispatch — pushes interest.created events to Phyne-CRM.

Mirrors the tezca pattern (`apps/api/crm_sync.py` + `tasks.deliver_crm_webhook`)
but adapted to ceq-api's stack: async httpx + FastAPI BackgroundTasks instead
of Celery. No-ops when `CRM_WEBHOOK_URL` or `CRM_WEBHOOK_SECRET` is unset, so
local dev and self-hosted deployments work without CRM wiring.

Payload signing: HMAC-SHA256 over the raw JSON body, hex-encoded, sent as
`X-Webhook-Signature: sha256=<hex>`. Phyne-CRM verifies with the shared secret.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
from datetime import datetime, timezone
from typing import Any

import httpx

from ceq_api.config import get_settings

logger = logging.getLogger(__name__)


def _sign(body: bytes, secret: str) -> str:
    """HMAC-SHA256 hex digest of `body` with `secret`."""
    return hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()


def _serialize_record(record: dict[str, Any]) -> dict[str, Any]:
    """Build the wire payload for an interest.created event."""
    return {
        "event": "interest.created",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source": "ceq",
        "data": {
            "email": record.get("email"),
            "feature_key": record.get("feature_key"),
            "wishlist": record.get("wishlist"),
            "janua_user_id": record.get("janua_user_id"),
            "source_page": record.get("source_page"),
            "created_at": record.get("created_at"),
        },
    }


async def dispatch_interest_to_crm(record: dict[str, Any]) -> None:
    """Push a feature-interest record to Phyne-CRM.

    Designed to be called from FastAPI's BackgroundTasks (fire-and-forget). All
    failures are logged and swallowed — a CRM outage must never break the
    user-facing capture flow. The DB row is the source of truth; CRM sync is a
    convenience.

    Args:
        record: Dict with at minimum `email` and `feature_key`. Other fields
            (`wishlist`, `janua_user_id`, `source_page`, `created_at`) are
            forwarded if present.
    """
    settings = get_settings()
    url = settings.crm_webhook_url
    secret = settings.crm_webhook_secret

    if not url or not secret:
        # Pre-monetization / local dev — no CRM wired up. Silent no-op.
        return

    payload = _serialize_record(record)
    # Stable JSON encoding (no whitespace) — what we sign is what we send.
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    signature = _sign(body, secret)
    timestamp_header = payload["timestamp"]

    headers = {
        "Content-Type": "application/json",
        "X-Webhook-Signature": f"sha256={signature}",
        "X-Webhook-Timestamp": timestamp_header,
        "User-Agent": "ceq-api/crm-sync",
    }

    try:
        async with httpx.AsyncClient(timeout=settings.crm_webhook_timeout_seconds) as client:
            resp = await client.post(url, content=body, headers=headers)
        if resp.status_code >= 400:
            logger.warning(
                "CRM webhook returned %s for feature_key=%s (body truncated: %s)",
                resp.status_code,
                record.get("feature_key"),
                resp.text[:200],
            )
            return
        logger.info(
            "CRM webhook delivered: feature_key=%s status=%s",
            record.get("feature_key"),
            resp.status_code,
        )
    except httpx.HTTPError as exc:
        # Network blip, DNS, timeout — nothing to do. The DB row is intact.
        logger.warning(
            "CRM webhook failed: feature_key=%s error=%s",
            record.get("feature_key"),
            exc,
        )
    except Exception:  # pragma: no cover — defensive last-resort
        logger.exception("Unexpected CRM webhook failure")
