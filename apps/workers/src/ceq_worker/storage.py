"""
R2 Storage Client for ceq-worker.

Handles uploading generated outputs to Cloudflare R2.
"""

import asyncio
from pathlib import Path
from typing import Any
from uuid import uuid4

import boto3
from botocore.config import Config

from ceq_worker.config import get_settings

settings = get_settings()


class StorageClient:
    """
    Cloudflare R2 storage client.
    
    Handles uploading generated outputs (images, videos, models)
    to R2 storage for retrieval by the API.
    """

    def __init__(self) -> None:
        self._client: Any = None

    async def initialize(self) -> None:
        """Initialize the S3-compatible R2 client."""
        if self._client is not None:
            return

        if not settings.r2_endpoint:
            print("   R2 storage not configured - outputs will be local only")
            return

        # Run synchronous boto3 init in executor
        loop = asyncio.get_event_loop()
        self._client = await loop.run_in_executor(
            None,
            self._create_client,
        )
        print("   R2 storage client initialized")

    def _create_client(self) -> Any:
        """Create S3-compatible client for R2."""
        return boto3.client(
            "s3",
            endpoint_url=settings.r2_endpoint,
            aws_access_key_id=settings.r2_access_key,
            aws_secret_access_key=settings.r2_secret_key,
            config=Config(
                signature_version="s3v4",
                retries={"max_attempts": 3},
            ),
        )

    async def upload_output(
        self,
        local_path: Path,
        job_id: str,
        content_type: str | None = None,
    ) -> str:
        """
        Upload an output file to R2.
        
        Args:
            local_path: Path to the local file
            job_id: Job ID for organizing outputs
            content_type: Optional MIME type override
            
        Returns:
            Public URL for the uploaded file
        """
        if self._client is None:
            # Return local path if R2 not configured
            return str(local_path)

        # Determine content type
        if content_type is None:
            content_type = self._guess_content_type(local_path)

        # Generate unique key
        unique_id = uuid4().hex[:8]
        key = f"outputs/{job_id}/{local_path.stem}_{unique_id}{local_path.suffix}"

        # Upload in executor (boto3 is sync)
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None,
            lambda: self._client.upload_file(
                str(local_path),
                settings.r2_bucket,
                key,
                ExtraArgs={
                    "ContentType": content_type,
                    "CacheControl": "public, max-age=31536000",  # 1 year
                },
            ),
        )

        # Return public URL
        if settings.r2_public_url:
            return f"{settings.r2_public_url}/{key}"
        else:
            return f"{settings.r2_endpoint}/{settings.r2_bucket}/{key}"

    async def upload_asset(
        self,
        local_path: Path,
        asset_type: str,
        asset_id: str,
    ) -> str:
        """
        Upload an asset (model, LoRA, etc.) to R2.
        
        Args:
            local_path: Path to the local file
            asset_type: Type of asset (checkpoint, lora, etc.)
            asset_id: Unique asset identifier
            
        Returns:
            Storage URI for the asset
        """
        if self._client is None:
            return str(local_path)

        key = f"assets/{asset_type}/{asset_id}/{local_path.name}"

        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None,
            lambda: self._client.upload_file(
                str(local_path),
                settings.r2_bucket,
                key,
            ),
        )

        return f"r2://{settings.r2_bucket}/{key}"

    async def download_asset(
        self,
        storage_uri: str,
        local_path: Path,
    ) -> Path:
        """
        Download an asset from R2 to local storage.
        
        Args:
            storage_uri: R2 URI (r2://bucket/key)
            local_path: Local destination path
            
        Returns:
            Path to downloaded file
        """
        if self._client is None:
            raise RuntimeError("R2 storage not configured")

        # Parse URI
        if not storage_uri.startswith("r2://"):
            raise ValueError(f"Invalid R2 URI: {storage_uri}")

        parts = storage_uri[5:].split("/", 1)
        bucket = parts[0]
        key = parts[1] if len(parts) > 1 else ""

        # Ensure parent directory exists
        local_path.parent.mkdir(parents=True, exist_ok=True)

        # Download in executor
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None,
            lambda: self._client.download_file(bucket, key, str(local_path)),
        )

        return local_path

    def _guess_content_type(self, path: Path) -> str:
        """Guess MIME type from file extension."""
        extension = path.suffix.lower()
        content_types = {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".webp": "image/webp",
            ".gif": "image/gif",
            ".mp4": "video/mp4",
            ".webm": "video/webm",
            ".glb": "model/gltf-binary",
            ".gltf": "model/gltf+json",
            ".safetensors": "application/octet-stream",
            ".ckpt": "application/octet-stream",
        }
        return content_types.get(extension, "application/octet-stream")
