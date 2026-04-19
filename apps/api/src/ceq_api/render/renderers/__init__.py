"""Renderer registry.

Each renderer maps a stable template name (e.g. "card-standard") to a callable
that produces image bytes. Renderers must be pure — same input MUST produce
identical bytes — so the R2 cache stays consistent.
"""

from __future__ import annotations

from typing import Any, Protocol


class Renderer(Protocol):
    """Protocol every renderer implements."""

    template: str
    version: str  # bump when output bytes would change
    content_type: str
    extension: str

    def render(self, data: dict[str, Any]) -> bytes: ...  # noqa: E704


class RendererRegistry:
    """Lookup table of available renderers."""

    def __init__(self) -> None:
        self._by_name: dict[str, Renderer] = {}

    def register(self, renderer: Renderer) -> None:
        self._by_name[renderer.template] = renderer

    def get(self, template: str) -> Renderer:
        if template not in self._by_name:
            raise KeyError(template)
        return self._by_name[template]

    def names(self) -> list[str]:
        return sorted(self._by_name)


# Module-level singleton.
registry = RendererRegistry()


def _load_builtins() -> None:
    from ceq_api.render.renderers.audio_tone_beep import ToneBeepRenderer
    from ceq_api.render.renderers.card import CardStandardRenderer
    from ceq_api.render.renderers.card_plate_3d import CardPlateRenderer

    registry.register(CardStandardRenderer())
    registry.register(ToneBeepRenderer())
    registry.register(CardPlateRenderer())


_load_builtins()
