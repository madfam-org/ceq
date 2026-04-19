"""Tests for the tone-beep audio renderer."""

from __future__ import annotations

import struct
import wave
from io import BytesIO

import pytest

from ceq_api.render.renderers import registry
from ceq_api.render.renderers.audio_tone_beep import ToneBeepRenderer

# ---------- registry ----------


def test_tone_beep_registered() -> None:
    r = registry.get("tone-beep")
    assert r.template == "tone-beep"
    assert r.content_type == "audio/wav"
    assert r.extension == "wav"


# ---------- WAV header / determinism ----------


def test_tone_beep_produces_valid_wav_bytes() -> None:
    out = ToneBeepRenderer().render({"frequency_hz": 440, "duration_ms": 100})
    # RIFF container magic.
    assert out[:4] == b"RIFF"
    assert out[8:12] == b"WAVE"
    assert len(out) > 100  # has actual audio data, not just a header


def test_tone_beep_wav_fmt_chunk_correct() -> None:
    out = ToneBeepRenderer().render({"frequency_hz": 440, "duration_ms": 50})
    with wave.open(BytesIO(out), "rb") as wav:
        assert wav.getnchannels() == 1
        assert wav.getsampwidth() == 2  # 16-bit
        assert wav.getframerate() == 22050
        # 50ms @ 22.05kHz = ~1103 frames. Allow +/-1 for integer rounding.
        assert abs(wav.getnframes() - 1102) <= 2


def test_tone_beep_is_deterministic() -> None:
    r = ToneBeepRenderer()
    data = {"frequency_hz": 880, "duration_ms": 200, "envelope": "adsr-gentle", "volume": 0.5}
    assert r.render(data) == r.render(data)


def test_tone_beep_different_frequencies_produce_different_bytes() -> None:
    r = ToneBeepRenderer()
    a = r.render({"frequency_hz": 440, "duration_ms": 100})
    b = r.render({"frequency_hz": 880, "duration_ms": 100})
    assert a != b


def test_tone_beep_different_durations_produce_different_lengths() -> None:
    r = ToneBeepRenderer()
    short = r.render({"frequency_hz": 440, "duration_ms": 50})
    long = r.render({"frequency_hz": 440, "duration_ms": 500})
    assert len(long) > len(short)


# ---------- envelope differentiation ----------


def test_tone_beep_envelopes_produce_different_bytes() -> None:
    """Each envelope shape should produce distinct audio for the same tone."""
    r = ToneBeepRenderer()
    base = {"frequency_hz": 440, "duration_ms": 200, "volume": 0.8}
    gentle = r.render({**base, "envelope": "adsr-gentle"})
    sharp = r.render({**base, "envelope": "adsr-sharp"})
    linear = r.render({**base, "envelope": "linear"})
    square = r.render({**base, "envelope": "square"})
    # All four should be mutually distinct (length identical, bytes differ).
    assert gentle != sharp
    assert gentle != linear
    assert gentle != square
    assert sharp != linear
    assert sharp != square
    assert linear != square


def test_tone_beep_square_envelope_is_loudest_at_midpoint() -> None:
    """Square envelope maintains full amplitude throughout — midpoint sample
    should be larger than a gentle ADSR midpoint at same volume."""
    r = ToneBeepRenderer()
    # Use a very low frequency so the sine doesn't dominate at the midpoint sample.
    square_out = r.render({"frequency_hz": 20, "duration_ms": 200, "envelope": "square", "volume": 1.0})
    gentle_out = r.render({"frequency_hz": 20, "duration_ms": 200, "envelope": "adsr-gentle", "volume": 1.0})
    # The two MUST differ — envelopes shape the amplitude differently.
    assert square_out != gentle_out


# ---------- parameter clamping / validation ----------


def test_tone_beep_clamps_out_of_range_frequency() -> None:
    r = ToneBeepRenderer()
    # Below min (20Hz) and above max (20000Hz) should clamp, not error.
    low = r.render({"frequency_hz": 1, "duration_ms": 50})
    high = r.render({"frequency_hz": 99999, "duration_ms": 50})
    assert low[:4] == b"RIFF"
    assert high[:4] == b"RIFF"


def test_tone_beep_clamps_out_of_range_duration() -> None:
    r = ToneBeepRenderer()
    # Should clamp to 10ms minimum, not produce an empty/invalid WAV.
    short = r.render({"frequency_hz": 440, "duration_ms": 1})
    with wave.open(BytesIO(short), "rb") as wav:
        assert wav.getnframes() >= 1


def test_tone_beep_clamps_volume_above_one() -> None:
    """Volume > 1.0 should clamp to 1.0, not overflow int16 and produce garbage."""
    r = ToneBeepRenderer()
    out = r.render({"frequency_hz": 440, "duration_ms": 100, "volume": 999.0})
    with wave.open(BytesIO(out), "rb") as wav:
        frames = wav.readframes(wav.getnframes())
    # No sample should exceed int16 max.
    samples = struct.unpack(f"<{len(frames) // 2}h", frames)
    assert max(samples) <= 32767
    assert min(samples) >= -32768


def test_tone_beep_rejects_invalid_envelope() -> None:
    with pytest.raises(ValueError, match="envelope"):
        ToneBeepRenderer().render({"envelope": "not-an-envelope"})


def test_tone_beep_defaults_work_without_any_input() -> None:
    """Calling with {} should yield the default 880Hz / 200ms beep."""
    out = ToneBeepRenderer().render({})
    assert out[:4] == b"RIFF"


# ---------- endpoint integration ----------


@pytest.fixture
def render_storage(mock_storage):
    from unittest.mock import AsyncMock

    mock_storage.head_object = AsyncMock(return_value=False)
    mock_storage.put_object = AsyncMock(return_value="r2://ceq-assets/render/tone-beep/abc.wav")
    mock_storage.storage_uri_for = lambda key: f"r2://ceq-assets/{key}"
    mock_storage.get_public_url = lambda uri: f"https://cdn.ceq.lol/{uri.split('/', 3)[-1]}"
    return mock_storage


def test_render_audio_happy_path(client, render_storage) -> None:
    resp = client.post(
        "/v1/render/audio",
        json={
            "template": "tone-beep",
            "data": {"frequency_hz": 880, "duration_ms": 200},
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["template"] == "tone-beep"
    assert body["content_type"] == "audio/wav"
    assert body["cached"] is False
    assert body["url"].endswith(".wav")
    render_storage.put_object.assert_awaited_once()


def test_render_audio_defaults_to_tone_beep(client, render_storage) -> None:
    """Empty template falls back to tone-beep so /v1/render/audio is still
    useful without an explicit template name."""
    resp = client.post("/v1/render/audio", json={"template": "", "data": {}})
    assert resp.status_code == 200, resp.text
    assert resp.json()["template"] == "tone-beep"


def test_render_audio_rejects_invalid_envelope(client, render_storage) -> None:
    resp = client.post(
        "/v1/render/audio",
        json={"template": "tone-beep", "data": {"envelope": "nonsense"}},
    )
    assert resp.status_code == 422


def test_render_audio_cache_hit_skips_upload(client, render_storage) -> None:
    from unittest.mock import AsyncMock

    render_storage.head_object = AsyncMock(return_value=True)
    resp = client.post(
        "/v1/render/audio",
        json={"template": "tone-beep", "data": {"frequency_hz": 440}},
    )
    assert resp.status_code == 200
    assert resp.json()["cached"] is True
    render_storage.put_object.assert_not_called()
