"""Card-plate 3D renderer.

Produces a parametric rectangular plate with rounded corners as a GLB
(glTF 2.0 binary). The 3D equivalent of the card-standard template —
useful as a physical-prototype preview target, a 3D card holder in an
AR viewer, or a base mesh for downstream procedural texturing.

Output:
  - Binary glTF 2.0 (GLB) with magic "glTF" + version 2
  - One mesh, one PBR material (metallic-roughness, baseColorFactor from accent)
  - Position + normal attributes, indexed triangle mesh
  - Units in millimeters (mesh scale preserves the input mm values; consumers
    can interpret as mm or apply their own unit conversion)

Hand-rolled glTF writer (stdlib only). Deterministic: identical input
params → identical GLB bytes. No floating-point nondeterminism because
we pre-compute vertex positions from integer tessellation and pack with
a fixed struct format.

Bump `version` when output bytes would change so cached renders are
invalidated.
"""

from __future__ import annotations

import json
import math
import struct
from dataclasses import dataclass
from typing import Any

# --- glTF binary constants ---------------------------------------------------

_GLB_MAGIC = 0x46546C67  # "glTF"
_GLB_VERSION = 2
_CHUNK_JSON = 0x4E4F534A  # "JSON"
_CHUNK_BIN = 0x004E4942  # "BIN\0"

# glTF componentType enums
_COMPONENT_UNSIGNED_INT = 5125
_COMPONENT_FLOAT = 5126

# glTF primitive modes
_MODE_TRIANGLES = 4

# Corner tessellation — fixed count per quadrant for deterministic output.
# 8 segments per quadrant → smooth enough corners without bloating the mesh.
_CORNER_SEGMENTS = 8


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def _hex_to_rgb_float(value: str) -> tuple[float, float, float]:
    raw = value.lstrip("#")
    if len(raw) == 3:
        raw = "".join(c * 2 for c in raw)
    if len(raw) != 6:
        raise ValueError(f"invalid hex color: {value!r}")
    try:
        r = int(raw[0:2], 16)
        g = int(raw[2:4], 16)
        b = int(raw[4:6], 16)
    except ValueError as exc:
        raise ValueError(f"invalid hex color: {value!r}") from exc
    return r / 255.0, g / 255.0, b / 255.0


@dataclass(frozen=True)
class CardPlateData:
    width_mm: float
    height_mm: float
    thickness_mm: float
    corner_radius_mm: float
    accent_hex: str

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CardPlateData:
        width = _clamp(float(data.get("width_mm", 63.5)), 10.0, 300.0)
        height = _clamp(float(data.get("height_mm", 88.9)), 10.0, 300.0)
        thickness = _clamp(float(data.get("thickness_mm", 2.0)), 0.5, 20.0)
        radius = _clamp(float(data.get("corner_radius_mm", 4.0)), 0.0, 20.0)
        accent = str(data.get("accent_hex", "#3C8CFF"))
        # Validate hex early so render-time failures surface as 422, not 500.
        _hex_to_rgb_float(accent)
        # Corner radius can't exceed half of the smaller dimension.
        max_radius = min(width, height) / 2.0
        if radius > max_radius:
            radius = max_radius
        return cls(
            width_mm=width,
            height_mm=height,
            thickness_mm=thickness,
            corner_radius_mm=radius,
            accent_hex=accent,
        )


# --- rounded-rectangle tessellation ------------------------------------------


def _rounded_rect_outline(
    width: float,
    height: float,
    radius: float,
    corner_segments: int,
) -> list[tuple[float, float]]:
    """
    Return the 2D outline of a rounded rectangle centered at the origin,
    as an ordered list of (x, y) points forming a closed polygon. Points
    are ordered counter-clockwise so the top face (+Z) has outward normals.
    """
    hw = width / 2.0
    hh = height / 2.0
    r = radius

    # If radius is zero, return the four corners directly.
    if r == 0.0:
        return [(-hw, -hh), (hw, -hh), (hw, hh), (-hw, hh)]

    points: list[tuple[float, float]] = []

    # Corner centers (CCW from bottom-right).
    corners = [
        (hw - r, -hh + r, -math.pi / 2.0, 0.0),           # bottom-right: 270° → 360°
        (hw - r, hh - r, 0.0, math.pi / 2.0),             # top-right:     0° →  90°
        (-hw + r, hh - r, math.pi / 2.0, math.pi),        # top-left:     90° → 180°
        (-hw + r, -hh + r, math.pi, 3.0 * math.pi / 2.0), # bottom-left: 180° → 270°
    ]

    for cx, cy, start_angle, end_angle in corners:
        span = end_angle - start_angle
        for i in range(corner_segments + 1):
            t = i / corner_segments
            angle = start_angle + span * t
            x = cx + r * math.cos(angle)
            y = cy + r * math.sin(angle)
            # Avoid duplicating the shared vertex between adjacent arcs.
            if points and points[-1] == (x, y):
                continue
            points.append((x, y))

    # Close the polygon by dropping the last point if it duplicates the first.
    if len(points) >= 2 and points[-1] == points[0]:
        points.pop()

    return points


def _triangle_fan_indices(center_index: int, ring_indices: list[int]) -> list[int]:
    """Generate triangle indices fanning from `center_index` over a closed ring."""
    indices: list[int] = []
    n = len(ring_indices)
    for i in range(n):
        a = ring_indices[i]
        b = ring_indices[(i + 1) % n]
        indices.extend([center_index, a, b])
    return indices


def _build_mesh(data: CardPlateData) -> tuple[list[tuple[float, float, float]], list[tuple[float, float, float]], list[int]]:
    """
    Tessellate the rounded plate.

    Returns (positions, normals, indices):
      - positions: list of (x, y, z) in millimeters
      - normals: list of (nx, ny, nz) unit vectors, one per position
      - indices: flat triangle list
    """
    outline = _rounded_rect_outline(
        data.width_mm, data.height_mm, data.corner_radius_mm, _CORNER_SEGMENTS
    )
    half_thickness = data.thickness_mm / 2.0

    positions: list[tuple[float, float, float]] = []
    normals: list[tuple[float, float, float]] = []
    indices: list[int] = []

    # --- top face (+Z) ---
    # Fan from a center vertex so the top is one connected triangle fan.
    top_center_idx = len(positions)
    positions.append((0.0, 0.0, half_thickness))
    normals.append((0.0, 0.0, 1.0))
    top_ring_start = len(positions)
    for x, y in outline:
        positions.append((x, y, half_thickness))
        normals.append((0.0, 0.0, 1.0))
    top_ring = list(range(top_ring_start, top_ring_start + len(outline)))
    indices.extend(_triangle_fan_indices(top_center_idx, top_ring))

    # --- bottom face (-Z) ---
    # Same shape, but fan winding reversed so normals point -Z outward.
    bot_center_idx = len(positions)
    positions.append((0.0, 0.0, -half_thickness))
    normals.append((0.0, 0.0, -1.0))
    bot_ring_start = len(positions)
    for x, y in outline:
        positions.append((x, y, -half_thickness))
        normals.append((0.0, 0.0, -1.0))
    bot_ring = list(range(bot_ring_start, bot_ring_start + len(outline)))
    # Reverse winding for downward-facing face.
    for tri_start in range(0, len(_triangle_fan_indices(bot_center_idx, bot_ring)), 3):
        fan_indices = _triangle_fan_indices(bot_center_idx, bot_ring)
        tri = fan_indices[tri_start:tri_start + 3]
        indices.extend([tri[0], tri[2], tri[1]])

    # --- side walls ---
    # Each outline edge becomes a quad (two triangles) with outward-facing normals.
    # Use *separate* vertices for the walls so per-face normals are correct —
    # sharing top/bottom ring vertices would smear the normal across the edge.
    n = len(outline)
    for i in range(n):
        x0, y0 = outline[i]
        x1, y1 = outline[(i + 1) % n]
        # Outward normal = cross((edge, 0), (0, 0, 1)) normalized.
        # For CCW-ordered outline viewed from +Z, outward = (dy, -dx, 0) normalized.
        dx = x1 - x0
        dy = y1 - y0
        length = math.sqrt(dx * dx + dy * dy)
        if length == 0.0:
            # Degenerate edge — skip. Shouldn't happen given tessellation.
            continue
        nx = dy / length
        ny = -dx / length
        normal = (nx, ny, 0.0)

        # 4 new vertices for this wall quad.
        base = len(positions)
        positions.append((x0, y0, half_thickness))
        positions.append((x1, y1, half_thickness))
        positions.append((x1, y1, -half_thickness))
        positions.append((x0, y0, -half_thickness))
        for _ in range(4):
            normals.append(normal)

        # Two triangles, CCW when viewed from outside.
        indices.extend([base + 0, base + 3, base + 2])
        indices.extend([base + 0, base + 2, base + 1])

    return positions, normals, indices


# --- glTF binary serialization -----------------------------------------------


def _write_glb(
    positions: list[tuple[float, float, float]],
    normals: list[tuple[float, float, float]],
    indices: list[int],
    base_color: tuple[float, float, float],
) -> bytes:
    """Serialize mesh to a minimal GLB (glTF 2.0 binary) file."""
    # Build binary buffer: positions | normals | indices.
    # Each section is 4-byte aligned (glTF requires alignment per componentType).
    pos_bytes = bytearray()
    for x, y, z in positions:
        pos_bytes += struct.pack("<fff", x, y, z)

    norm_bytes = bytearray()
    for nx, ny, nz in normals:
        norm_bytes += struct.pack("<fff", nx, ny, nz)

    idx_bytes = bytearray()
    for i in indices:
        idx_bytes += struct.pack("<I", i)

    # Pad each section up to a 4-byte boundary.
    def _pad4(buf: bytearray) -> bytearray:
        remainder = len(buf) % 4
        if remainder:
            buf += b"\x00" * (4 - remainder)
        return buf

    pos_bytes = _pad4(pos_bytes)
    norm_bytes = _pad4(norm_bytes)
    idx_bytes = _pad4(idx_bytes)

    pos_offset = 0
    norm_offset = pos_offset + len(pos_bytes)
    idx_offset = norm_offset + len(norm_bytes)
    total_bin_length = idx_offset + len(idx_bytes)

    # Bounding box for positions (required for POSITION accessor min/max).
    min_pos = [positions[0][0], positions[0][1], positions[0][2]]
    max_pos = [positions[0][0], positions[0][1], positions[0][2]]
    for x, y, z in positions:
        if x < min_pos[0]:
            min_pos[0] = x
        if y < min_pos[1]:
            min_pos[1] = y
        if z < min_pos[2]:
            min_pos[2] = z
        if x > max_pos[0]:
            max_pos[0] = x
        if y > max_pos[1]:
            max_pos[1] = y
        if z > max_pos[2]:
            max_pos[2] = z

    gltf_json: dict[str, Any] = {
        "asset": {"version": "2.0", "generator": "ceq-card-plate-3d"},
        "scene": 0,
        "scenes": [{"nodes": [0]}],
        "nodes": [{"mesh": 0}],
        "meshes": [
            {
                "primitives": [
                    {
                        "attributes": {
                            "POSITION": 0,
                            "NORMAL": 1,
                        },
                        "indices": 2,
                        "material": 0,
                        "mode": _MODE_TRIANGLES,
                    }
                ]
            }
        ],
        "materials": [
            {
                "pbrMetallicRoughness": {
                    "baseColorFactor": [
                        base_color[0],
                        base_color[1],
                        base_color[2],
                        1.0,
                    ],
                    "metallicFactor": 0.1,
                    "roughnessFactor": 0.7,
                },
                "doubleSided": False,
            }
        ],
        "buffers": [{"byteLength": total_bin_length}],
        "bufferViews": [
            {
                "buffer": 0,
                "byteOffset": pos_offset,
                "byteLength": len(pos_bytes),
                "target": 34962,  # ARRAY_BUFFER
            },
            {
                "buffer": 0,
                "byteOffset": norm_offset,
                "byteLength": len(norm_bytes),
                "target": 34962,
            },
            {
                "buffer": 0,
                "byteOffset": idx_offset,
                "byteLength": len(idx_bytes),
                "target": 34963,  # ELEMENT_ARRAY_BUFFER
            },
        ],
        "accessors": [
            {
                "bufferView": 0,
                "componentType": _COMPONENT_FLOAT,
                "count": len(positions),
                "type": "VEC3",
                "min": min_pos,
                "max": max_pos,
            },
            {
                "bufferView": 1,
                "componentType": _COMPONENT_FLOAT,
                "count": len(normals),
                "type": "VEC3",
            },
            {
                "bufferView": 2,
                "componentType": _COMPONENT_UNSIGNED_INT,
                "count": len(indices),
                "type": "SCALAR",
            },
        ],
    }

    # Serialize JSON with sorted keys + tight separators for deterministic bytes.
    json_bytes = json.dumps(
        gltf_json, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    # JSON chunk must be padded with spaces (0x20) to 4-byte alignment.
    json_pad = (4 - len(json_bytes) % 4) % 4
    json_bytes += b" " * json_pad

    # BIN chunk (already padded above).
    bin_bytes = bytes(pos_bytes + norm_bytes + idx_bytes)

    # Compose GLB:
    # Header (12 bytes): magic, version, total length
    # JSON chunk: length (4) + type (4) + data
    # BIN chunk:  length (4) + type (4) + data
    total_length = (
        12  # header
        + 8 + len(json_bytes)
        + 8 + len(bin_bytes)
    )

    out = bytearray()
    out += struct.pack("<III", _GLB_MAGIC, _GLB_VERSION, total_length)
    out += struct.pack("<II", len(json_bytes), _CHUNK_JSON)
    out += json_bytes
    out += struct.pack("<II", len(bin_bytes), _CHUNK_BIN)
    out += bin_bytes
    return bytes(out)


class CardPlateRenderer:
    """Parametric rounded-rectangle plate → GLB (glTF 2.0 binary)."""

    template = "card-plate"
    version = "1"
    content_type = "model/gltf-binary"
    extension = "glb"

    def render(self, data: dict[str, Any]) -> bytes:
        params = CardPlateData.from_dict(data)
        positions, normals, indices = _build_mesh(params)
        base_color = _hex_to_rgb_float(params.accent_hex)
        return _write_glb(positions, normals, indices, base_color)
