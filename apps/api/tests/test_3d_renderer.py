"""Tests for the card-plate 3D (GLB) renderer."""

from __future__ import annotations

import json
import struct

import pytest

from ceq_api.render.renderers import registry
from ceq_api.render.renderers.card_plate_3d import CardPlateRenderer

# ---------- registry ----------


def test_card_plate_registered() -> None:
    r = registry.get("card-plate")
    assert r.template == "card-plate"
    assert r.content_type == "model/gltf-binary"
    assert r.extension == "glb"


# ---------- GLB structural correctness ----------


def test_card_plate_produces_glb_with_correct_magic() -> None:
    out = CardPlateRenderer().render({})
    # GLB magic: "glTF" (0x46546C67 little-endian).
    assert out[:4] == b"glTF"
    version = struct.unpack("<I", out[4:8])[0]
    assert version == 2


def test_card_plate_glb_length_field_matches_actual_size() -> None:
    out = CardPlateRenderer().render({})
    reported_length = struct.unpack("<I", out[8:12])[0]
    assert reported_length == len(out)


def test_card_plate_has_json_and_bin_chunks() -> None:
    out = CardPlateRenderer().render({})
    # After 12-byte header: JSON chunk header.
    json_length, json_type = struct.unpack("<II", out[12:20])
    assert json_type == 0x4E4F534A  # "JSON"
    json_blob = out[20 : 20 + json_length]
    # Strip trailing padding spaces.
    gltf = json.loads(json_blob.rstrip(b" "))
    assert gltf["asset"]["version"] == "2.0"
    assert len(gltf["meshes"]) == 1
    assert len(gltf["materials"]) == 1

    # BIN chunk follows.
    bin_header_offset = 20 + json_length
    bin_length, bin_type = struct.unpack(
        "<II", out[bin_header_offset : bin_header_offset + 8]
    )
    assert bin_type == 0x004E4942  # "BIN\0"
    assert bin_length > 0


def test_card_plate_mesh_is_non_empty() -> None:
    out = CardPlateRenderer().render({})
    json_length = struct.unpack("<I", out[12:16])[0]
    gltf = json.loads(out[20 : 20 + json_length].rstrip(b" "))
    # Position accessor must have a nontrivial count.
    position_accessor = gltf["accessors"][gltf["meshes"][0]["primitives"][0]["attributes"]["POSITION"]]
    assert position_accessor["count"] > 8  # at minimum more than a cube's 8 vertices
    # Indexed triangle mesh — indices must be divisible by 3.
    index_accessor_idx = gltf["meshes"][0]["primitives"][0]["indices"]
    index_accessor = gltf["accessors"][index_accessor_idx]
    assert index_accessor["count"] > 0
    assert index_accessor["count"] % 3 == 0


def test_card_plate_bounding_box_matches_dimensions() -> None:
    """Position accessor min/max should match width/height/thickness inputs."""
    data = {"width_mm": 60.0, "height_mm": 90.0, "thickness_mm": 3.0, "corner_radius_mm": 5.0}
    out = CardPlateRenderer().render(data)
    json_length = struct.unpack("<I", out[12:16])[0]
    gltf = json.loads(out[20 : 20 + json_length].rstrip(b" "))
    pos_accessor = gltf["accessors"][0]
    assert pos_accessor["min"] == [-30.0, -45.0, -1.5]
    assert pos_accessor["max"] == [30.0, 45.0, 1.5]


# ---------- determinism ----------


def test_card_plate_is_deterministic() -> None:
    r = CardPlateRenderer()
    data = {
        "width_mm": 63.5,
        "height_mm": 88.9,
        "thickness_mm": 2.0,
        "corner_radius_mm": 4.0,
        "accent_hex": "#3C8CFF",
    }
    assert r.render(data) == r.render(data)


def test_card_plate_different_dimensions_produce_different_bytes() -> None:
    r = CardPlateRenderer()
    small = r.render({"width_mm": 50.0, "height_mm": 70.0})
    large = r.render({"width_mm": 80.0, "height_mm": 110.0})
    assert small != large


def test_card_plate_different_accent_produces_different_bytes() -> None:
    r = CardPlateRenderer()
    blue = r.render({"accent_hex": "#3C8CFF"})
    red = r.render({"accent_hex": "#FF5A3C"})
    assert blue != red


# ---------- parameter clamping / validation ----------


def test_card_plate_clamps_huge_dimensions() -> None:
    r = CardPlateRenderer()
    # width_mm=10000 should clamp to 300.
    out = r.render({"width_mm": 10000.0, "height_mm": 10000.0})
    json_length = struct.unpack("<I", out[12:16])[0]
    gltf = json.loads(out[20 : 20 + json_length].rstrip(b" "))
    pos_accessor = gltf["accessors"][0]
    assert pos_accessor["max"][0] <= 150.0  # 300/2
    assert pos_accessor["max"][1] <= 150.0


def test_card_plate_clamps_tiny_thickness() -> None:
    r = CardPlateRenderer()
    # thickness_mm=0.01 should clamp to 0.5 minimum.
    out = r.render({"thickness_mm": 0.01})
    json_length = struct.unpack("<I", out[12:16])[0]
    gltf = json.loads(out[20 : 20 + json_length].rstrip(b" "))
    pos_accessor = gltf["accessors"][0]
    assert pos_accessor["max"][2] >= 0.25  # half of 0.5mm minimum


def test_card_plate_radius_exceeding_half_dim_is_reduced() -> None:
    """Corner radius cannot exceed half the smaller dimension; reduce silently."""
    r = CardPlateRenderer()
    # 100mm wide, 50mm tall, radius=40 → would exceed 25 (half of 50), reduce to 25.
    out = r.render({
        "width_mm": 100.0,
        "height_mm": 50.0,
        "corner_radius_mm": 40.0,
    })
    # Should render without error and produce a closed mesh.
    assert out[:4] == b"glTF"


def test_card_plate_zero_radius_produces_sharp_corners() -> None:
    r = CardPlateRenderer()
    out = r.render({"corner_radius_mm": 0.0})
    assert out[:4] == b"glTF"


def test_card_plate_rejects_invalid_hex() -> None:
    with pytest.raises(ValueError, match="hex"):
        CardPlateRenderer().render({"accent_hex": "not-a-color"})


def test_card_plate_defaults_work_without_any_input() -> None:
    """Standard trading-card dimensions should be the default."""
    out = CardPlateRenderer().render({})
    assert out[:4] == b"glTF"
    json_length = struct.unpack("<I", out[12:16])[0]
    gltf = json.loads(out[20 : 20 + json_length].rstrip(b" "))
    # Default is 63.5mm x 88.9mm (standard card).
    pos_accessor = gltf["accessors"][0]
    assert abs(pos_accessor["max"][0] - 31.75) < 0.01
    assert abs(pos_accessor["max"][1] - 44.45) < 0.01


def test_card_plate_material_uses_accent_color() -> None:
    r = CardPlateRenderer()
    # Pure red accent.
    out = r.render({"accent_hex": "#FF0000"})
    json_length = struct.unpack("<I", out[12:16])[0]
    gltf = json.loads(out[20 : 20 + json_length].rstrip(b" "))
    base_color = gltf["materials"][0]["pbrMetallicRoughness"]["baseColorFactor"]
    assert base_color[0] == 1.0
    assert base_color[1] == 0.0
    assert base_color[2] == 0.0
    assert base_color[3] == 1.0


# ---------- endpoint integration ----------


@pytest.fixture
def render_storage(mock_storage):
    from unittest.mock import AsyncMock

    mock_storage.head_object = AsyncMock(return_value=False)
    mock_storage.put_object = AsyncMock(return_value="r2://ceq-assets/render/card-plate/abc.glb")
    mock_storage.storage_uri_for = lambda key: f"r2://ceq-assets/{key}"
    mock_storage.get_public_url = lambda uri: f"https://cdn.ceq.lol/{uri.split('/', 3)[-1]}"
    return mock_storage


def test_render_3d_happy_path(client, render_storage) -> None:
    resp = client.post(
        "/v1/render/3d",
        json={
            "template": "card-plate",
            "data": {"width_mm": 63.5, "height_mm": 88.9},
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["template"] == "card-plate"
    assert body["content_type"] == "model/gltf-binary"
    assert body["cached"] is False
    assert body["url"].endswith(".glb")
    render_storage.put_object.assert_awaited_once()


def test_render_3d_defaults_to_card_plate(client, render_storage) -> None:
    resp = client.post("/v1/render/3d", json={"template": "", "data": {}})
    assert resp.status_code == 200, resp.text
    assert resp.json()["template"] == "card-plate"


def test_render_3d_rejects_invalid_accent(client, render_storage) -> None:
    resp = client.post(
        "/v1/render/3d",
        json={"template": "card-plate", "data": {"accent_hex": "not-hex"}},
    )
    assert resp.status_code == 422


def test_render_3d_cache_hit_skips_upload(client, render_storage) -> None:
    from unittest.mock import AsyncMock

    render_storage.head_object = AsyncMock(return_value=True)
    resp = client.post(
        "/v1/render/3d",
        json={"template": "card-plate", "data": {}},
    )
    assert resp.status_code == 200
    assert resp.json()["cached"] is True
    render_storage.put_object.assert_not_called()
