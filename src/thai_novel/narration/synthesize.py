"""
edge-tts synthesizer with content-addressable caching and 3-parallel cap.

The narration cache lives at ./cache/narration/<key>.wav  where key =
sha256(text + voice + rate + pitch). Identical inputs hit instantly.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

import edge_tts

from ..hashing import narration_key

log = logging.getLogger("thai_novel.narration")

# Per-spec: max 3 concurrent network requests. Edge-tts will rate-limit you
# above about 5; 3 is comfortable and matches our project-wide stage cap.
MAX_CONCURRENT = 3


async def _run_ffmpeg(args: list[str]) -> tuple[int, bytes]:
    """Run ffmpeg with arguments as a list (no shell, no injection)."""
    proc = await asyncio.create_subprocess_exec(
        "ffmpeg", *args,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()
    return proc.returncode or 0, stderr


async def synthesize_sentence(
    text: str,
    voice: str,
    rate: str,
    pitch: str,
    cache_dir: Path,
    sem: asyncio.Semaphore,
) -> Path:
    """
    Synthesize one sentence; returns the path to a .wav. Caches by content hash.

    edge-tts writes mp3; we transcode to wav so the rest of the pipeline can
    treat narration as 22050 Hz mono PCM.
    """
    key = narration_key(text, voice, rate, pitch)
    out_wav = cache_dir / f"{key}.wav"
    if out_wav.exists():
        return out_wav

    cache_dir.mkdir(parents=True, exist_ok=True)

    async with sem:
        # 1. edge-tts -> mp3
        tmp_mp3 = cache_dir / f"{key}.partial.mp3"
        try:
            communicate = edge_tts.Communicate(text=text, voice=voice, rate=rate, pitch=pitch)
            await communicate.save(str(tmp_mp3))
        except Exception as e:
            tmp_mp3.unlink(missing_ok=True)
            raise RuntimeError(f"edge-tts failed for {key[:8]}...: {e}") from e

        # 2. mp3 -> wav (22050 Hz mono, matches Piper sample rate so we can mix freely)
        tmp_wav = cache_dir / f"{key}.partial.wav"
        rc, stderr = await _run_ffmpeg([
            "-y", "-hide_banner", "-loglevel", "error",
            "-i", str(tmp_mp3),
            "-ar", "22050", "-ac", "1",
            str(tmp_wav),
        ])
        if rc != 0:
            tmp_mp3.unlink(missing_ok=True)
            tmp_wav.unlink(missing_ok=True)
            raise RuntimeError(f"ffmpeg mp3->wav failed: {stderr.decode().strip()}")

        tmp_mp3.unlink(missing_ok=True)
        # Atomic rename so a crashed run can't leave a half-written cache entry.
        tmp_wav.replace(out_wav)

    return out_wav


async def synthesize_many(
    sentences: list[tuple[str, str, str, str]],  # (text, voice, rate, pitch)
    cache_dir: Path,
    on_progress=None,
) -> list[Path]:
    """Synthesize many sentences in parallel (capped at MAX_CONCURRENT)."""
    sem = asyncio.Semaphore(MAX_CONCURRENT)
    done = 0
    total = len(sentences)

    async def _one(idx: int, payload: tuple[str, str, str, str]) -> tuple[int, Path]:
        nonlocal done
        text, voice, rate, pitch = payload
        path = await synthesize_sentence(text, voice, rate, pitch, cache_dir, sem)
        done += 1
        if on_progress:
            on_progress(done, total)
        return idx, path

    results = await asyncio.gather(*[_one(i, p) for i, p in enumerate(sentences)])
    results.sort(key=lambda x: x[0])
    return [p for _, p in results]
