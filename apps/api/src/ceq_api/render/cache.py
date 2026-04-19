"""R2-backed cache for deterministic renders.

Cache strategy:
  key = render/{template}/{hash}.{ext}

On cache hit, HEAD the object to confirm existence and return its public URL.
On miss, the caller renders bytes and uploads them via `put`.
"""

from __future__ import annotations

from ceq_api.storage import StorageClient


class RenderCache:
    """R2-backed cache for rendered assets."""

    def __init__(self, storage: StorageClient, prefix: str = "render") -> None:
        self._storage = storage
        self._prefix = prefix.rstrip("/")

    def key(self, template: str, digest: str, ext: str) -> str:
        """Build the R2 object key for a cached render."""
        return f"{self._prefix}/{template}/{digest}.{ext.lstrip('.')}"

    async def exists(self, key: str) -> bool:
        return await self._storage.head_object(key)

    async def put(
        self,
        key: str,
        body: bytes,
        content_type: str,
        cache_control: str = "public, max-age=31536000, immutable",
    ) -> str:
        """
        Upload bytes to R2 at the given key and return the storage URI.

        Immutable cache-control is safe because keys are content-addressed
        (hash-based) — same inputs always land at the same key.
        """
        return await self._storage.put_object(
            key=key,
            body=body,
            content_type=content_type,
            cache_control=cache_control,
        )
