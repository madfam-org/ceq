"""Tests for the hyperobject-card render template and the FLUX texture graph.

Mirrors `test_render.py`'s structure (registry → renderer → endpoint) and adds
the coverage this template needs specifically: silhouette geometry edge cases
and the checked-in ComfyUI graph that the seeder loads.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from ceq_api.render.hash import render_hash
from ceq_api.render.renderers import registry
from ceq_api.render.renderers.hyperobject_card import (
    _MAX_SILHOUETTE_POINTS,
    HyperobjectCardRenderer,
)

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def _circle(points: int = 24, radius: float = 0.45) -> list[list[float]]:
    """A closed normalized polyline — the well-formed silhouette baseline."""
    return [
        [
            0.5 + radius * math.cos(2 * math.pi * i / points),
            0.5 + radius * math.sin(2 * math.pi * i / points),
        ]
        for i in range(points)
    ]


def _full_payload(**overrides: object) -> dict:
    data = {
        "name": "Hyperobject 100",
        "secondary_name": "Cartridge · sandbox",
        "domain_or_family": "yantra4d commons",
        "tier_or_rarity": "T1",
        "accent": "#7C5CFF",
        "palette": ["#7C5CFF", "#3CE0C0", "#FFB03C"],
        "silhouette": _circle(),
        "description": "A form that exists across surfaces at once.",
        "provenance_line": "yantra4d commons · CERN-OHL-W",
        "locale_lines": [
            {"lang": "es", "text": "Hiperobjeto 100"},
            {"lang": "en", "text": "Hyperobject 100"},
        ],
    }
    data.update(overrides)
    return data


# ---------- registry ----------


def test_hyperobject_card_registered() -> None:
    r = registry.get("hyperobject-card")
    assert r.template == "hyperobject-card"
    assert r.content_type == "image/png"
    assert r.extension == "png"


def test_hyperobject_card_does_not_shadow_card_standard() -> None:
    """Both card templates coexist — the new one must not replace the old."""
    assert registry.get("card-standard").template == "card-standard"
    assert "hyperobject-card" in registry.names()
    assert "card-standard" in registry.names()


# ---------- renderer: output + determinism ----------


def test_renderer_produces_png_bytes() -> None:
    out = HyperobjectCardRenderer().render(_full_payload())
    assert out[:8] == PNG_MAGIC
    assert len(out) > 1000


def test_renderer_is_deterministic() -> None:
    """Determinism contract: same input MUST produce identical bytes."""
    r = HyperobjectCardRenderer()
    payload = _full_payload()
    assert r.render(payload) == r.render(payload)


def test_renderer_is_deterministic_across_instances() -> None:
    """No instance-level state may leak into the output."""
    payload = _full_payload()
    assert HyperobjectCardRenderer().render(payload) == HyperobjectCardRenderer().render(payload)


def test_renderer_key_order_does_not_change_bytes() -> None:
    """Dict ordering is not part of the visual input."""
    r = HyperobjectCardRenderer()
    base = _full_payload()
    reordered = dict(reversed(list(base.items())))
    assert r.render(base) == r.render(reordered)


def test_different_silhouettes_produce_different_bytes() -> None:
    r = HyperobjectCardRenderer()
    a = r.render(_full_payload(silhouette=_circle(points=24)))
    b = r.render(_full_payload(silhouette=[[0.1, 0.1], [0.9, 0.15], [0.5, 0.9]]))
    assert a != b


def test_hash_changes_with_version_bump() -> None:
    """Bump-version discipline: a version bump must invalidate cached renders."""
    data = _full_payload()
    assert render_hash("hyperobject-card", data, "1") != render_hash("hyperobject-card", data, "2")


# ---------- renderer: schema validation ----------


def test_name_is_required() -> None:
    with pytest.raises(ValueError, match="name"):
        HyperobjectCardRenderer().render({"domain_or_family": "commons"})


def test_domain_or_family_is_required() -> None:
    with pytest.raises(ValueError, match="domain_or_family"):
        HyperobjectCardRenderer().render({"name": "X"})


def test_rejects_bad_accent_hex() -> None:
    with pytest.raises(ValueError, match="hex"):
        HyperobjectCardRenderer().render(
            {"name": "X", "domain_or_family": "commons", "accent": "notacolor"}
        )


def test_rejects_bad_palette_hex() -> None:
    with pytest.raises(ValueError, match="hex"):
        HyperobjectCardRenderer().render(
            _full_payload(palette=["#7C5CFF", "zzzzzz"]),
        )


@pytest.mark.parametrize("bad", ["zzzzzz", "#zzzzzz", "#12345", "", "#1234567"])
def test_rejects_non_hex_digits_with_a_legible_message(bad: str) -> None:
    """
    Right-length-but-not-hex must not leak int()'s "invalid literal" message.

    `card._hex_to_rgb` length-checks only, so "zzzzzz" would otherwise surface
    as an opaque int-parse error in the 422 body.
    """
    with pytest.raises(ValueError, match="invalid hex color"):
        HyperobjectCardRenderer().render(_full_payload(palette=[bad]))


def test_palette_is_capped_at_three() -> None:
    """Extra palette entries are dropped, not an error."""
    r = HyperobjectCardRenderer()
    three = r.render(_full_payload(palette=["#111111", "#222222", "#333333"]))
    four = r.render(_full_payload(palette=["#111111", "#222222", "#333333", "#444444"]))
    assert three == four


def test_locale_lines_require_lang_and_text() -> None:
    with pytest.raises(ValueError, match="lang"):
        HyperobjectCardRenderer().render(_full_payload(locale_lines=[{"lang": "es"}]))


def test_locale_lines_reject_non_object_entries() -> None:
    with pytest.raises(ValueError, match="locale_lines"):
        HyperobjectCardRenderer().render(_full_payload(locale_lines=["es: hola"]))


def test_optional_fields_may_all_be_omitted() -> None:
    """Only name + domain_or_family are required."""
    out = HyperobjectCardRenderer().render({"name": "Minimal", "domain_or_family": "selva"})
    assert out[:8] == PNG_MAGIC


def test_short_hex_accent_is_accepted() -> None:
    out = HyperobjectCardRenderer().render(
        {"name": "Short hex", "domain_or_family": "commons", "accent": "#abc"}
    )
    assert out[:8] == PNG_MAGIC


# ---------- renderer: silhouette edge cases ----------


def test_silhouette_absent_falls_back_to_monogram() -> None:
    out = HyperobjectCardRenderer().render(_full_payload(silhouette=None))
    assert out[:8] == PNG_MAGIC


def test_silhouette_empty_list_falls_back_to_monogram() -> None:
    """Empty is a legitimate 'no vector form', not an error."""
    r = HyperobjectCardRenderer()
    empty = r.render(_full_payload(silhouette=[]))
    absent = r.render(_full_payload(silhouette=None))
    assert empty[:8] == PNG_MAGIC
    assert empty == absent


def test_silhouette_degenerate_single_point_falls_back() -> None:
    out = HyperobjectCardRenderer().render(_full_payload(silhouette=[[0.5, 0.5]]))
    assert out[:8] == PNG_MAGIC


def test_silhouette_degenerate_repeated_points_falls_back() -> None:
    """Three identical points enclose no area — treat as no silhouette."""
    r = HyperobjectCardRenderer()
    repeated = r.render(_full_payload(silhouette=[[0.5, 0.5], [0.5, 0.5], [0.5, 0.5]]))
    assert repeated == r.render(_full_payload(silhouette=[]))


def test_silhouette_collinear_two_distinct_points_falls_back() -> None:
    out = HyperobjectCardRenderer().render(
        _full_payload(silhouette=[[0.1, 0.1], [0.9, 0.9], [0.1, 0.1]])
    )
    assert out == HyperobjectCardRenderer().render(_full_payload(silhouette=[]))


def test_silhouette_minimum_viable_triangle_renders() -> None:
    out = HyperobjectCardRenderer().render(
        _full_payload(silhouette=[[0.1, 0.9], [0.5, 0.1], [0.9, 0.9]])
    )
    assert out != HyperobjectCardRenderer().render(_full_payload(silhouette=[]))


def test_silhouette_over_200_points_is_decimated_not_rejected() -> None:
    out = HyperobjectCardRenderer().render(_full_payload(silhouette=_circle(points=1000)))
    assert out[:8] == PNG_MAGIC


def test_silhouette_decimation_is_deterministic() -> None:
    r = HyperobjectCardRenderer()
    payload = _full_payload(silhouette=_circle(points=5000))
    assert r.render(payload) == r.render(payload)


def test_silhouette_at_exactly_the_cap_renders() -> None:
    out = HyperobjectCardRenderer().render(
        _full_payload(silhouette=_circle(points=_MAX_SILHOUETTE_POINTS))
    )
    assert out[:8] == PNG_MAGIC


def test_silhouette_out_of_range_coords_are_clamped() -> None:
    """Exporters emit small out-of-range values; clamp rather than reject."""
    out = HyperobjectCardRenderer().render(
        _full_payload(silhouette=[[-0.2, 1.4], [1.3, -0.1], [0.5, 1.2]])
    )
    assert out[:8] == PNG_MAGIC


def test_silhouette_rejects_non_pair_points() -> None:
    with pytest.raises(ValueError, match=r"\[x, y\] pairs"):
        HyperobjectCardRenderer().render(_full_payload(silhouette=[[0.1, 0.2, 0.3]]))


def test_silhouette_rejects_non_numeric_coords() -> None:
    with pytest.raises(ValueError, match="numbers"):
        HyperobjectCardRenderer().render(_full_payload(silhouette=[["a", "b"], [0.2, 0.3]]))


def test_silhouette_rejects_non_list() -> None:
    with pytest.raises(ValueError, match="silhouette"):
        HyperobjectCardRenderer().render(_full_payload(silhouette="circle"))


# ---------- renderer: long-content resilience ----------


def test_long_name_is_truncated_not_overflowed() -> None:
    out = HyperobjectCardRenderer().render(_full_payload(name="Hyperobject " * 20))
    assert out[:8] == PNG_MAGIC


def test_long_description_and_provenance_render() -> None:
    out = HyperobjectCardRenderer().render(
        _full_payload(
            description="An extended description. " * 40,
            provenance_line="fashion cabinet · rank 300 · " * 10,
        )
    )
    assert out[:8] == PNG_MAGIC


# ---------- endpoint ----------


@pytest.fixture
def render_storage(mock_storage):
    """Storage mock that supports head/put for render cache."""
    mock_storage.head_object = AsyncMock(return_value=False)
    mock_storage.put_object = AsyncMock(
        return_value="r2://ceq-assets/render/hyperobject-card/abc.png"
    )
    mock_storage.storage_uri_for = lambda key: f"r2://ceq-assets/{key}"
    mock_storage.get_public_url = lambda uri: f"https://cdn.ceq.lol/{uri.split('/', 3)[-1]}"
    return mock_storage


def test_render_hyperobject_via_thumbnail_endpoint(client, render_storage) -> None:
    resp = client.post(
        "/v1/render/thumbnail",
        json={"template": "hyperobject-card", "data": _full_payload()},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["template"] == "hyperobject-card"
    assert body["template_version"] == "1"
    assert body["content_type"] == "image/png"
    assert len(body["hash"]) == 64
    assert "render/hyperobject-card/" in body["storage_uri"]


def test_render_hyperobject_invalid_data_returns_422(client, render_storage) -> None:
    resp = client.post(
        "/v1/render/thumbnail",
        json={"template": "hyperobject-card", "data": {"name": "no domain"}},
    )
    assert resp.status_code == 422


def test_hyperobject_listed_in_templates_endpoint(client, render_storage) -> None:
    resp = client.get("/v1/render/templates")
    assert resp.status_code == 200
    names = {t["name"] for t in resp.json()}
    assert "hyperobject-card" in names


def test_identical_requests_share_a_hash(client, render_storage) -> None:
    payload = {"template": "hyperobject-card", "data": _full_payload()}
    r1 = client.post("/v1/render/thumbnail", json=payload)
    r2 = client.post("/v1/render/thumbnail", json=payload)
    assert r1.json()["hash"] == r2.json()["hash"]
    assert r1.json()["storage_uri"] == r2.json()["storage_uri"]


# ---------- ComfyUI texture graph (GPU lane, parked) ----------

_REPO_ROOT = Path(__file__).resolve().parents[3]
_TEXTURE_PATH = _REPO_ROOT / "templates" / "3d" / "hyperobject-texture.json"


@pytest.fixture(scope="module")
def texture_template() -> dict:
    return json.loads(_TEXTURE_PATH.read_text(encoding="utf-8"))


def test_texture_template_file_exists() -> None:
    assert _TEXTURE_PATH.is_file()


def test_texture_template_has_required_top_level_keys(texture_template: dict) -> None:
    """Matches the `templates/3d/triposr-image-to-3d.json` file convention."""
    for key in (
        "name",
        "description",
        "category",
        "tags",
        "model_requirements",
        "vram_requirement_gb",
        "input_schema",
        "workflow",
    ):
        assert key in texture_template, f"missing key: {key}"
    assert texture_template["category"] == "3d"


def test_texture_template_input_schema_parameterizes_prompt_seed_resolution(
    texture_template: dict,
) -> None:
    props = texture_template["input_schema"]["properties"]
    for field in ("prompt", "seed", "width", "height"):
        assert field in props, f"missing input: {field}"
    assert texture_template["input_schema"]["required"] == ["prompt"]


def test_texture_template_graph_links_are_consistent(texture_template: dict) -> None:
    """Every link references real nodes; ids are unique; high-water marks hold."""
    graph = texture_template["workflow"]
    node_ids = [n["id"] for n in graph["nodes"]]
    assert len(node_ids) == len(set(node_ids)), "duplicate node ids"

    link_ids = [link[0] for link in graph["links"]]
    assert len(link_ids) == len(set(link_ids)), "duplicate link ids"

    for link_id, src_node, _src_slot, dst_node, _dst_slot, _type in graph["links"]:
        assert src_node in node_ids, f"link {link_id} from unknown node {src_node}"
        assert dst_node in node_ids, f"link {link_id} to unknown node {dst_node}"

    assert graph["last_node_id"] >= max(node_ids)
    assert graph["last_link_id"] >= max(link_ids)


def test_texture_template_declared_links_match_node_wiring(texture_template: dict) -> None:
    """Each node input `link` id must appear in the graph's link table."""
    graph = texture_template["workflow"]
    declared = {link[0] for link in graph["links"]}
    for node in graph["nodes"]:
        for socket in node.get("inputs", []):
            if socket.get("link") is not None:
                assert socket["link"] in declared, (
                    f"node {node['id']} input {socket['name']} references "
                    f"undeclared link {socket['link']}"
                )


def test_texture_template_is_flux_based(texture_template: dict) -> None:
    assert any("flux" in m.lower() for m in texture_template["model_requirements"])
    types = {n["type"] for n in texture_template["workflow"]["nodes"]}
    assert {"CheckpointLoaderSimple", "CLIPTextEncode", "KSampler", "VAEDecode"} <= types


def test_texture_template_placeholders_are_declared_inputs(texture_template: dict) -> None:
    """Every {{placeholder}} in the graph must exist in input_schema."""
    import re

    graph_text = json.dumps(texture_template["workflow"])
    placeholders = set(re.findall(r"\{\{(\w+)\}\}", graph_text))
    declared = set(texture_template["input_schema"]["properties"])
    assert placeholders <= declared, f"undeclared placeholders: {placeholders - declared}"


def test_texture_template_is_marked_gpu_lane(texture_template: dict) -> None:
    """The GPU lane is parked — the row must say so where operators will read it."""
    assert "gpu-lane" in texture_template["tags"]
    assert "parked" in texture_template["description"].lower()


# ---------- seeder wiring ----------


def test_texture_template_is_seeded(texture_template: dict) -> None:
    """The graph must reach the DB Template table via SEED_TEMPLATES."""
    from ceq_api.seed_templates import get_template_by_name

    seeded = get_template_by_name(texture_template["name"])
    assert seeded is not None, "hyperobject texture template is not in SEED_TEMPLATES"
    assert seeded["category"] == "3d"
    # Key mapping: file uses `workflow`, the DB column is `workflow_json`.
    assert "workflow" not in seeded
    assert seeded["workflow_json"] == texture_template["workflow"]


def test_seeded_entry_carries_fields_seed_db_reads() -> None:
    """seed_db.py reads these keys off each dict — all must be present."""
    from ceq_api.seed_templates import get_template_by_name

    seeded = get_template_by_name("Hyperobject Texture (FLUX)")
    assert seeded is not None
    for key in ("name", "category", "workflow_json", "input_schema"):
        assert key in seeded
    assert isinstance(seeded["tags"], list)
    assert isinstance(seeded["model_requirements"], list)
    assert isinstance(seeded["vram_requirement_gb"], int)


def test_seeded_template_names_are_unique() -> None:
    """seed_db matches on name — collisions would silently skip a row."""
    from ceq_api.seed_templates import SEED_TEMPLATES

    names = [t["name"] for t in SEED_TEMPLATES]
    assert len(names) == len(set(names))
