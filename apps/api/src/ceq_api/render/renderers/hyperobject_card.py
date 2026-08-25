"""Hyperobject card renderer.

Produces a 512x768 PNG portrait of a *hyperobject* — an entity that exists
across several ecosystem surfaces at once (a yantra4d commons cartridge, a
fashion-cabinet garment rank, a Selva species). Unlike `card-standard`, which
renders a single game-facing card face, this template is built to carry
cross-surface identity: a domain/family line, a palette drawn from the object
itself, an optional vector silhouette as the hero glyph, a provenance line
naming the surface and license, and optional per-locale name lines.

Layout hierarchy (top to bottom):

    ┌────────────────────────────────┐
    │ NAME                    [tier] │  title block + accent rule
    │ secondary name                 │
    │ DOMAIN OR FAMILY               │  small caps, letterspaced
    │                                │
    │          ╭────────╮            │  hero glyph: filled silhouette
    │          │        │            │  polygon (or monogram fallback)
    │          ╰────────╯            │
    │                                │
    │ ■ ■ ■                          │  palette chips
    │ description, wrapped           │
    │ lang · localized name          │  locale lines
    │ ──────────────────────────     │
    │ provenance · license      ceq  │  provenance rule + stamp
    └────────────────────────────────┘

Determinism contract: identical `data` MUST produce identical bytes. All
geometry is computed from integer pixel arithmetic and rounded before it
reaches Pillow, and the silhouette is rasterized at a fixed supersample
factor, so there is no platform-dependent float drift in the output.

Bump `version` when the visual output changes so cached renders under
`render/hyperobject-card/{hash}.png` are invalidated rather than served
stale. See `apps/api/README.md#render-generative-assets` for the
bump-version discipline.
"""

from __future__ import annotations

import io
from dataclasses import dataclass, field
from typing import Any

from PIL import Image, ImageDraw, ImageFilter

from ceq_api.render.renderers.card import (
    _hex_to_rgb,
    _mix,
    _resolve_font,
    _text_width,
    _vertical_gradient,
    _wrap_text,
)

# Silhouette rasterization is supersampled then downsampled for smooth edges.
# Fixed factor => deterministic bytes.
_SUPERSAMPLE = 4

# Guardrails on caller-supplied geometry. A silhouette past this many points
# is decimated (evenly, deterministically) rather than rejected — callers
# exporting from a vector tool routinely emit thousands of points.
_MAX_SILHOUETTE_POINTS = 200

# A polygon needs at least 3 distinct points to enclose area.
_MIN_SILHOUETTE_POINTS = 3

# Palette chips shown under the hero glyph.
_MAX_PALETTE = 3


def _validate_hex(value: str) -> str:
    """
    Validate a hex color, raising a *caller-legible* ValueError.

    `card._hex_to_rgb` only length-checks before handing the digits to `int(…,
    16)`, so a well-formed-length but non-hex string ("zzzzzz") escapes as
    "invalid literal for int() with base 16" — opaque when surfaced as a 422.
    Parse here so every color field fails with the same "invalid hex color"
    message regardless of how it is malformed.
    """
    try:
        _hex_to_rgb(value)
    except ValueError as exc:
        if "invalid hex color" not in str(exc):
            raise ValueError(f"invalid hex color: {value!r}") from exc
        raise
    return value


def _normalize_silhouette(raw: Any) -> tuple[tuple[float, float], ...]:
    """
    Validate and normalize a silhouette polyline.

    Accepts a closed or open normalized polyline — a sequence of [x, y] pairs
    in the 0..1 unit square. Returns a tuple of clamped float pairs, or an
    empty tuple when the input is absent or degenerate (fewer than 3 distinct
    points, i.e. it cannot enclose area). Degenerate input is *not* an error:
    the renderer falls back to a monogram glyph, because a hyperobject without
    a vector form is still a legitimate hyperobject.

    Silhouettes longer than `_MAX_SILHOUETTE_POINTS` are decimated with a
    fixed stride so output stays deterministic and the rasterizer stays cheap.
    """
    if raw is None:
        return ()
    if not isinstance(raw, (list, tuple)):
        raise ValueError("silhouette must be a list of [x, y] points")

    points: list[tuple[float, float]] = []
    for item in raw:
        if not isinstance(item, (list, tuple)) or len(item) != 2:
            raise ValueError("silhouette points must be [x, y] pairs")
        x_raw, y_raw = item
        if isinstance(x_raw, bool) or isinstance(y_raw, bool):
            raise ValueError("silhouette coordinates must be numbers")
        if not isinstance(x_raw, (int, float)) or not isinstance(y_raw, (int, float)):
            raise ValueError("silhouette coordinates must be numbers")
        # Clamp into the unit square rather than rejecting — exporters often
        # emit tiny out-of-range values from float rounding at the extremes.
        points.append((min(max(float(x_raw), 0.0), 1.0), min(max(float(y_raw), 0.0), 1.0)))

    if len(points) > _MAX_SILHOUETTE_POINTS:
        stride = len(points) / _MAX_SILHOUETTE_POINTS
        points = [points[int(i * stride)] for i in range(_MAX_SILHOUETTE_POINTS)]

    # Distinct-point check: a polyline that collapses to a point or a line
    # encloses no area and would rasterize to nothing.
    if len({(round(x, 6), round(y, 6)) for x, y in points}) < _MIN_SILHOUETTE_POINTS:
        return ()

    return tuple(points)


def _normalize_palette(raw: Any) -> tuple[str, ...]:
    """Validate up to `_MAX_PALETTE` hex colors. Extra entries are dropped."""
    if raw is None:
        return ()
    if not isinstance(raw, (list, tuple)):
        raise ValueError("palette must be a list of hex colors")
    colors: list[str] = []
    for value in list(raw)[:_MAX_PALETTE]:
        colors.append(_validate_hex(str(value)))
    return tuple(colors)


def _normalize_locale_lines(raw: Any) -> tuple[tuple[str, str], ...]:
    """Validate `[{lang, text}, ...]` into ordered (lang, text) pairs."""
    if raw is None:
        return ()
    if not isinstance(raw, (list, tuple)):
        raise ValueError("locale_lines must be a list of {lang, text} objects")
    lines: list[tuple[str, str]] = []
    for item in raw:
        if not isinstance(item, dict):
            raise ValueError("locale_lines entries must be {lang, text} objects")
        lang = str(item.get("lang", "")).strip()
        text = str(item.get("text", "")).strip()
        if not lang or not text:
            raise ValueError("locale_lines entries require both 'lang' and 'text'")
        lines.append((lang, text))
    return tuple(lines)


@dataclass(frozen=True)
class HyperobjectData:
    """Validated input for the hyperobject-card template."""

    name: str
    domain_or_family: str
    secondary_name: str = ""
    tier_or_rarity: str = ""
    accent: str = "#7C5CFF"
    description: str = ""
    provenance_line: str = ""
    palette: tuple[str, ...] = field(default_factory=tuple)
    silhouette: tuple[tuple[float, float], ...] = field(default_factory=tuple)
    locale_lines: tuple[tuple[str, str], ...] = field(default_factory=tuple)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> HyperobjectData:
        if not data.get("name"):
            raise ValueError("hyperobject.name is required")
        if not data.get("domain_or_family"):
            raise ValueError("hyperobject.domain_or_family is required")

        accent = _validate_hex(str(data.get("accent") or "#7C5CFF"))

        return cls(
            name=str(data["name"]),
            domain_or_family=str(data["domain_or_family"]),
            secondary_name=str(data.get("secondary_name") or ""),
            tier_or_rarity=str(data.get("tier_or_rarity") or ""),
            accent=accent,
            description=str(data.get("description") or ""),
            provenance_line=str(data.get("provenance_line") or ""),
            palette=_normalize_palette(data.get("palette")),
            silhouette=_normalize_silhouette(data.get("silhouette")),
            locale_lines=_normalize_locale_lines(data.get("locale_lines")),
        )


class HyperobjectCardRenderer:
    """Pillow-based hyperobject portrait — 512x768 PNG."""

    template = "hyperobject-card"
    version = "1"
    content_type = "image/png"
    extension = "png"

    WIDTH = 512
    HEIGHT = 768
    PADDING = 40
    FRAME_INSET = 16
    FRAME_RADIUS = 24

    # Hero glyph occupies a fixed square band so cards in a grid line up.
    GLYPH_BOX_TOP = 250
    GLYPH_BOX_SIZE = 260

    def render(self, data: dict[str, Any]) -> bytes:
        obj = HyperobjectData.from_dict(data)
        accent = _hex_to_rgb(obj.accent)

        # Background: shade the accent into near-black so the card reads as
        # belonging to the object rather than as color-on-black.
        top = _mix((10, 10, 16), accent, 0.28)
        bottom = _mix((5, 5, 9), accent, 0.06)
        img = _vertical_gradient((self.WIDTH, self.HEIGHT), top, bottom)

        self._draw_hero_glyph(img, obj, accent)

        draw = ImageDraw.Draw(img, "RGBA")
        self._draw_frame(draw, accent)
        body_bottom = self._draw_header(draw, obj, accent)
        self._draw_palette(draw, obj, y=self.GLYPH_BOX_TOP + self.GLYPH_BOX_SIZE + 18)
        self._draw_body(draw, obj, top_y=max(body_bottom, self.GLYPH_BOX_TOP))
        self._draw_footer(draw, obj, accent)

        out = io.BytesIO()
        img.save(out, format="PNG", optimize=True)
        return out.getvalue()

    # ---------- composition pieces ----------

    def _draw_frame(self, draw: ImageDraw.ImageDraw, accent: tuple[int, int, int]) -> None:
        draw.rounded_rectangle(
            (
                self.FRAME_INSET,
                self.FRAME_INSET,
                self.WIDTH - self.FRAME_INSET,
                self.HEIGHT - self.FRAME_INSET,
            ),
            radius=self.FRAME_RADIUS,
            outline=(*accent, 170),
            width=2,
        )

    def _draw_header(
        self,
        draw: ImageDraw.ImageDraw,
        obj: HyperobjectData,
        accent: tuple[int, int, int],
    ) -> int:
        """Name, tier pill, accent rule, secondary name, domain line."""
        name_font = _resolve_font("DejaVuSans-Bold.ttf", 40)
        secondary_font = _resolve_font("DejaVuSans-Oblique.ttf", 20)
        domain_font = _resolve_font("DejaVuSans-Bold.ttf", 14)
        tier_font = _resolve_font("DejaVuSans-Bold.ttf", 20)

        y = self.PADDING + 12

        # Tier pill first — it reserves the top-right corner so a long name
        # can be measured against the remaining width.
        tier_left = self.WIDTH - self.PADDING
        if obj.tier_or_rarity:
            pill_w = max(_text_width(obj.tier_or_rarity, tier_font), 36) + 22
            pill_h = 32
            x1 = self.WIDTH - self.PADDING
            x0 = x1 - pill_w
            draw.rounded_rectangle((x0, y, x1, y + pill_h), radius=pill_h // 2, fill=accent)
            tw = _text_width(obj.tier_or_rarity, tier_font)
            draw.text(
                (x0 + (pill_w - tw) // 2, y + 4),
                obj.tier_or_rarity,
                font=tier_font,
                fill=(8, 8, 12),
            )
            tier_left = x0 - 12

        # Name — truncated to the width the pill left behind.
        name_max_w = tier_left - self.PADDING
        name = self._truncate(obj.name, name_font, name_max_w)
        draw.text((self.PADDING, y), name, font=name_font, fill=(246, 246, 251))

        # Accent rule under the name — the card's strongest horizontal.
        rule_y = y + 50
        rule_w = min(_text_width(name, name_font), name_max_w)
        draw.rectangle((self.PADDING, rule_y, self.PADDING + rule_w, rule_y + 3), fill=accent)
        y = rule_y + 14

        if obj.secondary_name:
            secondary = self._truncate(
                obj.secondary_name, secondary_font, self.WIDTH - 2 * self.PADDING
            )
            draw.text((self.PADDING, y), secondary, font=secondary_font, fill=(198, 198, 214))
            y += 28

        # Domain/family — letterspaced small caps, the classification line.
        domain = self._truncate(
            obj.domain_or_family.upper(), domain_font, self.WIDTH - 2 * self.PADDING, spaced=True
        )
        self._draw_letterspaced(draw, (self.PADDING, y), domain, domain_font, _mix(accent, (255, 255, 255), 0.45))
        return y + 26

    def _draw_hero_glyph(
        self,
        img: Image.Image,
        obj: HyperobjectData,
        accent: tuple[int, int, int],
    ) -> None:
        """
        Hero glyph: the silhouette polygon when present, else a monogram.

        The polygon is rasterized on a supersampled mask and softened with a
        fixed-radius blur, so edges read as intentional rather than aliased.
        """
        box_x = (self.WIDTH - self.GLYPH_BOX_SIZE) // 2
        box_y = self.GLYPH_BOX_TOP

        if not obj.silhouette:
            self._draw_monogram(img, obj, accent, box_x, box_y)
            return

        # Fit the normalized polyline into the glyph box, preserving aspect
        # ratio and centering it. Integer rounding keeps this deterministic.
        xs = [p[0] for p in obj.silhouette]
        ys = [p[1] for p in obj.silhouette]
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
        span_x = max(max_x - min_x, 1e-6)
        span_y = max(max_y - min_y, 1e-6)
        scale = (self.GLYPH_BOX_SIZE * 0.88) / max(span_x, span_y)
        draw_w = span_x * scale
        draw_h = span_y * scale
        off_x = (self.GLYPH_BOX_SIZE - draw_w) / 2
        off_y = (self.GLYPH_BOX_SIZE - draw_h) / 2

        s = _SUPERSAMPLE
        mask = Image.new("L", (self.GLYPH_BOX_SIZE * s, self.GLYPH_BOX_SIZE * s), 0)
        mask_draw = ImageDraw.Draw(mask)
        polygon = [
            (
                round((off_x + (x - min_x) * scale) * s),
                round((off_y + (y - min_y) * scale) * s),
            )
            for x, y in obj.silhouette
        ]
        mask_draw.polygon(polygon, fill=255)
        mask = mask.resize((self.GLYPH_BOX_SIZE, self.GLYPH_BOX_SIZE), Image.Resampling.LANCZOS)
        mask = mask.filter(ImageFilter.GaussianBlur(radius=0.6))

        # Fill: a vertical gradient of the accent so the form has depth.
        fill = _vertical_gradient(
            (self.GLYPH_BOX_SIZE, self.GLYPH_BOX_SIZE),
            _mix(accent, (255, 255, 255), 0.35),
            _mix(accent, (0, 0, 0), 0.25),
        )
        img.paste(fill, (box_x, box_y), mask)

    def _draw_monogram(
        self,
        img: Image.Image,
        obj: HyperobjectData,
        accent: tuple[int, int, int],
        box_x: int,
        box_y: int,
    ) -> None:
        """Fallback hero: the name's first character, large and translucent."""
        glyph = obj.name.strip()[:1].upper()
        if not glyph:
            return
        draw = ImageDraw.Draw(img, "RGBA")
        font = _resolve_font("DejaVuSans-Bold.ttf", 180)
        gw = _text_width(glyph, font)
        draw.text(
            (box_x + (self.GLYPH_BOX_SIZE - gw) // 2, box_y + 30),
            glyph,
            font=font,
            fill=(*_mix(accent, (255, 255, 255), 0.2), 210),
        )

    def _draw_palette(self, draw: ImageDraw.ImageDraw, obj: HyperobjectData, y: int) -> None:
        """Palette chips — small rounded swatches, left-aligned."""
        if not obj.palette:
            return
        chip_w, chip_h, gap = 34, 10, 8
        x = self.PADDING
        for color in obj.palette:
            draw.rounded_rectangle(
                (x, y, x + chip_w, y + chip_h),
                radius=chip_h // 2,
                fill=_hex_to_rgb(color),
            )
            x += chip_w + gap

    def _draw_body(self, draw: ImageDraw.ImageDraw, obj: HyperobjectData, top_y: int) -> None:
        """Description + locale lines, stacked above the footer rule."""
        body_font = _resolve_font("DejaVuSans.ttf", 18)
        locale_font = _resolve_font("DejaVuSans.ttf", 13)
        locale_lang_font = _resolve_font("DejaVuSans-Bold.ttf", 13)

        max_w = self.WIDTH - 2 * self.PADDING
        line_h = 24
        locale_h = 18

        blocks: list[str] = []
        if obj.description:
            blocks = _wrap_text(obj.description, body_font, max_w)[:3]

        # Bottom-anchored: footer rule sits at a fixed height, body stacks up
        # from it so cards with different content still align at the base.
        footer_rule_y = self.HEIGHT - self.PADDING - 34
        total_h = line_h * len(blocks) + locale_h * len(obj.locale_lines)
        if obj.locale_lines and blocks:
            total_h += 8
        y = footer_rule_y - 16 - total_h

        for line in blocks:
            draw.text((self.PADDING, y), line, font=body_font, fill=(219, 219, 229))
            y += line_h

        if obj.locale_lines and blocks:
            y += 8
        for lang, text in obj.locale_lines:
            tag = f"{lang.upper()}"
            draw.text((self.PADDING, y), tag, font=locale_lang_font, fill=(150, 150, 168))
            tag_w = _text_width(tag, locale_lang_font)
            localized = self._truncate(text, locale_font, max_w - tag_w - 10)
            draw.text((self.PADDING + tag_w + 10, y), localized, font=locale_font, fill=(190, 190, 205))
            y += locale_h

    def _draw_footer(
        self,
        draw: ImageDraw.ImageDraw,
        obj: HyperobjectData,
        accent: tuple[int, int, int],
    ) -> None:
        """Hairline rule, provenance line, and the ceq origin stamp."""
        rule_y = self.HEIGHT - self.PADDING - 34
        draw.rectangle(
            (self.PADDING, rule_y, self.WIDTH - self.PADDING, rule_y),
            fill=(*accent, 120),
        )

        stamp_font = _resolve_font("DejaVuSans.ttf", 12)
        stamp_w = _text_width("ceq", stamp_font)
        draw.text(
            (self.WIDTH - self.PADDING - stamp_w, rule_y + 12),
            "ceq",
            font=stamp_font,
            fill=(155, 155, 172),
        )

        if obj.provenance_line:
            prov_font = _resolve_font("DejaVuSans.ttf", 12)
            prov = self._truncate(
                obj.provenance_line, prov_font, self.WIDTH - 2 * self.PADDING - stamp_w - 14
            )
            draw.text((self.PADDING, rule_y + 12), prov, font=prov_font, fill=(168, 168, 186))

    # ---------- text helpers ----------

    def _truncate(self, text: str, font: Any, max_w: int, *, spaced: bool = False) -> str:
        """Ellipsize `text` to fit `max_w`. `spaced` accounts for letterspacing."""
        measure = self._spaced_width if spaced else _text_width
        if measure(text, font) <= max_w:
            return text
        ellipsis = "…"
        trimmed = text
        while trimmed and measure(trimmed + ellipsis, font) > max_w:
            trimmed = trimmed[:-1]
        return (trimmed + ellipsis) if trimmed else ""

    @staticmethod
    def _spaced_width(text: str, font: Any) -> int:
        return sum(_text_width(ch, font) + 2 for ch in text)

    @staticmethod
    def _draw_letterspaced(
        draw: ImageDraw.ImageDraw,
        origin: tuple[int, int],
        text: str,
        font: Any,
        fill: tuple[int, int, int],
    ) -> None:
        """Draw `text` with a fixed 2px tracking — small-caps classification look."""
        x, y = origin
        for ch in text:
            draw.text((x, y), ch, font=font, fill=fill)
            x += _text_width(ch, font) + 2
