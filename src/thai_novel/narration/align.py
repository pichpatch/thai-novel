"""
Subtitle timing.

Two strategies, picked at runtime:
  1. Whisper-MLX forced alignment (best — runs on Neural Engine)
  2. Even-distribution fallback (no extra deps, lower quality)

Both produce a list of (start_sec, end_sec, text) tuples for subtitle cues.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import soundfile as sf

log = logging.getLogger("thai_novel.narration.align")


@dataclass
class SubtitleCue:
    start_sec: float
    end_sec: float
    text: str
    words: list[dict] | None = None  # [{"word": "...", "start_sec": ..., "end_sec": ...}]


def even_distribute(
    wav_path: Path,
    sentences: list[str],
    leading_silence_sec: float = 0.2,
    trailing_silence_sec: float = 0.6,
    sentence_pause_sec: float = 0.3,
) -> list[SubtitleCue]:
    """
    Cheap fallback: distribute total duration across sentences by character count.
    Good enough for first-render preview; replace with whisper alignment for final.
    """
    audio, sr = sf.read(str(wav_path), dtype="float32", always_2d=False)
    total = len(audio) / sr
    speech_time = max(0.0, total - leading_silence_sec - trailing_silence_sec -
                      sentence_pause_sec * max(0, len(sentences) - 1))
    total_chars = sum(len(s) for s in sentences) or 1

    cues: list[SubtitleCue] = []
    t = leading_silence_sec
    for i, s in enumerate(sentences):
        dur = speech_time * (len(s) / total_chars)
        cues.append(SubtitleCue(start_sec=t, end_sec=t + dur, text=s))
        t += dur
        if i < len(sentences) - 1:
            t += sentence_pause_sec
    return cues


def whisper_align(wav_path: Path, sentences: list[str], language: str = "th") -> list[SubtitleCue] | None:
    """
    Forced alignment via mlx-whisper. Returns None if mlx-whisper isn't
    installed (caller should fall back to even_distribute).
    """
    try:
        import mlx_whisper  # type: ignore
    except ImportError:
        return None

    try:
        result = mlx_whisper.transcribe(
            str(wav_path),
            path_or_hf_repo="mlx-community/whisper-tiny-mlx",
            language=language,
            word_timestamps=True,
            verbose=False,
        )
    except Exception as e:
        log.warning(f"whisper alignment failed, falling back: {e}")
        return None

    cues: list[SubtitleCue] = []
    for seg in result.get("segments", []):
        words = [
            {"word": w["word"], "start_sec": float(w["start"]), "end_sec": float(w["end"])}
            for w in seg.get("words", [])
        ]
        cues.append(SubtitleCue(
            start_sec=float(seg["start"]),
            end_sec=float(seg["end"]),
            text=seg["text"].strip(),
            words=words,
        ))
    return cues or None


def align_block(wav_path: Path, sentences: list[str], language: str = "th") -> list[SubtitleCue]:
    """Try whisper; fall back to even distribution."""
    aligned = whisper_align(wav_path, sentences, language=language)
    if aligned:
        return aligned
    return even_distribute(wav_path, sentences)
