"""
/v1/render — generic asset generation.

Deterministic, cached renders. Given a template + data, return a stable public
URL. Identical inputs hit the R2 cache and skip re-rendering.

This is CEQ's "generic renderer" surface — currently image-only (cards).
Audio and 3D endpoints are stubs exposing the same request shape so callers
can integrate against a stable contract while the backends are built out.
"""

from __future__ import annotations

import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from ceq_api.auth import JanuaUser, get_current_user
from ceq_api.render import RenderCache, registry, render_hash
from ceq_api.storage import StorageClient, get_storage

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------- schemas ----------


class RenderRequest(BaseModel):
    """Generic render request."""

    template: str = Field(..., description="Template identifier (e.g. 'card-standard').")
    data: dict[str, Any] = Field(..., description="Template-specific input.")


class RenderResponse(BaseModel):
    """Render response — identical shape for cache hit and miss."""

    url: str = Field(..., description="Public URL for the rendered asset.")
    storage_uri: str = Field(..., description="Internal R2 URI (r2://bucket/key).")
    hash: str = Field(..., description="Deterministic input hash.")
    template: str
    template_version: str
    content_type: str
    cached: bool = Field(..., description="True if served from R2 cache.")


# ---------- image render (cards) ----------


@router.post(
    "/card",
    response_model=RenderResponse,
    summary="Render a card thumbnail",
    description=(
        "Render a card-shaped thumbnail from structured data. Deterministic: "
        "identical inputs return the same cached URL. Safe to call on every "
        "record save — cache lookups are cheap."
    ),
)
async def render_card(
    request: RenderRequest,
    user: Annotated[JanuaUser, Depends(get_current_user)],
    storage: Annotated[StorageClient, Depends(get_storage)],
) -> RenderResponse:
    return await _render_image(
        template=request.template or "card-standard",
        data=request.data,
        storage=storage,
    )


@router.post(
    "/thumbnail",
    response_model=RenderResponse,
    summary="Render a thumbnail (generic)",
    description=(
        "Generic thumbnail endpoint. Template name is required — callers opt "
        "into a specific visual style via `template`. See GET /v1/render/templates."
    ),
)
async def render_thumbnail(
    request: RenderRequest,
    user: Annotated[JanuaUser, Depends(get_current_user)],
    storage: Annotated[StorageClient, Depends(get_storage)],
) -> RenderResponse:
    return await _render_image(
        template=request.template,
        data=request.data,
        storage=storage,
    )


class TemplateInfo(BaseModel):
    name: str
    version: str
    content_type: str
    extension: str


@router.get(
    "/templates",
    response_model=list[TemplateInfo],
    summary="List available render templates",
)
async def list_templates(
    user: Annotated[JanuaUser, Depends(get_current_user)],
) -> list[TemplateInfo]:
    return [
        TemplateInfo(
            name=name,
            version=registry.get(name).version,
            content_type=registry.get(name).content_type,
            extension=registry.get(name).extension,
        )
        for name in registry.names()
    ]


# ---------- stubs for broader ambition ----------


@router.post(
    "/audio",
    status_code=status.HTTP_501_NOT_IMPLEMENTED,
    summary="Render an audio asset (not yet implemented)",
    description=(
        "Reserved for future audio generation. Returns 501 today. The request "
        "shape matches other render endpoints so callers can integrate early."
    ),
)
async def render_audio(
    request: RenderRequest,
    user: Annotated[JanuaUser, Depends(get_current_user)],
) -> dict[str, str]:
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="audio rendering not yet implemented; contract is stable, backend coming",
    )


@router.post(
    "/3d",
    status_code=status.HTTP_501_NOT_IMPLEMENTED,
    summary="Render a 3D asset (not yet implemented)",
    description=(
        "Reserved for future 3D generation (GLB/USDZ). Returns 501 today. Use "
        "/v1/workflows with the triposr-image-to-3d template for current 3D jobs."
    ),
)
async def render_3d(
    request: RenderRequest,
    user: Annotated[JanuaUser, Depends(get_current_user)],
) -> dict[str, str]:
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="3D rendering not yet implemented; use /v1/workflows for ComfyUI-backed 3D jobs",
    )


# ---------- internal ----------


async def _render_image(
    template: str,
    data: dict[str, Any],
    storage: StorageClient,
) -> RenderResponse:
    try:
        renderer = registry.get(template)
    except KeyError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"unknown template: {template!r}",
        ) from None

    if not storage.is_configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="render cache unavailable: R2 storage not configured",
        )

    digest = render_hash(template, data, renderer.version)
    cache = RenderCache(storage)
    key = cache.key(template, digest, renderer.extension)
    storage_uri = storage.storage_uri_for(key)

    cached = await cache.exists(key)
    if not cached:
        try:
            image_bytes = renderer.render(data)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=str(exc),
            ) from exc
        except Exception:
            logger.exception("render failed for template=%s digest=%s", template, digest)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="render failed",
            ) from None

        await cache.put(key=key, body=image_bytes, content_type=renderer.content_type)

    public_url = storage.get_public_url(storage_uri)
    return RenderResponse(
        url=public_url,
        storage_uri=storage_uri,
        hash=digest,
        template=template,
        template_version=renderer.version,
        content_type=renderer.content_type,
        cached=cached,
    )
