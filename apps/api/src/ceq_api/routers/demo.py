"""Public landing demo endpoints — live renders without auth or credit debits.

Fixed preset payloads only. Rate-limited. Intended for ceq.lol interactive demo.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ceq_api.auth.janua import JanuaUser
from ceq_api.config import get_settings
from ceq_api.db import get_db
from ceq_api.middleware import limiter
from ceq_api.models import Template
from ceq_api.render.renderers import registry
from ceq_api.routers.render import RenderResponse, _render_asset
from ceq_api.storage import StorageClient, get_storage

router = APIRouter(prefix="/v1/demo", tags=["demo"])

# Sentinel user — credits are skipped for demo renders.
_DEMO_USER = JanuaUser(
    id=UUID("00000000-0000-0000-0000-000000000001"),
    email="demo@ceq.lol",
)


@dataclass(frozen=True)
class DemoPreset:
    """Fixed render preset exposed on the landing demo."""

    id: str
    render_family: str
    template: str
    data: dict[str, Any]
    api_path: str
    credit_cost: int


DEMO_PRESETS: dict[str, DemoPreset] = {
    "card": DemoPreset(
        id="card",
        render_family="card",
        template="card-standard",
        api_path="card",
        credit_cost=5,
        data={
            "title": "STRATUM CHRONICLE",
            "subtitle": "Obsidian palette · seed 91724",
            "description": "Landing demo card — deterministic CEQ render.",
            "accent": "#7c2d12",
            "glyph": "◆",
            "badge": "SR",
        },
    ),
    "thumbnail": DemoPreset(
        id="thumbnail",
        render_family="card",
        template="card-standard",
        api_path="card",
        credit_cost=5,
        data={
            "title": "FOUNDER DROP",
            "subtitle": "Launch post · copper accent",
            "description": "Social-ready card render from structured inputs.",
            "accent": "#f59e0b",
            "glyph": "⚡",
            "badge": "NEW",
        },
    ),
    "audio": DemoPreset(
        id="audio",
        render_family="audio",
        template="tone-beep",
        api_path="audio",
        credit_cost=3,
        data={
            "frequency_hz": 440,
            "duration_ms": 220,
            "envelope": "adsr-sharp",
            "volume": 0.6,
        },
    ),
    "plate": DemoPreset(
        id="plate",
        render_family="3d",
        template="card-plate",
        api_path="3d",
        credit_cost=10,
        data={
            "width_mm": 63.5,
            "height_mm": 88.9,
            "thickness_mm": 12.0,
            "corner_radius_mm": 4.0,
            "accent_hex": "#111827",
        },
    ),
}


class DemoStatusResponse(BaseModel):
    """Live platform snapshot for the marketing proof strip."""

    api: str = Field(..., description="'ok' when the demo surface is available.")
    demo_enabled: bool
    workflow_templates: int = Field(..., description="GPU workflow templates in registry.")
    render_templates: int = Field(..., description="Deterministic /v1/render templates.")
    render_template_names: list[str]


class DemoPresetInfo(BaseModel):
    id: str
    label: str
    title: str
    api_path: str
    credit_cost: int
    input_summary: str
    output_summary: str


@router.get(
    "/status",
    response_model=DemoStatusResponse,
    summary="Landing demo platform status",
)
async def demo_status(
    db: Annotated[AsyncSession, Depends(get_db)],
) -> DemoStatusResponse:
    settings = get_settings()
    count_result = await db.execute(select(func.count()).select_from(Template))
    workflow_count = int(count_result.scalar() or 0)
    names = registry.names()
    return DemoStatusResponse(
        api="ok" if settings.demo_enabled else "disabled",
        demo_enabled=settings.demo_enabled,
        workflow_templates=workflow_count,
        render_templates=len(names),
        render_template_names=names,
    )


@router.get(
    "/presets",
    response_model=list[DemoPresetInfo],
    summary="List fixed landing demo presets",
)
async def list_demo_presets() -> list[DemoPresetInfo]:
    labels = {
        "card": ("Card", "Card Standard", "512×768 PNG"),
        "thumbnail": ("Thumbnail", "Social Card", "512×768 PNG"),
        "audio": ("Audio", "Tone Beep", "22.05kHz WAV"),
        "plate": ("3D Plate", "Card Plate", "glTF 2.0 binary"),
    }
    summaries = {
        "card": "Stratum Chronicle, obsidian palette, seed 91724",
        "thumbnail": "Launch post, copper accent, social card",
        "audio": "A4 pulse, 220ms attack, 0.6 gain",
        "plate": "Rounded plate, 12mm depth, matte black",
    }
    return [
        DemoPresetInfo(
            id=preset.id,
            label=labels[preset.id][0],
            title=labels[preset.id][1],
            api_path=preset.api_path,
            credit_cost=preset.credit_cost,
            input_summary=summaries[preset.id],
            output_summary=labels[preset.id][2],
        )
        for preset in DEMO_PRESETS.values()
    ]


@router.post(
    "/render/{preset_id}",
    response_model=RenderResponse,
    summary="Run a fixed landing demo render (no auth, no credits)",
)
@limiter.limit("60/hour")
async def demo_render(
    request: Request,  # noqa: ARG001 — required by slowapi
    preset_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    storage: Annotated[StorageClient, Depends(get_storage)],
) -> RenderResponse:
    settings = get_settings()
    if not settings.demo_enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Public demo is disabled.",
        )

    preset = DEMO_PRESETS.get(preset_id)
    if preset is None:
        allowed = ", ".join(sorted(DEMO_PRESETS))
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"unknown demo preset: {preset_id!r} (allowed: {allowed})",
        )

    return await _render_asset(
        template=preset.template,
        data=preset.data,
        render_family=preset.render_family,
        user=_DEMO_USER,
        db=db,
        storage=storage,
        skip_credits=True,
    )
