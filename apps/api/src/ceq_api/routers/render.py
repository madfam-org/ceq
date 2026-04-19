"""
/v1/render — generic asset generation.

Deterministic, cached renders. Given a template + data, return a stable public
URL. Identical inputs hit the R2 cache and skip re-rendering.

Three asset families today:
  - image: /v1/render/card, /v1/render/thumbnail  (Pillow-based)
  - audio: /v1/render/audio                       (stdlib WAV synthesis)
  - 3D:    /v1/render/3d                          (stdlib GLB writer)

All three flow through a single generic dispatcher (`_render_asset`) — they
differ only in which templates they accept. The cache, hash, and response
shape are uniform across families.
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
    return await _render_asset(
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
    return await _render_asset(
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


# ---------- audio render ----------


@router.post(
    "/audio",
    response_model=RenderResponse,
    summary="Render an audio asset",
    description=(
        "Render a deterministic audio asset (WAV). Current templates: "
        "`tone-beep` (parametric sine-wave beep with ADSR envelopes — useful "
        "for notification chimes and UI feedback sounds). Deterministic, "
        "cached, same response shape as /card and /thumbnail."
    ),
)
async def render_audio(
    request: RenderRequest,
    user: Annotated[JanuaUser, Depends(get_current_user)],
    storage: Annotated[StorageClient, Depends(get_storage)],
) -> RenderResponse:
    return await _render_asset(
        template=request.template or "tone-beep",
        data=request.data,
        storage=storage,
    )


# ---------- 3D render ----------


@router.post(
    "/3d",
    response_model=RenderResponse,
    summary="Render a 3D asset",
    description=(
        "Render a deterministic 3D asset (GLB / glTF 2.0 binary). Current "
        "templates: `card-plate` (parametric rounded-rectangle plate — 3D "
        "counterpart to card-standard, useful as a physical-prototype preview "
        "or AR card holder). Deterministic, cached, same response shape as "
        "/card and /thumbnail."
    ),
)
async def render_3d(
    request: RenderRequest,
    user: Annotated[JanuaUser, Depends(get_current_user)],
    storage: Annotated[StorageClient, Depends(get_storage)],
) -> RenderResponse:
    return await _render_asset(
        template=request.template or "card-plate",
        data=request.data,
        storage=storage,
    )


# ---------- internal ----------


async def _render_asset(
    template: str,
    data: dict[str, Any],
    storage: StorageClient,
) -> RenderResponse:
    """
    Generic render dispatcher. Works for any registered renderer regardless
    of output media — image/png, audio/wav, model/gltf-binary all flow through
    the same hash + cache + response pipeline.
    """
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
            asset_bytes = renderer.render(data)
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

        try:
            await cache.put(key=key, body=asset_bytes, content_type=renderer.content_type)
        except Exception:
            logger.exception("render cache write failed for key=%s", key)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="render failed: cache write error",
            ) from None

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
