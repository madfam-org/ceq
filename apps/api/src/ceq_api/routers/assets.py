"""Asset management endpoints (models, LoRAs, VAEs, embeddings)."""

import hashlib
import logging
from datetime import datetime
from typing import Annotated, Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ceq_api.auth import JanuaUser, get_current_user
from ceq_api.db import get_db
from ceq_api.models import Asset
from ceq_api.storage import get_storage

logger = logging.getLogger(__name__)

router = APIRouter()


# === Pydantic Models ===


class AssetResponse(BaseModel):
    """Response model for an asset."""

    id: UUID
    name: str
    description: str | None
    asset_type: str = Field(description="checkpoint | lora | vae | embedding | controlnet")
    storage_uri: str
    public_url: str
    size_bytes: int
    checksum: str | None
    tags: list[str]
    preview_url: str | None
    asset_metadata: dict[str, Any]
    is_public: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class AssetList(BaseModel):
    """Paginated asset list."""

    assets: list[AssetResponse]
    total: int
    skip: int
    limit: int


class AssetUploadResponse(BaseModel):
    """Response after uploading an asset."""

    id: UUID
    name: str
    storage_uri: str
    public_url: str
    message: str


class PresignedUploadRequest(BaseModel):
    """Request for a presigned upload URL."""

    filename: str = Field(min_length=1, max_length=255)
    asset_type: str = Field(description="checkpoint | lora | vae | embedding | controlnet")
    content_type: str = Field(default="application/octet-stream")
    size_bytes: int = Field(gt=0, description="File size in bytes")
    description: str | None = None
    tags: list[str] = Field(default_factory=list)


class PresignedUploadResponse(BaseModel):
    """Response with presigned upload URL."""

    upload_url: str
    storage_uri: str
    asset_id: UUID
    expires_in: int = Field(description="URL expiration in seconds")
    message: str


class ConfirmUploadRequest(BaseModel):
    """Request to confirm a presigned upload completed."""

    checksum: str | None = Field(None, description="SHA256 hash of uploaded file")


# === Asset Types ===

ASSET_TYPES = {
    "checkpoint": {
        "name": "Checkpoint",
        "description": "Base model checkpoints (SD 1.5, SDXL, Flux, etc.)",
        "extensions": [".safetensors", ".ckpt"],
        "icon": "🧬",
        "max_size_gb": 20,
    },
    "lora": {
        "name": "LoRA",
        "description": "Low-rank adaptations for style/subject transfer",
        "extensions": [".safetensors"],
        "icon": "🎨",
        "max_size_gb": 1,
    },
    "vae": {
        "name": "VAE",
        "description": "Variational autoencoders for image decoding",
        "extensions": [".safetensors", ".pt"],
        "icon": "🔮",
        "max_size_gb": 2,
    },
    "embedding": {
        "name": "Embedding",
        "description": "Textual inversions and embeddings",
        "extensions": [".safetensors", ".pt"],
        "icon": "💎",
        "max_size_gb": 0.1,
    },
    "controlnet": {
        "name": "ControlNet",
        "description": "Conditioning models for structural control",
        "extensions": [".safetensors"],
        "icon": "🎛️",
        "max_size_gb": 5,
    },
}


# === Helper Functions ===


def _validate_asset_type(asset_type: str) -> None:
    """Validate asset type is supported."""
    if asset_type not in ASSET_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid asset_type. Must be one of: {', '.join(ASSET_TYPES.keys())}",
        )


def _validate_file_extension(filename: str, asset_type: str) -> None:
    """Validate file extension matches asset type."""
    allowed_extensions = ASSET_TYPES[asset_type]["extensions"]
    if not any(filename.lower().endswith(ext) for ext in allowed_extensions):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid file extension for {asset_type}. Allowed: {', '.join(allowed_extensions)}",
        )


async def _enrich_asset_response(asset: Asset) -> dict[str, Any]:
    """Add public URL to asset response."""
    storage = await get_storage()
    return {
        "id": asset.id,
        "name": asset.name,
        "description": asset.description,
        "asset_type": asset.asset_type,
        "storage_uri": asset.storage_uri,
        "public_url": storage.get_public_url(asset.storage_uri),
        "size_bytes": asset.size_bytes,
        "checksum": asset.checksum,
        "tags": asset.tags,
        "preview_url": asset.preview_url,
        "asset_metadata": asset.asset_metadata,
        "is_public": asset.is_public,
        "created_at": asset.created_at,
        "updated_at": asset.updated_at,
    }


# === Endpoints ===


@router.get("/", response_model=AssetList)
async def list_assets(
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[JanuaUser, Depends(get_current_user)],
    asset_type: str | None = Query(None, description="Filter by asset type"),
    tag: str | None = Query(None, description="Filter by tag"),
    public_only: bool = Query(False, description="Show only public assets"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
) -> AssetList:
    """
    List available assets.

    Browse the material repository.
    """
    # Build query
    query = select(Asset).where(Asset.is_deleted == False)  # noqa: E712

    # Filter by visibility
    if public_only:
        query = query.where(Asset.is_public == True)  # noqa: E712
    else:
        # Own assets + public assets
        query = query.where(
            (Asset.user_id == user.id) | (Asset.is_public == True)  # noqa: E712
        )

    # Filter by asset type
    if asset_type:
        _validate_asset_type(asset_type)
        query = query.where(Asset.asset_type == asset_type)

    # Filter by tag
    if tag:
        query = query.where(Asset.tags.contains([tag]))

    # Count total
    count_query = select(func.count()).select_from(query.subquery())
    total = await db.scalar(count_query) or 0

    # Fetch page
    query = query.order_by(Asset.created_at.desc())
    query = query.offset(skip).limit(limit)
    result = await db.execute(query)
    assets = list(result.scalars().all())

    # Enrich with public URLs
    enriched_assets = [await _enrich_asset_response(a) for a in assets]

    return AssetList(
        assets=[AssetResponse(**a) for a in enriched_assets],
        total=total,
        skip=skip,
        limit=limit,
    )


@router.get("/types")
async def list_asset_types() -> dict[str, Any]:
    """
    List asset types.

    The categories of raw materials.
    """
    return {
        "types": ASSET_TYPES,
    }


@router.get("/{asset_id}", response_model=AssetResponse)
async def get_asset(
    asset_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[JanuaUser, Depends(get_current_user)],
) -> AssetResponse:
    """
    Get an asset by ID.

    Examine a specific material.
    """
    query = select(Asset).where(
        Asset.id == asset_id,
        Asset.is_deleted == False,  # noqa: E712
    )
    result = await db.execute(query)
    asset = result.scalar_one_or_none()

    if asset is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Asset not found in the vault.",
        )

    # Check access
    if not asset.is_public and asset.user_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. This material is private.",
        )

    enriched = await _enrich_asset_response(asset)
    return AssetResponse(**enriched)


@router.post("/", response_model=AssetUploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_asset(
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[JanuaUser, Depends(get_current_user)],
    file: UploadFile = File(...),
    name: str = Form(...),
    asset_type: str = Form(...),
    description: str | None = Form(None),
    tags: str = Form(""),  # Comma-separated
    is_public: bool = Form(False),
) -> AssetUploadResponse:
    """
    Upload a new asset.

    Add raw materials to the vault.

    Note: For large files (>100MB), use the presigned URL endpoint instead.
    """
    storage = await get_storage()

    if not storage.is_configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Storage not configured. The vault is offline.",
        )

    # Validate asset type
    _validate_asset_type(asset_type)

    # Validate file extension
    if file.filename:
        _validate_file_extension(file.filename, asset_type)

    # Read file content
    content = await file.read()
    size_bytes = len(content)

    # Check size limit
    max_size_gb = ASSET_TYPES[asset_type]["max_size_gb"]
    max_size_bytes = int(max_size_gb * 1024 * 1024 * 1024)
    if size_bytes > max_size_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File too large. Maximum for {asset_type}: {max_size_gb}GB",
        )

    # Calculate checksum
    checksum = hashlib.sha256(content).hexdigest()

    # Generate storage key
    unique_id = uuid4().hex[:8]
    safe_filename = file.filename or f"asset_{unique_id}"
    key = f"assets/{asset_type}/{user.id}/{unique_id}_{safe_filename}"

    # Upload to R2
    try:
        # Use boto3 directly for actual upload
        from ceq_api.config import get_settings
        import boto3
        from botocore.config import Config

        settings = get_settings()
        s3_client = boto3.client(
            "s3",
            endpoint_url=settings.r2_endpoint,
            aws_access_key_id=settings.r2_access_key,
            aws_secret_access_key=settings.r2_secret_key,
            config=Config(signature_version="s3v4"),
        )

        s3_client.put_object(
            Bucket=settings.r2_bucket,
            Key=key,
            Body=content,
            ContentType=file.content_type or "application/octet-stream",
        )
        storage_uri = f"r2://{settings.r2_bucket}/{key}"

    except Exception as e:
        logger.error(f"Failed to upload asset to R2: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to upload to storage. The vault rejected the material.",
        )

    # Parse tags
    tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else []

    # Create database record
    asset = Asset(
        name=name,
        description=description,
        asset_type=asset_type,
        storage_uri=storage_uri,
        size_bytes=size_bytes,
        checksum=checksum,
        tags=tag_list,
        asset_metadata={},
        user_id=user.id,
        org_id=user.org_id,
        is_public=is_public,
    )

    db.add(asset)
    await db.flush()
    await db.refresh(asset)

    return AssetUploadResponse(
        id=asset.id,
        name=asset.name,
        storage_uri=asset.storage_uri,
        public_url=storage.get_public_url(asset.storage_uri),
        message="Material secured in the vault. ✨",
    )


@router.post("/presigned-url", response_model=PresignedUploadResponse)
async def get_presigned_upload_url(
    data: PresignedUploadRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[JanuaUser, Depends(get_current_user)],
) -> PresignedUploadResponse:
    """
    Get a presigned URL for direct R2 upload.

    For large files - upload directly to storage.
    After upload completes, call POST /assets/{id}/confirm to finalize.
    """
    storage = await get_storage()

    if not storage.is_configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Storage not configured. The vault is offline.",
        )

    # Validate asset type
    _validate_asset_type(data.asset_type)

    # Validate file extension
    _validate_file_extension(data.filename, data.asset_type)

    # Check size limit
    max_size_gb = ASSET_TYPES[data.asset_type]["max_size_gb"]
    max_size_bytes = int(max_size_gb * 1024 * 1024 * 1024)
    if data.size_bytes > max_size_bytes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File too large. Maximum for {data.asset_type}: {max_size_gb}GB",
        )

    # Generate storage key
    unique_id = uuid4().hex[:8]
    key = f"assets/{data.asset_type}/{user.id}/{unique_id}_{data.filename}"

    # Create pending asset record
    asset = Asset(
        name=data.filename,
        description=data.description,
        asset_type=data.asset_type,
        storage_uri=f"r2://pending/{key}",  # Mark as pending
        size_bytes=data.size_bytes,
        tags=data.tags,
        asset_metadata={"status": "pending_upload"},
        user_id=user.id,
        org_id=user.org_id,
        is_public=False,
    )

    db.add(asset)
    await db.flush()
    await db.refresh(asset)

    # Generate presigned upload URL
    expires_in = 3600  # 1 hour
    upload_data = await storage.generate_upload_url(
        key=key,
        content_type=data.content_type,
        expires_in=expires_in,
    )

    # Update asset with actual storage URI
    asset.storage_uri = upload_data["storage_uri"]
    await db.flush()

    return PresignedUploadResponse(
        upload_url=upload_data["upload_url"],
        storage_uri=upload_data["storage_uri"],
        asset_id=asset.id,
        expires_in=expires_in,
        message="Vault portal opened. Upload directly, then confirm. ⚡",
    )


@router.post("/{asset_id}/confirm", response_model=AssetResponse)
async def confirm_upload(
    asset_id: UUID,
    data: ConfirmUploadRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[JanuaUser, Depends(get_current_user)],
) -> AssetResponse:
    """
    Confirm a presigned upload completed.

    Finalize the asset after direct upload.
    """
    query = select(Asset).where(
        Asset.id == asset_id,
        Asset.user_id == user.id,
        Asset.is_deleted == False,  # noqa: E712
    )
    result = await db.execute(query)
    asset = result.scalar_one_or_none()

    if asset is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Asset not found or not owned by you.",
        )

    # Update metadata
    asset.asset_metadata = {"status": "confirmed"}
    if data.checksum:
        asset.checksum = data.checksum

    await db.flush()
    await db.refresh(asset)

    enriched = await _enrich_asset_response(asset)
    return AssetResponse(**enriched)


@router.delete("/{asset_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_asset(
    asset_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[JanuaUser, Depends(get_current_user)],
) -> None:
    """
    Delete an asset.

    Remove materials from the vault.
    """
    query = select(Asset).where(
        Asset.id == asset_id,
        Asset.user_id == user.id,
        Asset.is_deleted == False,  # noqa: E712
    )
    result = await db.execute(query)
    asset = result.scalar_one_or_none()

    if asset is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Asset not found or not owned by you.",
        )

    # Delete from R2
    storage = await get_storage()
    try:
        await storage.delete_object(asset.storage_uri)
        logger.info(f"Deleted asset from R2: {asset.storage_uri}")
    except Exception as e:
        logger.warning(f"Failed to delete asset from R2: {e}")
        # Continue with soft delete even if R2 delete fails

    # Soft delete
    asset.is_deleted = True
    await db.flush()
