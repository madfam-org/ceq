"""Asset management endpoints (models, LoRAs, VAEs, embeddings)."""

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from pydantic import BaseModel, Field

from ceq_api.auth import JanuaUser, get_current_user

router = APIRouter()


# === Pydantic Models ===


class AssetResponse(BaseModel):
    """Response model for an asset."""

    id: UUID
    name: str
    asset_type: str = Field(description="checkpoint | lora | vae | embedding | controlnet")
    storage_uri: str
    size_bytes: int
    description: str | None
    tags: list[str]
    preview_url: str | None
    created_at: str


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
    message: str


# === Asset Types ===

ASSET_TYPES = {
    "checkpoint": {
        "name": "Checkpoint",
        "description": "Base model checkpoints (SD 1.5, SDXL, Flux, etc.)",
        "extensions": [".safetensors", ".ckpt"],
        "icon": "🧬",
    },
    "lora": {
        "name": "LoRA",
        "description": "Low-rank adaptations for style/subject transfer",
        "extensions": [".safetensors"],
        "icon": "🎨",
    },
    "vae": {
        "name": "VAE",
        "description": "Variational autoencoders for image decoding",
        "extensions": [".safetensors", ".pt"],
        "icon": "🔮",
    },
    "embedding": {
        "name": "Embedding",
        "description": "Textual inversions and embeddings",
        "extensions": [".safetensors", ".pt"],
        "icon": "💎",
    },
    "controlnet": {
        "name": "ControlNet",
        "description": "Conditioning models for structural control",
        "extensions": [".safetensors"],
        "icon": "🎛️",
    },
}


# === Endpoints ===


@router.get("/", response_model=AssetList)
async def list_assets(
    user: Annotated[JanuaUser, Depends(get_current_user)],
    asset_type: str | None = None,
    tag: str | None = None,
    skip: int = 0,
    limit: int = 50,
) -> AssetList:
    """
    List available assets.

    Browse the material repository.
    """
    # TODO: Query database with filters
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Inventorying the vault...",
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
    user: Annotated[JanuaUser, Depends(get_current_user)],
) -> AssetResponse:
    """
    Get an asset by ID.

    Examine a specific material.
    """
    # TODO: Query database
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Locating material...",
    )


@router.post("/", response_model=AssetUploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_asset(
    user: Annotated[JanuaUser, Depends(get_current_user)],
    name: str,
    asset_type: str,
    file: UploadFile = File(...),
    description: str | None = None,
    tags: list[str] | None = None,
) -> AssetUploadResponse:
    """
    Upload a new asset.

    Add raw materials to the vault.

    Note: For large files (>100MB), use the presigned URL endpoint instead.
    """
    # TODO: Validate file type
    # TODO: Upload to R2
    # TODO: Create database record
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Vault intake processing...",
    )


@router.post("/presigned-url")
async def get_presigned_upload_url(
    user: Annotated[JanuaUser, Depends(get_current_user)],
    filename: str,
    asset_type: str,
    content_type: str,
    size_bytes: int,
) -> dict[str, str]:
    """
    Get a presigned URL for direct R2 upload.

    For large files - upload directly to storage.
    """
    # TODO: Generate presigned URL from R2
    # TODO: Create pending asset record
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Preparing vault portal...",
    )


@router.delete("/{asset_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_asset(
    asset_id: UUID,
    user: Annotated[JanuaUser, Depends(get_current_user)],
) -> None:
    """
    Delete an asset.

    Remove materials from the vault.
    """
    # TODO: Delete from R2
    # TODO: Delete database record
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Vault ejection processing...",
    )