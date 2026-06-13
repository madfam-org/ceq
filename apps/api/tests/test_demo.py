"""Tests for public landing demo endpoints."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest


@pytest.fixture
def render_storage(mock_storage):
    mock_storage.head_object = AsyncMock(return_value=False)
    mock_storage.put_object = AsyncMock(return_value="r2://ceq-assets/render/demo.png")
    mock_storage.storage_uri_for = lambda key: f"r2://ceq-assets/{key}"
    mock_storage.get_public_url = lambda uri: f"https://cdn.example/{uri.split('/')[-1]}"
    mock_storage.is_configured = True
    return mock_storage


def test_demo_status_returns_template_counts(client) -> None:
    response = client.get("/v1/demo/status")
    assert response.status_code == 200
    body = response.json()
    assert body["api"] == "ok"
    assert body["demo_enabled"] is True
    assert body["render_templates"] >= 3
    assert "card-standard" in body["render_template_names"]


def test_demo_presets_lists_four_families(client) -> None:
    response = client.get("/v1/demo/presets")
    assert response.status_code == 200
    presets = response.json()
    assert len(presets) == 4
    ids = {item["id"] for item in presets}
    assert ids == {"card", "thumbnail", "audio", "plate"}


def test_demo_render_card_produces_url(client, render_storage) -> None:
    response = client.post("/v1/demo/render/card")
    assert response.status_code == 200
    body = response.json()
    assert body["template"] == "card-standard"
    assert body["url"].startswith("https://")
    assert body["cached"] is False


def test_demo_render_unknown_preset_returns_404(client) -> None:
    response = client.post("/v1/demo/render/not-real")
    assert response.status_code == 404


def test_interest_accepts_landing_tier_keys(client) -> None:
    response = client.post(
        "/v1/interest/",
        json={
            "email": "founder@studio.tld",
            "feature_key": "ceq_pro_artist",
            "wishlist": {"text": "Need private gallery + SDK"},
            "source_page": "landing_pricing",
        },
    )
    assert response.status_code == 201
    assert response.json()["status"] == "registered"
