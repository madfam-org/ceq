"""Tests for the /v1/render pipeline."""

from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy import select

from ceq_api.models import CreditLedgerEntry, CreditLedgerType
from ceq_api.render.hash import render_hash
from ceq_api.render.renderers import registry
from ceq_api.render.renderers.card import CardStandardRenderer
from ceq_api.routers import render as render_router

# ---------- hash ----------


def test_render_hash_is_deterministic() -> None:
    h1 = render_hash("t", {"a": 1, "b": 2}, "1")
    h2 = render_hash("t", {"b": 2, "a": 1}, "1")
    assert h1 == h2


def test_render_hash_varies_with_data() -> None:
    h1 = render_hash("t", {"a": 1}, "1")
    h2 = render_hash("t", {"a": 2}, "1")
    assert h1 != h2


def test_render_hash_varies_with_template() -> None:
    h1 = render_hash("a", {}, "1")
    h2 = render_hash("b", {}, "1")
    assert h1 != h2


def test_render_hash_varies_with_version() -> None:
    h1 = render_hash("t", {}, "1")
    h2 = render_hash("t", {}, "2")
    assert h1 != h2


# ---------- registry ----------


def test_card_standard_registered() -> None:
    r = registry.get("card-standard")
    assert r.template == "card-standard"
    assert r.content_type == "image/png"
    assert r.extension == "png"


def test_unknown_template_raises() -> None:
    with pytest.raises(KeyError):
        registry.get("does-not-exist")


# ---------- renderer ----------


def test_card_renderer_produces_png_bytes() -> None:
    data = {
        "title": "Volcán",
        "subtitle": "Elemental / Fire",
        "description": "A fiery catalyst.",
        "accent": "#FF5A3C",
        "badge": "R",
        "glyph": "A",
    }
    out = CardStandardRenderer().render(data)
    assert out[:8] == b"\x89PNG\r\n\x1a\n"
    assert len(out) > 1000  # reasonable PNG size


def test_card_renderer_is_deterministic() -> None:
    data = {"title": "Same", "subtitle": "Input", "accent": "#123456"}
    r = CardStandardRenderer()
    assert r.render(data) == r.render(data)


def test_card_renderer_requires_title() -> None:
    with pytest.raises(ValueError, match="title"):
        CardStandardRenderer().render({})


def test_card_renderer_rejects_bad_hex() -> None:
    with pytest.raises(ValueError, match="hex"):
        CardStandardRenderer().render({"title": "X", "accent": "notacolor"})


# ---------- endpoint ----------


@pytest.fixture
def render_storage(mock_storage):
    """Storage mock that supports head/put for render cache."""
    mock_storage.head_object = AsyncMock(return_value=False)
    mock_storage.put_object = AsyncMock(return_value="r2://ceq-assets/render/card-standard/abc.png")
    mock_storage.storage_uri_for = lambda key: f"r2://ceq-assets/{key}"
    mock_storage.get_public_url = lambda uri: f"https://cdn.ceq.lol/{uri.split('/', 3)[-1]}"
    return mock_storage


def test_render_card_happy_path(client, render_storage) -> None:
    resp = client.post(
        "/v1/render/card",
        json={
            "template": "card-standard",
            "data": {"title": "Volcán", "accent": "#FF5A3C"},
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["template"] == "card-standard"
    assert body["content_type"] == "image/png"
    assert body["cached"] is False
    assert body["url"].startswith("https://")
    assert body["storage_uri"].startswith("r2://")
    assert len(body["hash"]) == 64

    render_storage.put_object.assert_awaited_once()


def test_render_card_cache_hit_skips_upload(client, render_storage) -> None:
    render_storage.head_object = AsyncMock(return_value=True)
    resp = client.post(
        "/v1/render/card",
        json={
            "template": "card-standard",
            "data": {"title": "Cached", "accent": "#00FF00"},
        },
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["cached"] is True
    render_storage.put_object.assert_not_called()


def test_render_thumbnail_unknown_template_returns_404(client, render_storage) -> None:
    resp = client.post(
        "/v1/render/thumbnail",
        json={"template": "nope", "data": {"title": "x"}},
    )
    assert resp.status_code == 404


def test_render_rejects_invalid_data(client, render_storage) -> None:
    resp = client.post(
        "/v1/render/card",
        json={"template": "card-standard", "data": {}},  # missing title
    )
    assert resp.status_code == 422


def test_render_audio_unknown_template_returns_404(client, render_storage) -> None:
    """/audio now ships with `tone-beep`; unknown templates 404 like other families."""
    resp = client.post(
        "/v1/render/audio",
        json={"template": "nope", "data": {}},
    )
    assert resp.status_code == 404


def test_render_3d_unknown_template_returns_404(client, render_storage) -> None:
    """/3d now ships with `card-plate`; unknown templates 404 like other families."""
    resp = client.post(
        "/v1/render/3d",
        json={"template": "nope", "data": {}},
    )
    assert resp.status_code == 404


def test_list_templates(client, render_storage) -> None:
    resp = client.get("/v1/render/templates")
    assert resp.status_code == 200
    templates = resp.json()
    names = {t["name"] for t in templates}
    # All three built-ins should be exposed: image, audio, 3D.
    assert "card-standard" in names
    assert "tone-beep" in names
    assert "card-plate" in names


def test_render_returns_500_when_r2_upload_fails(client, render_storage) -> None:
    """If put_object raises, return 500 — don't leak half-state into the response."""
    render_storage.put_object = AsyncMock(side_effect=RuntimeError("R2 is down"))
    resp = client.post(
        "/v1/render/card",
        json={
            "template": "card-standard",
            "data": {"title": "Wreckage", "accent": "#808080"},
        },
    )
    assert resp.status_code == 500
    assert "cache write" in resp.json()["detail"]


def test_render_when_storage_not_configured_returns_503(client, render_storage) -> None:
    render_storage.is_configured = False
    resp = client.post(
        "/v1/render/card",
        json={"template": "card-standard", "data": {"title": "X"}},
    )
    assert resp.status_code == 503


def test_thumbnail_requires_explicit_template(client, render_storage) -> None:
    """Unlike /card, /thumbnail requires the caller to name the template."""
    resp = client.post(
        "/v1/render/thumbnail",
        json={"template": "", "data": {"title": "x"}},
    )
    assert resp.status_code == 404


def test_same_inputs_produce_same_hash_across_requests(client, render_storage) -> None:
    """Determinism contract: two identical requests return the same hash + storage_uri."""
    payload = {
        "template": "card-standard",
        "data": {"title": "Repeat", "accent": "#123456", "badge": "R"},
    }
    r1 = client.post("/v1/render/card", json=payload)
    r2 = client.post("/v1/render/card", json=payload)
    assert r1.status_code == 200 and r2.status_code == 200
    assert r1.json()["hash"] == r2.json()["hash"]
    assert r1.json()["storage_uri"] == r2.json()["storage_uri"]


def test_different_inputs_produce_different_hashes(client, render_storage) -> None:
    p1 = {"template": "card-standard", "data": {"title": "A"}}
    p2 = {"template": "card-standard", "data": {"title": "B"}}
    r1 = client.post("/v1/render/card", json=p1)
    r2 = client.post("/v1/render/card", json=p2)
    assert r1.json()["hash"] != r2.json()["hash"]


@pytest.mark.asyncio
async def test_render_card_debits_credits_on_cache_miss(
    async_client,
    db_session,
    mock_user,
    render_storage,
    monkeypatch,
) -> None:
    monkeypatch.setattr(render_router.settings, "render_credit_debits_enabled", True)
    await _grant_credits(db_session, mock_user.id, mock_user.org_id, amount=10)

    response = await async_client.post(
        "/v1/render/card",
        json={
            "template": "card-standard",
            "data": {"title": "Paid render", "accent": "#FF5A3C"},
        },
    )

    assert response.status_code == 200, response.text
    body = response.json()
    result = await db_session.execute(
        select(CreditLedgerEntry).where(
            CreditLedgerEntry.transaction_type == CreditLedgerType.DEBIT.value
        )
    )
    debit = result.scalar_one()
    assert debit.user_id == mock_user.id
    assert debit.org_id == mock_user.org_id
    assert debit.amount == -5
    assert debit.reason == "render:card:card-standard"
    assert debit.idempotency_key == f"render:{mock_user.id}:card-standard:{body['hash']}"
    assert debit.ledger_metadata["storage_uri"] == body["storage_uri"]


@pytest.mark.asyncio
async def test_render_card_rejects_insufficient_credits_before_rendering(
    async_client,
    render_storage,
    monkeypatch,
) -> None:
    monkeypatch.setattr(render_router.settings, "render_credit_debits_enabled", True)

    response = await async_client.post(
        "/v1/render/card",
        json={
            "template": "card-standard",
            "data": {"title": "No balance", "accent": "#FF5A3C"},
        },
    )

    assert response.status_code == 402
    assert response.json()["detail"]["message"] == "Insufficient CEQ credits."
    render_storage.put_object.assert_not_called()


@pytest.mark.asyncio
async def test_render_card_cache_hit_does_not_debit_credits(
    async_client,
    db_session,
    render_storage,
    monkeypatch,
) -> None:
    monkeypatch.setattr(render_router.settings, "render_credit_debits_enabled", True)
    render_storage.head_object = AsyncMock(return_value=True)

    response = await async_client.post(
        "/v1/render/card",
        json={
            "template": "card-standard",
            "data": {"title": "Cached paid render", "accent": "#FF5A3C"},
        },
    )

    assert response.status_code == 200, response.text
    assert response.json()["cached"] is True
    render_storage.put_object.assert_not_called()

    result = await db_session.execute(
        select(CreditLedgerEntry).where(
            CreditLedgerEntry.transaction_type == CreditLedgerType.DEBIT.value
        )
    )
    assert result.scalars().all() == []


async def _grant_credits(db_session, user_id, org_id, *, amount: int) -> None:
    db_session.add(
        CreditLedgerEntry(
            user_id=user_id,
            org_id=org_id,
            amount=amount,
            transaction_type=CreditLedgerType.GRANT.value,
            reason="test grant",
            idempotency_key=f"render-test-grant-{uuid4()}",
            ledger_metadata={},
        )
    )
    await db_session.flush()
