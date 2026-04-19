"""Deterministic input hashing for render cache keys."""

from __future__ import annotations

import hashlib
import json
from typing import Any


def render_hash(template: str, data: dict[str, Any], template_version: str) -> str:
    """
    Compute a stable hash for a render request.

    The hash changes when: the template name changes, any field in `data`
    changes, or the template version is bumped. Key ordering inside `data`
    is normalized so {"a": 1, "b": 2} and {"b": 2, "a": 1} hash identically.

    Args:
        template: Template identifier (e.g. "card-standard").
        data: Render input — serialized as sorted-key JSON.
        template_version: Version of the template. Bump when the renderer's
            visual output changes so old cached assets aren't served.

    Returns:
        Hex SHA-256 digest (64 chars).
    """
    payload = {
        "template": template,
        "version": template_version,
        "data": data,
    }
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()
