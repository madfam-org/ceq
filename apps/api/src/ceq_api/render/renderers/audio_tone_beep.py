"""Tone-beep audio renderer.

Produces a deterministic WAV file — 16-bit PCM, 22.05kHz mono — from a
frequency, duration, envelope shape, and volume. Useful for app
notification sounds, confirmation chimes, and card-interaction feedback
where a deterministic, cache-friendly asset URL beats bundling audio
files with the client.

This is intentionally *not* a TTS / neural-audio generator. The contract
is "parametric synthesis in pure stdlib" — zero external API deps, zero
credentials, zero per-call cost. Neural audio can be a future template
(e.g. `tts-neural`) once there's a caller who needs it.

Bump `version` when output bytes would change so cached renders are
invalidated.
"""

from __future__ import annotations

import io
import math
import struct
import wave
from dataclasses import dataclass
from typing import Any

_SAMPLE_RATE_HZ = 22050
_SAMPLE_WIDTH_BYTES = 2  # 16-bit PCM
_CHANNELS = 1  # mono
_MAX_AMPLITUDE = 32767  # int16 max, leaves 1 count of headroom

_ENVELOPES = ("adsr-gentle", "adsr-sharp", "linear", "square")


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


@dataclass(frozen=True)
class ToneBeepData:
    frequency_hz: float
    duration_ms: int
    envelope: str
    volume: float

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ToneBeepData:
        freq = _clamp(float(data.get("frequency_hz", 880)), 20.0, 20000.0)
        dur = int(_clamp(float(data.get("duration_ms", 200)), 10.0, 5000.0))
        env = str(data.get("envelope", "adsr-gentle"))
        if env not in _ENVELOPES:
            raise ValueError(
                f"invalid envelope: {env!r} (must be one of {_ENVELOPES})"
            )
        vol = _clamp(float(data.get("volume", 0.5)), 0.0, 1.0)
        return cls(frequency_hz=freq, duration_ms=dur, envelope=env, volume=vol)


def _envelope_at(
    sample_index: int,
    total_samples: int,
    envelope: str,
) -> float:
    """
    Return the envelope amplitude multiplier in [0, 1] for a given sample.

    Envelopes are expressed as proportions of the total sample window so
    short and long tones share the same perceptual shape.
    """
    if total_samples <= 1:
        return 1.0
    t = sample_index / (total_samples - 1)  # [0, 1]

    if envelope == "square":
        # Brick-wall gate — full amplitude the whole way, click at the ends.
        return 1.0

    if envelope == "linear":
        # Triangle window: 0 → 1 → 0 across the tone.
        return 1.0 - abs(2.0 * t - 1.0)

    if envelope == "adsr-sharp":
        # 2% attack, 8% decay to 0.7 sustain, 20% release.
        attack_end = 0.02
        decay_end = 0.10
        release_start = 0.80
        sustain_level = 0.7
    else:  # adsr-gentle (default)
        # 10% attack, 15% decay to 0.8 sustain, 25% release.
        attack_end = 0.10
        decay_end = 0.25
        release_start = 0.75
        sustain_level = 0.8

    if t < attack_end:
        return t / attack_end
    if t < decay_end:
        span = decay_end - attack_end
        progress = (t - attack_end) / span
        return 1.0 - progress * (1.0 - sustain_level)
    if t < release_start:
        return sustain_level
    # Release: sustain_level → 0 over remaining window.
    span = 1.0 - release_start
    progress = (t - release_start) / span
    return sustain_level * (1.0 - progress)


class ToneBeepRenderer:
    """Stdlib tone synthesizer — 16-bit PCM WAV."""

    template = "tone-beep"
    version = "1"
    content_type = "audio/wav"
    extension = "wav"

    def render(self, data: dict[str, Any]) -> bytes:
        params = ToneBeepData.from_dict(data)

        total_samples = int(_SAMPLE_RATE_HZ * params.duration_ms / 1000)
        # Guard against pathological inputs. Minimum 1 sample so wave.open is happy.
        total_samples = max(total_samples, 1)

        angular_step = 2.0 * math.pi * params.frequency_hz / _SAMPLE_RATE_HZ
        peak = _MAX_AMPLITUDE * params.volume

        # Pre-build the int16 sample buffer with struct.pack for deterministic bytes.
        frames = bytearray(total_samples * _SAMPLE_WIDTH_BYTES)
        for i in range(total_samples):
            envelope_gain = _envelope_at(i, total_samples, params.envelope)
            sample_value = peak * envelope_gain * math.sin(angular_step * i)
            # Round-half-to-even for determinism across platforms (Python's default).
            int_sample = int(round(sample_value))
            # Clamp to int16 range in case of any float edge case.
            if int_sample > _MAX_AMPLITUDE:
                int_sample = _MAX_AMPLITUDE
            elif int_sample < -_MAX_AMPLITUDE - 1:
                int_sample = -_MAX_AMPLITUDE - 1
            struct.pack_into("<h", frames, i * _SAMPLE_WIDTH_BYTES, int_sample)

        out = io.BytesIO()
        with wave.open(out, "wb") as wav:
            wav.setnchannels(_CHANNELS)
            wav.setsampwidth(_SAMPLE_WIDTH_BYTES)
            wav.setframerate(_SAMPLE_RATE_HZ)
            wav.writeframes(bytes(frames))
        return out.getvalue()
