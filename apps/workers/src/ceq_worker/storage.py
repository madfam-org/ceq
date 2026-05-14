"""
R2 Storage Client for ceq-worker.

Handles uploading generated outputs to Cloudflare R2.
"""

import asyncio
import struct
import wave
from pathlib import Path
from typing import Any
from uuid import uuid4

import boto3
from botocore.config import Config
from PIL import Image, UnidentifiedImageError

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
    ) -> dict[str, Any]:
        """
        Upload an output file to R2.

        Args:
            local_path: Path to the local file
            job_id: Job ID for organizing outputs
            content_type: Optional MIME type override

        Returns:
            Descriptor for the uploaded file, suitable for the API callback.
        """
        if content_type is None:
            content_type = self._guess_content_type(local_path)
        file_metadata = self._inspect_output_file(local_path, content_type)

        if self._client is None:
            local_url = str(local_path)
            return {
                "filename": local_path.name,
                "storage_uri": local_url,
                "public_url": local_url,
                "file_type": content_type,
                "file_size_bytes": local_path.stat().st_size,
                "preview_url": local_url if content_type.startswith("image/") else None,
                **file_metadata,
            }

        # Generate unique key
        unique_id = uuid4().hex[:8]
        key = f"outputs/{job_id}/{local_path.stem}_{unique_id}{local_path.suffix}"
        storage_uri = f"r2://{settings.r2_bucket}/{key}"

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

        public_url: str
        if settings.r2_public_url:
            public_url = f"{settings.r2_public_url}/{key}"
        else:
            public_url = f"{settings.r2_endpoint}/{settings.r2_bucket}/{key}"

        return {
            "filename": local_path.name,
            "storage_uri": storage_uri,
            "public_url": public_url,
            "file_type": content_type,
            "file_size_bytes": local_path.stat().st_size,
            "preview_url": public_url if content_type.startswith("image/") else None,
            **file_metadata,
        }

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
            ".bmp": "image/bmp",
            ".tif": "image/tiff",
            ".tiff": "image/tiff",
            ".wav": "audio/wav",
            ".mp3": "audio/mpeg",
            ".m4a": "audio/mp4",
            ".ogg": "audio/ogg",
            ".mp4": "video/mp4",
            ".m4v": "video/mp4",
            ".mov": "video/quicktime",
            ".webm": "video/webm",
            ".mkv": "video/x-matroska",
            ".glb": "model/gltf-binary",
            ".gltf": "model/gltf+json",
            ".obj": "model/obj",
            ".fbx": "application/octet-stream",
            ".usdz": "model/vnd.usdz+zip",
            ".ply": "model/ply",
            ".stl": "model/stl",
            ".json": "application/json",
            ".zip": "application/zip",
            ".safetensors": "application/octet-stream",
            ".ckpt": "application/octet-stream",
        }
        return content_types.get(extension, "application/octet-stream")

    def _inspect_output_file(self, path: Path, content_type: str) -> dict[str, Any]:
        """Extract stable metadata for gallery/API output descriptors."""
        descriptor: dict[str, Any] = {}
        metadata: dict[str, Any] = {}

        if content_type.startswith("image/"):
            try:
                with Image.open(path) as image:
                    descriptor["width"] = image.width
                    descriptor["height"] = image.height
                    metadata["image_format"] = image.format
                    metadata["image_mode"] = image.mode
            except (UnidentifiedImageError, OSError):
                metadata["inspection_error"] = "image_metadata_unavailable"
        elif content_type == "audio/wav":
            try:
                with wave.open(str(path), "rb") as audio:
                    frames = audio.getnframes()
                    frame_rate = audio.getframerate()
                    descriptor["duration_seconds"] = frames / frame_rate if frame_rate else 0.0
                    metadata["audio_channels"] = audio.getnchannels()
                    metadata["audio_sample_rate"] = frame_rate
                    metadata["audio_sample_width_bytes"] = audio.getsampwidth()
            except (wave.Error, OSError, EOFError):
                metadata["inspection_error"] = "audio_metadata_unavailable"
        elif content_type in {"video/mp4", "video/quicktime"}:
            duration_seconds = self._read_mp4_duration_seconds(path)
            if duration_seconds is not None:
                descriptor["duration_seconds"] = duration_seconds
            else:
                metadata["inspection_error"] = "video_duration_unavailable"
        elif content_type == "model/gltf-binary":
            try:
                header = path.read_bytes()[:12]
                if len(header) == 12:
                    magic, version, declared_length = struct.unpack("<4sII", header)
                    if magic == b"glTF":
                        metadata["glb_version"] = version
                        metadata["glb_declared_length_bytes"] = declared_length
            except OSError:
                metadata["inspection_error"] = "model_metadata_unavailable"

        if metadata:
            descriptor["metadata"] = metadata
        return descriptor

    def _read_mp4_duration_seconds(self, path: Path) -> float | None:
        """Read MP4/MOV duration from the mvhd box without shelling out."""
        try:
            with path.open("rb") as file_obj:
                file_size = path.stat().st_size
                return self._find_mvhd_duration(file_obj, file_size)
        except (OSError, struct.error):
            return None

    def _find_mvhd_duration(self, file_obj: Any, end: int) -> float | None:
        """Recursively scan MP4 boxes until mvhd duration is found."""
        while file_obj.tell() + 8 <= end:
            box_start = file_obj.tell()
            header = file_obj.read(8)
            if len(header) < 8:
                return None

            box_size, box_type = struct.unpack(">I4s", header)
            header_size = 8
            if box_size == 1:
                large_size = file_obj.read(8)
                if len(large_size) < 8:
                    return None
                box_size = struct.unpack(">Q", large_size)[0]
                header_size = 16
            elif box_size == 0:
                box_size = end - box_start

            box_end = box_start + box_size
            payload_start = box_start + header_size
            if box_end <= payload_start or box_end > end:
                return None

            if box_type == b"mvhd":
                file_obj.seek(payload_start)
                return self._parse_mvhd_duration(file_obj, box_end)

            if box_type in {b"moov", b"trak", b"mdia"}:
                file_obj.seek(payload_start)
                duration = self._find_mvhd_duration(file_obj, box_end)
                if duration is not None:
                    return duration

            file_obj.seek(box_end)

        return None

    def _parse_mvhd_duration(self, file_obj: Any, box_end: int) -> float | None:
        """Parse duration from an mvhd box payload."""
        header = file_obj.read(4)
        if len(header) < 4:
            return None

        version = header[0]
        if version == 1:
            payload = file_obj.read(28)
            if len(payload) < 28:
                return None
            timescale = struct.unpack(">I", payload[16:20])[0]
            duration = struct.unpack(">Q", payload[20:28])[0]
        else:
            payload = file_obj.read(16)
            if len(payload) < 16:
                return None
            timescale = struct.unpack(">I", payload[8:12])[0]
            duration = struct.unpack(">I", payload[12:16])[0]

        file_obj.seek(box_end)
        if not timescale:
            return None
        return duration / timescale
