"""Standard card renderer.

Produces a 512x768 PNG with a gradient background derived from the accent
color, a bold title, optional subtitle, optional glyph, optional rarity
badge, and optional description. Deterministic: same input → same bytes.

Bump `version` when the visual output changes so cached renders are
invalidated.
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

# Font resolution: bundled → system DejaVu (prod Linux) → platform fallbacks (dev).
_BUNDLED_FONT_DIR = Path(__file__).parent.parent / "assets" / "fonts"

# Per-role fallback chain. Each role points at a list of (dir, filename) pairs
# tried in order. First existing file wins.
_FONT_CHAIN: dict[str, list[tuple[str, str]]] = {
    "DejaVuSans-Bold.ttf": [
        ("/usr/share/fonts/truetype/dejavu", "DejaVuSans-Bold.ttf"),
        ("/usr/share/fonts/dejavu", "DejaVuSans-Bold.ttf"),
        ("/System/Library/Fonts/Supplemental", "Arial Bold.ttf"),
        ("/Library/Fonts", "Arial Bold.ttf"),
        ("C:\\Windows\\Fonts", "arialbd.ttf"),
    ],
    "DejaVuSans.ttf": [
        ("/usr/share/fonts/truetype/dejavu", "DejaVuSans.ttf"),
        ("/usr/share/fonts/dejavu", "DejaVuSans.ttf"),
        ("/System/Library/Fonts/Supplemental", "Arial.ttf"),
        ("/Library/Fonts", "Arial.ttf"),
        ("C:\\Windows\\Fonts", "arial.ttf"),
    ],
    "DejaVuSans-Oblique.ttf": [
        ("/usr/share/fonts/truetype/dejavu", "DejaVuSans-Oblique.ttf"),
        ("/usr/share/fonts/dejavu", "DejaVuSans-Oblique.ttf"),
        ("/System/Library/Fonts/Supplemental", "Arial Italic.ttf"),
        ("/Library/Fonts", "Arial Italic.ttf"),
        ("C:\\Windows\\Fonts", "ariali.ttf"),
    ],
}


def _resolve_font(filename: str, size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    # Bundled first — ships with the image for guaranteed visual consistency.
    bundled = _BUNDLED_FONT_DIR / filename
    if bundled.exists():
        return ImageFont.truetype(str(bundled), size=size)
    # Fallback chain.
    for directory, fname in _FONT_CHAIN.get(filename, []):
        path = Path(directory) / fname
        if path.exists():
            return ImageFont.truetype(str(path), size=size)
    return ImageFont.load_default()


def _hex_to_rgb(value: str) -> tuple[int, int, int]:
    value = value.lstrip("#")
    if len(value) == 3:
        value = "".join(c * 2 for c in value)
    if len(value) != 6:
        raise ValueError(f"invalid hex color: {value!r}")
    return int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16)


def _mix(a: tuple[int, int, int], b: tuple[int, int, int], t: float) -> tuple[int, int, int]:
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))  # type: ignore[return-value]


def _vertical_gradient(
    size: tuple[int, int],
    top: tuple[int, int, int],
    bottom: tuple[int, int, int],
) -> Image.Image:
    w, h = size
    img = Image.new("RGB", size, top)
    px = img.load()
    assert px is not None
    for y in range(h):
        t = y / max(h - 1, 1)
        color = _mix(top, bottom, t)
        for x in range(w):
            px[x, y] = color
    return img


def _wrap_text(text: str, font: ImageFont.FreeTypeFont | ImageFont.ImageFont, max_width: int) -> list[str]:
    """Greedy word-wrap. Works with both FreeType and default fonts."""
    words = text.split()
    if not words:
        return []
    lines: list[str] = []
    current = words[0]
    for word in words[1:]:
        trial = f"{current} {word}"
        if _text_width(trial, font) <= max_width:
            current = trial
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return lines


def _text_width(text: str, font: ImageFont.FreeTypeFont | ImageFont.ImageFont) -> int:
    # Pillow >=10: getbbox returns (x0, y0, x1, y1).
    bbox = font.getbbox(text)
    return bbox[2] - bbox[0]


@dataclass(frozen=True)
class CardData:
    title: str
    subtitle: str = ""
    description: str = ""
    accent: str = "#3C8CFF"
    glyph: str = ""  # short unicode (emoji, letter, rune)
    badge: str = ""  # short rarity tag e.g. "R", "SR", "★★★"

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CardData:
        allowed = {"title", "subtitle", "description", "accent", "glyph", "badge"}
        if not data.get("title"):
            raise ValueError("card.title is required")
        return cls(**{k: str(v) for k, v in data.items() if k in allowed})


class CardStandardRenderer:
    """Pillow-based card renderer — 512x768 PNG."""

    template = "card-standard"
    version = "1"
    content_type = "image/png"
    extension = "png"

    WIDTH = 512
    HEIGHT = 768
    PADDING = 40
    INNER_RADIUS = 24

    def render(self, data: dict[str, Any]) -> bytes:
        card = CardData.from_dict(data)
        accent = _hex_to_rgb(card.accent)

        # Deep background — shade the accent for richness rather than black-on-color.
        top = _mix((12, 12, 18), accent, 0.25)
        bottom = _mix((6, 6, 10), accent, 0.05)

        img = _vertical_gradient((self.WIDTH, self.HEIGHT), top, bottom)
        draw = ImageDraw.Draw(img, "RGBA")

        # Inner frame — rounded rectangle stroke in accent, subtle.
        frame_inset = 16
        draw.rounded_rectangle(
            (frame_inset, frame_inset, self.WIDTH - frame_inset, self.HEIGHT - frame_inset),
            radius=self.INNER_RADIUS,
            outline=(*accent, 180),
            width=2,
        )

        title_font = _resolve_font("DejaVuSans-Bold.ttf", 44)
        subtitle_font = _resolve_font("DejaVuSans-Oblique.ttf", 22)
        body_font = _resolve_font("DejaVuSans.ttf", 20)
        glyph_font = _resolve_font("DejaVuSans-Bold.ttf", 180)
        badge_font = _resolve_font("DejaVuSans-Bold.ttf", 22)

        # Title — top-left with accent underline.
        title_y = self.PADDING + 16
        draw.text(
            (self.PADDING, title_y),
            card.title,
            font=title_font,
            fill=(245, 245, 250),
        )
        title_width = min(_text_width(card.title, title_font), self.WIDTH - 2 * self.PADDING)
        underline_y = title_y + 54
        draw.rectangle(
            (self.PADDING, underline_y, self.PADDING + title_width, underline_y + 3),
            fill=accent,
        )

        # Subtitle below title.
        if card.subtitle:
            draw.text(
                (self.PADDING, underline_y + 14),
                card.subtitle,
                font=subtitle_font,
                fill=(200, 200, 215),
            )

        # Badge — top-right corner pill.
        if card.badge:
            bw = max(_text_width(card.badge, badge_font), 40) + 24
            bh = 36
            bx1 = self.WIDTH - self.PADDING
            bx0 = bx1 - bw
            by0 = self.PADDING
            by1 = by0 + bh
            draw.rounded_rectangle((bx0, by0, bx1, by1), radius=bh // 2, fill=accent)
            tw = _text_width(card.badge, badge_font)
            draw.text(
                (bx0 + (bw - tw) // 2, by0 + 5),
                card.badge,
                font=badge_font,
                fill=(10, 10, 15),
            )

        # Glyph — centered, large, semi-transparent accent.
        if card.glyph:
            gw = _text_width(card.glyph, glyph_font)
            gh = 180
            gx = (self.WIDTH - gw) // 2
            gy = (self.HEIGHT - gh) // 2 - 20
            draw.text((gx, gy), card.glyph, font=glyph_font, fill=(*accent, 220))

        # Description — bottom, wrapped.
        if card.description:
            max_w = self.WIDTH - 2 * self.PADDING
            lines = _wrap_text(card.description, body_font, max_w)[:4]
            line_h = 26
            total_h = line_h * len(lines)
            y = self.HEIGHT - self.PADDING - total_h
            for line in lines:
                draw.text((self.PADDING, y), line, font=body_font, fill=(220, 220, 230))
                y += line_h

        # Footer stamp — muted "ceq" corner mark so recipients can trace origin.
        stamp_font = _resolve_font("DejaVuSans.ttf", 12)
        draw.text(
            (self.WIDTH - self.PADDING - 28, self.HEIGHT - self.PADDING - 6),
            "ceq",
            font=stamp_font,
            fill=(160, 160, 175),
        )

        # Optimize size — PNG optimize=True is deterministic.
        out = io.BytesIO()
        img.save(out, format="PNG", optimize=True)
        return out.getvalue()
