"""
Ecosystem Intent Router — Cross-Platform Semantic AI Brain

CEQ acts as the "brain" that understands user intent and routes requests to
the correct service in the MADFAM Solarpunk Foundry ecosystem:

  • Blueprint Harvester — static mesh catalogue, ingestion, format conversion
  • Yantra4D           — parametric CAD, scripted generation, material simulation
  • Factlas            — geospatial / urban / landscape queries

POST /v1/intent/route

The initial implementation uses a production-ready keyword/pattern classifier.
This layer is designed to be hot-swapped with an LLM-backed agent (e.g.
function-calling GPT-4o or a fine-tuned Mistral) without changing the
public API contract.
"""

import logging
import os
import re
from typing import Any, Literal

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from ceq_api.auth import JanuaUser, get_current_user

logger = logging.getLogger(__name__)

router = APIRouter()

# Upstream service base URLs — Enclii-injected
_BLUEPRINT_HARVESTER_URL = os.getenv("BLUEPRINT_HARVESTER_URL", "http://blueprint-harvester-api:8000")
_YANTRA4D_URL = os.getenv("YANTRA4D_URL", "http://yantra4d-api:8000")
_FACTLAS_URL = os.getenv("FACTLAS_URL", "http://factlas-api:8000")

Platform = Literal["blueprint-harvester", "yantra4d", "factlas", "ceq"]

# ── Intent classification rules ────────────────────────────────────────────────
# Each rule: (compiled_pattern, platform, confidence, explanation)
_RULES: list[tuple[re.Pattern[str], Platform, float, str]] = [
    # Yantra4D — parametric / scripted / simulation
    (re.compile(r"\b(parametric|openscad|cadquery|scad|cad|print|3d.print|simulate|material|heat|thermal|melt|infill|layer|nozzle|slicer|gcode|g-code)\b", re.I), "yantra4d", 0.85, "Detected parametric CAD or 3D printing intent"),
    # Factlas — geospatial / landscape / urban
    (re.compile(r"\b(map|geo|gis|terrain|city|urban|building|street|latitude|longitude|lidar|satellite|cesium|tile|landscape|region|coordinate|address|location)\b", re.I), "factlas", 0.85, "Detected geospatial / urban planning intent"),
    # Blueprint Harvester — search, catalogue, file ops
    (re.compile(r"\b(search|find|catalog|catalogue|download|upload|stl|obj|glb|gltf|mesh|file|asset|library|browse|filter|license|format|convert|normalize)\b", re.I), "blueprint-harvester", 0.80, "Detected asset cataloguing or file search intent"),
    # CEQ self — synthesis, generation, AI
    (re.compile(r"\b(generate|synthesize|synthesis|create|design|ai|model|imagine|render|image|video|flux|sdxl|hunyuan|triposr|diffusion)\b", re.I), "ceq", 0.80, "Detected generative AI / synthesis intent"),
]

_FALLBACK_PLATFORM: Platform = "blueprint-harvester"


# ── Schemas ────────────────────────────────────────────────────────────────────


class IntentRouteRequest(BaseModel):
    query: str = Field(
        ...,
        min_length=2,
        max_length=2000,
        description="Natural language query or task description from the user.",
    )
    context: dict[str, Any] = Field(
        default_factory=dict,
        description="Optional structured context (active asset ID, current view, etc.).",
    )
    forward: bool = Field(
        default=False,
        description=(
            "If True, CEQ forwards the query to the resolved platform's search/query endpoint. "
            "If False, only returns the routing decision."
        ),
    )


class IntentRouteResponse(BaseModel):
    query: str
    platform: Platform
    confidence: float = Field(ge=0.0, le=1.0)
    explanation: str
    upstream_url: str | None = None
    upstream_response: dict[str, Any] | None = None
    model: str = Field(default="keyword-classifier-v1")


# ── Classifier ─────────────────────────────────────────────────────────────────


def _classify_intent(query: str) -> tuple[Platform, float, str]:
    """
    Rule-based intent classifier.

    Scores every rule against the query, accumulates per-platform evidence,
    and returns the highest-confidence platform.
    """
    scores: dict[Platform, float] = {
        "blueprint-harvester": 0.0,
        "yantra4d": 0.0,
        "factlas": 0.0,
        "ceq": 0.0,
    }
    explanations: dict[Platform, str] = {}

    for pattern, platform, confidence, explanation in _RULES:
        if pattern.search(query):
            scores[platform] = max(scores[platform], confidence)
            explanations[platform] = explanation

    best_platform = max(scores, key=lambda p: scores[p])
    best_score = scores[best_platform]

    if best_score < 0.1:
        # No signal — fall back to the data lake
        return _FALLBACK_PLATFORM, 0.5, "No strong intent signal detected — defaulting to Blueprint Harvester."

    return best_platform, best_score, explanations.get(best_platform, "Intent matched.")


def _upstream_url_for(platform: Platform) -> str:
    """Return the search/query endpoint for each platform."""
    return {
        "blueprint-harvester": f"{_BLUEPRINT_HARVESTER_URL}/api/v1/geometry/search",
        "yantra4d": f"{_YANTRA4D_URL}/api/v1/render",
        "factlas": f"{_FACTLAS_URL}/api/v1/observations/search",
        "ceq": "",  # self — handled internally
    }[platform]


# ── Endpoint ───────────────────────────────────────────────────────────────────


@router.post(
    "/route",
    response_model=IntentRouteResponse,
    summary="Semantic ecosystem intent router",
    description=(
        "Classifies a natural language query and routes it to the correct "
        "MADFAM Foundry platform. Set 'forward=true' to proxy the query directly."
    ),
)
async def route_intent(
    data: IntentRouteRequest,
    user: JanuaUser = Depends(get_current_user),
) -> IntentRouteResponse:
    """Classify user intent and optionally forward to the resolved platform."""

    platform, confidence, explanation = _classify_intent(data.query)
    upstream_url = _upstream_url_for(platform) or None

    logger.info(
        "Intent routed",
        extra={
            "platform": platform,
            "confidence": confidence,
            "query_preview": data.query[:80],
            "forward": data.forward,
        },
    )

    upstream_response: dict[str, Any] | None = None

    if data.forward and upstream_url and platform != "ceq":
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(
                    upstream_url,
                    params={"q": data.query},
                    headers={"X-CEQ-Intent-Forward": "true", "X-CEQ-Confidence": str(confidence)},
                )
                resp.raise_for_status()
                upstream_response = resp.json()
        except httpx.HTTPStatusError as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Upstream {platform} returned {exc.response.status_code}: {exc.response.text[:200]}",
            )
        except httpx.RequestError as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Could not reach {platform} at {upstream_url}: {exc}",
            )

    return IntentRouteResponse(
        query=data.query,
        platform=platform,
        confidence=confidence,
        explanation=explanation,
        upstream_url=upstream_url,
        upstream_response=upstream_response,
        model="keyword-classifier-v1",
    )
