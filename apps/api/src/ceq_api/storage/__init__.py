"""
R2 Storage module for ceq-api.

Provides presigned URL generation for output downloads and direct uploads.
"""

import asyncio
from functools import lru_cache
from typing import Any

import boto3
from botocore.config import Config

from ceq_api.config import get_settings


class StorageClient:
    """
    Cloudflare R2 storage client for the API.

    Handles presigned URL generation for secure access to outputs
    without exposing R2 credentials to clients.
    """

    def __init__(self) -> None:
        self._client: Any = None
        self._settings = get_settings()

    async def initialize(self) -> None:
        """Initialize the S3-compatible R2 client."""
        if self._client is not None:
            return

        if not self._settings.r2_endpoint:
            return

        loop = asyncio.get_event_loop()
        self._client = await loop.run_in_executor(
            None,
            self._create_client,
        )

    def _create_client(self) -> Any:
        """Create S3-compatible client for R2."""
        return boto3.client(
            "s3",
            endpoint_url=self._settings.r2_endpoint,
            aws_access_key_id=self._settings.r2_access_key,
            aws_secret_access_key=self._settings.r2_secret_key,
            config=Config(
                signature_version="s3v4",
                retries={"max_attempts": 3},
            ),
        )

    @property
    def is_configured(self) -> bool:
        """Check if R2 storage is configured."""
        return bool(self._settings.r2_endpoint)

    def get_public_url(self, storage_uri: str) -> str:
        """
        Convert internal storage URI to public URL.

        Args:
            storage_uri: R2 URI (r2://bucket/key) or full URL

        Returns:
            Public URL for the resource
        """
        # Already a URL
        if storage_uri.startswith("http"):
            return storage_uri

        # Parse R2 URI
        if storage_uri.startswith("r2://"):
            parts = storage_uri[5:].split("/", 1)
            key = parts[1] if len(parts) > 1 else ""
        else:
            # Assume it's just a key
            key = storage_uri

        if self._settings.r2_public_url:
            return f"{self._settings.r2_public_url}/{key}"
        else:
            return f"{self._settings.r2_endpoint}/{self._settings.r2_bucket}/{key}"

    async def generate_download_url(
        self,
        storage_uri: str,
        expires_in: int = 3600,
        filename: str | None = None,
    ) -> str:
        """
        Generate a presigned download URL.

        Args:
            storage_uri: R2 URI or key for the object
            expires_in: URL expiration time in seconds (default 1 hour)
            filename: Optional filename for Content-Disposition header

        Returns:
            Presigned URL for downloading the object
        """
        if self._client is None:
            # Return public URL if client not configured
            return self.get_public_url(storage_uri)

        # Parse key from URI
        if storage_uri.startswith("r2://"):
            parts = storage_uri[5:].split("/", 1)
            bucket = parts[0]
            key = parts[1] if len(parts) > 1 else ""
        elif storage_uri.startswith("http"):
            # Extract key from URL
            # Format: https://endpoint/bucket/key or https://public-url/key
            key = storage_uri.split("/", 3)[-1]
            bucket = self._settings.r2_bucket
        else:
            key = storage_uri
            bucket = self._settings.r2_bucket

        params: dict[str, Any] = {
            "Bucket": bucket,
            "Key": key,
        }

        # Add content-disposition if filename provided
        if filename:
            params["ResponseContentDisposition"] = f'attachment; filename="{filename}"'

        loop = asyncio.get_event_loop()
        url = await loop.run_in_executor(
            None,
            lambda: self._client.generate_presigned_url(
                "get_object",
                Params=params,
                ExpiresIn=expires_in,
            ),
        )
        return url

    async def generate_upload_url(
        self,
        key: str,
        content_type: str = "application/octet-stream",
        expires_in: int = 3600,
    ) -> dict[str, str]:
        """
        Generate a presigned upload URL for direct client uploads.

        Args:
            key: Object key (path within bucket)
            content_type: MIME type of the upload
            expires_in: URL expiration time in seconds

        Returns:
            Dict with 'upload_url' and 'storage_uri'
        """
        if self._client is None:
            raise RuntimeError("R2 storage not configured")

        loop = asyncio.get_event_loop()
        url = await loop.run_in_executor(
            None,
            lambda: self._client.generate_presigned_url(
                "put_object",
                Params={
                    "Bucket": self._settings.r2_bucket,
                    "Key": key,
                    "ContentType": content_type,
                },
                ExpiresIn=expires_in,
            ),
        )

        return {
            "upload_url": url,
            "storage_uri": f"r2://{self._settings.r2_bucket}/{key}",
        }

    async def delete_object(self, storage_uri: str) -> bool:
        """
        Delete an object from R2.

        Args:
            storage_uri: R2 URI or key for the object

        Returns:
            True if deleted successfully
        """
        if self._client is None:
            return False

        # Parse key from URI
        if storage_uri.startswith("r2://"):
            parts = storage_uri[5:].split("/", 1)
            bucket = parts[0]
            key = parts[1] if len(parts) > 1 else ""
        else:
            key = storage_uri
            bucket = self._settings.r2_bucket

        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None,
            lambda: self._client.delete_object(Bucket=bucket, Key=key),
        )
        return True

    async def delete_prefix(self, prefix: str) -> int:
        """
        Delete all objects with a given prefix.

        Args:
            prefix: Key prefix to delete (e.g., "outputs/job-id/")

        Returns:
            Number of objects deleted
        """
        if self._client is None:
            return 0

        loop = asyncio.get_event_loop()

        # List objects with prefix
        response = await loop.run_in_executor(
            None,
            lambda: self._client.list_objects_v2(
                Bucket=self._settings.r2_bucket,
                Prefix=prefix,
            ),
        )

        objects = response.get("Contents", [])
        if not objects:
            return 0

        # Delete objects
        delete_keys = [{"Key": obj["Key"]} for obj in objects]
        await loop.run_in_executor(
            None,
            lambda: self._client.delete_objects(
                Bucket=self._settings.r2_bucket,
                Delete={"Objects": delete_keys},
            ),
        )

        return len(delete_keys)


# Singleton instance
_storage_client: StorageClient | None = None


async def get_storage() -> StorageClient:
    """Get the storage client singleton, initializing if needed."""
    global _storage_client
    if _storage_client is None:
        _storage_client = StorageClient()
        await _storage_client.initialize()
    return _storage_client
