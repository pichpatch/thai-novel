"""
Stitch per-sentence WAVs into one block-level WAV with mood-aware pauses
and loudness normalization.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import soundfile as sf


SAMPLE_RATE = 22050


def _silence(ms: int) -> np.ndarray:
    return np.zeros(int(SAMPLE_RATE * ms / 1000), dtype=np.float32)


def _hann_taper(audio: np.ndarray, ms: float = 5.0) -> np.ndarray:
    """Apply a tiny Hann-window taper to both ends to kill edge clicks."""
    n = int(SAMPLE_RATE * ms / 1000)
    if len(audio) < 2 * n or n <= 0:
        return audio
    window = np.hanning(2 * n).astype(np.float32)
    audio = audio.copy()
    audio[:n] *= window[:n]
    audio[-n:] *= window[n:]
    return audio


def _loudness_normalize(audio: np.ndarray, target_lufs: float = -19.0) -> np.ndarray:
    """
    Normalize to ~target LUFS (speech-friendly). Uses pyloudnorm if installed,
    otherwise falls back to a peak-target normalization at -3 dBFS.
    """
    try:
        import pyloudnorm as pyln

        meter = pyln.Meter(SAMPLE_RATE)
        current = meter.integrated_loudness(audio)
        if not np.isfinite(current):
            raise ValueError("non-finite loudness")
        return pyln.normalize.loudness(audio, current, target_lufs).astype(np.float32)
    except Exception:
        # Fallback: peak normalize to -3 dBFS, leaves enough headroom for mixing.
        peak = float(np.max(np.abs(audio))) or 1.0
        target_peak = 10 ** (-3.0 / 20.0)
        return (audio * (target_peak / peak)).astype(np.float32)


def stitch_block(
    sentence_wavs: list[Path],
    sentence_pause_ms: int,
    out_path: Path,
    leading_silence_ms: int = 200,
    trailing_silence_ms: int = 600,
) -> float:
    """
    Concatenate sentence WAVs into one block WAV. Returns duration in seconds.
    """
    parts: list[np.ndarray] = [_silence(leading_silence_ms)]
    for i, wav_path in enumerate(sentence_wavs):
        audio, sr = sf.read(str(wav_path), dtype="float32", always_2d=False)
        if sr != SAMPLE_RATE:
            raise ValueError(f"{wav_path} is {sr} Hz; expected {SAMPLE_RATE}")
        audio = _hann_taper(audio)
        parts.append(audio)
        if i < len(sentence_wavs) - 1:
            parts.append(_silence(sentence_pause_ms))
    parts.append(_silence(trailing_silence_ms))

    full = np.concatenate(parts)
    full = _loudness_normalize(full)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(out_path), full, SAMPLE_RATE)
    return len(full) / SAMPLE_RATE


def concat_wavs(wavs: list[Path], out_path: Path) -> float:
    """
    Concat a list of WAVs end-to-end (no extra silence). Used to stitch
    block-level WAVs into the final episode-level narration track.
    """
    parts: list[np.ndarray] = []
    for w in wavs:
        audio, sr = sf.read(str(w), dtype="float32", always_2d=False)
        if sr != SAMPLE_RATE:
            raise ValueError(f"{w} is {sr} Hz; expected {SAMPLE_RATE}")
        parts.append(audio)
    full = np.concatenate(parts) if parts else np.zeros(0, dtype=np.float32)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(out_path), full, SAMPLE_RATE)
    return len(full) / SAMPLE_RATE
