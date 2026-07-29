"""
Phase D (rewritten, pure-ffmpeg).

Replaces the Remotion-based renderer. Walks the compiled timeline.json,
pre-renders text/logo cards via PIL, builds one short MP4 per segment via
ffmpeg, then concatenates them into a single raw video (video + narration
audio baked in) ready for Stage 5 mux.

No Chrome. No JavaScript runtime. No webpack. ~30–90s for a 9-minute episode.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from pathlib import Path

from ..channel import CHANNEL_NAME
from . import cards
from .cards import (
    cached_card,
    find_font,
    render_chapter_card,
    render_end_card,
    render_episode_title,
    render_logo_splash,
)
from ..hashing import canon_hash
from ..images.library import resolve as resolve_lib

log = logging.getLogger("thai_novel.compose")

# Concurrency cap for parallel ffmpeg invocations.
# Each one is ~1 thread of libx264 + decode; M2 Pro 32 GB handles 4 cleanly.
MAX_PARALLEL_SEGMENTS = 4

# Standard segment audio format. Matches what narration WAVs are produced at.
SEG_SAMPLE_RATE = 22050
SEG_AUDIO_CHANNELS = 1


# ─────────────────────────────────────────────────────────────────────────────
# Subprocess helpers
# ─────────────────────────────────────────────────────────────────────────────


async def _ffmpeg(args: list[str]) -> tuple[int, bytes]:
    create = asyncio.create_subprocess_exec  # bound name
    proc = await create(
        "ffmpeg", *args,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.PIPE,
    )
    _, err = await proc.communicate()
    return proc.returncode or 0, err


# ─────────────────────────────────────────────────────────────────────────────
# Segment building
# ─────────────────────────────────────────────────────────────────────────────


async def _build_segment(
    *,
    image_path: Path,
    audio_path: Path | None,
    duration_sec: float,
    width: int,
    height: int,
    fps: int,
    out_path: Path,
    sem: asyncio.Semaphore,
    color_grade_eq: str | None = None,
) -> Path:
    """
    Build a single segment mp4 from a still image + optional audio.

    If audio_path is None, generates silent audio of the right length so
    every segment has matching audio properties (concat -c copy needs uniform
    streams).

    Cache: out_path is content-addressed by the caller (filename includes
    sha256 of image+audio paths+duration+size+fps+grade), so if any input
    changes — say you re-render the logo card and its filename changes —
    a new segment file is built and the old one is left behind (./clean
    sweeps it up).
    """
    if out_path.exists():
        return out_path  # cache hit
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # Video filter: scale image to project size, preserving aspect ratio with
    # black-bar padding if needed. setsar=1 keeps players happy.
    vf_parts = [
        f"scale={width}:{height}:force_original_aspect_ratio=decrease",
        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=black",
        "setsar=1",
    ]
    if color_grade_eq:
        vf_parts.append(color_grade_eq)
    vf = ",".join(vf_parts)

    args: list[str] = ["-y", "-hide_banner", "-loglevel", "error"]
    # Video input: loop the still image at the target fps for the target duration.
    args += [
        "-loop", "1",
        "-framerate", str(fps),
        "-t", f"{duration_sec:.4f}",
        "-i", str(image_path),
    ]
    # Audio input: real wav, or generated silence.
    if audio_path is not None:
        args += ["-i", str(audio_path)]
    else:
        args += [
            "-f", "lavfi",
            "-t", f"{duration_sec:.4f}",
            "-i", f"anullsrc=channel_layout=mono:sample_rate={SEG_SAMPLE_RATE}",
        ]

    args += [
        "-vf", vf,
        "-c:v", "libx264",
        "-tune", "stillimage",
        "-crf", "28",
        "-preset", "fast",
        "-pix_fmt", "yuv420p",
        "-r", str(fps),
        # Uniform audio across segments so `-c copy` concat works.
        "-c:a", "aac",
        "-b:a", "128k",
        "-ar", "44100",
        "-ac", "2",
        # Stop when the shorter stream ends; with -t on both, they're equal.
        "-shortest",
        str(out_path),
    ]

    async with sem:
        rc, stderr = await _ffmpeg(args)

    if rc != 0:
        raise RuntimeError(
            f"ffmpeg segment build failed for {out_path.name}:\n"
            f"{stderr.decode(errors='replace')[-1500:]}"
        )
    return out_path


def _eq_for_grade(grade: str | None) -> str | None:
    """Translate our color_grade tokens into a one-liner ffmpeg eq= filter."""
    if not grade or grade == "neutral":
        return None
    return {
        "warm_cozy":       "eq=saturation=1.05:brightness=0.02:contrast=0.97,colorbalance=rs=0.08:gs=0.02:bs=-0.05",
        "cool_night":      "eq=saturation=0.9:brightness=-0.08:contrast=1.05,colorbalance=rs=-0.05:bs=0.08",
        "golden_hour":     "eq=saturation=1.15:brightness=0.05:contrast=1.02,colorbalance=rs=0.10:gs=0.04:bs=-0.06",
        "melancholy_blue": "eq=saturation=0.7:brightness=-0.05,colorbalance=rs=-0.06:bs=0.10",
        "playful_pop":     "eq=saturation=1.2:brightness=0.05:contrast=1.05",
    }.get(grade)


# ─────────────────────────────────────────────────────────────────────────────
# Concat
# ─────────────────────────────────────────────────────────────────────────────


async def _concat_segments(segment_paths: list[Path], out_path: Path) -> Path:
    """Stream-copy concat (no re-encoding — instant)."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    list_file = out_path.parent / f"{out_path.stem}.concat.txt"
    # ffmpeg concat list: one `file '<path>'` per segment, paths escaped.
    list_file.write_text(
        "\n".join(f"file '{p.resolve()}'" for p in segment_paths) + "\n",
        encoding="utf-8",
    )
    args = [
        "-y", "-hide_banner", "-loglevel", "error",
        "-f", "concat", "-safe", "0",
        "-i", str(list_file),
        "-c", "copy",
        "-movflags", "+faststart",
        str(out_path),
    ]
    rc, stderr = await _ffmpeg(args)
    list_file.unlink(missing_ok=True)
    if rc != 0:
        raise RuntimeError(f"concat failed:\n{stderr.decode(errors='replace')[-1500:]}")
    return out_path


# ─────────────────────────────────────────────────────────────────────────────
# Public entry point
# ─────────────────────────────────────────────────────────────────────────────


async def compose_video(
    timeline_path: Path,
    out_path: Path,
    project_root: Path,
) -> Path:
    """
    Build raw.mp4 from the compiled timeline.json. Replaces Remotion render.

    Returns the path to raw.mp4 (video + narration audio baked in, no music yet).
    Stage 5 (encode/finalize.py) takes it from here.
    """
    timeline = json.loads(timeline_path.read_text(encoding="utf-8"))

    episode_id = timeline["episode_id"]
    width = int(timeline["width"])
    height = int(timeline["height"])
    fps = int(timeline["fps"])
    channel_name = CHANNEL_NAME

    work_dir = project_root / "cache" / episode_id / "segments"
    cards_dir = project_root / "cache" / episode_id / "cards"
    work_dir.mkdir(parents=True, exist_ok=True)
    cards_dir.mkdir(parents=True, exist_ok=True)

    library_root = project_root / "library"
    font_path = find_font(library_root)
    log.info(f"using font: {font_path}")

    # ── Pre-render cards (PIL, ~1s total) ───────────────────────────────────
    intro = timeline.get("intro")
    logo_card_path: Path | None = None
    title_card_path: Path | None = None

    if intro and intro.get("show"):
        logo_ref = intro.get("logo_ref")
        logo_file = (
            resolve_lib(logo_ref, library_root) if logo_ref else None
        )
        # Welcome: full-screen logo
        logo_card_path = cached_card(
            kind="logo_splash",
            inputs={
                "logo": str(logo_file) if logo_file else None,
                "channel": channel_name,
                "w": width, "h": height,
            },
            cache_dir=cards_dir,
            renderer=render_logo_splash,
            logo_path=logo_file, channel_name=channel_name, width=width, height=height,
        )
        # Episode title
        title_card_path = cached_card(
            kind="episode_title",
            inputs={
                "text": intro["title_text"],
                "logo": str(logo_file) if logo_file else None,
                "w": width, "h": height, "font": font_path,
            },
            cache_dir=cards_dir,
            renderer=render_episode_title,
            title_text=intro["title_text"],
            logo_path=logo_file,
            width=width, height=height, font_path=font_path,
        )

    # Chapter cards
    chapter_card_paths: list[Path | None] = []
    total_ch = len(timeline["chapters"])
    for i, ch in enumerate(timeline["chapters"]):
        if not ch.get("show_title_card"):
            chapter_card_paths.append(None)
            continue
        cp = cached_card(
            kind=f"chapter_{ch['id']}",
            inputs={
                "title": ch["title"], "idx": i + 1, "total": total_ch,
                "w": width, "h": height, "font": font_path,
            },
            cache_dir=cards_dir,
            renderer=render_chapter_card,
            title=ch["title"], chapter_index=i + 1, total_chapters=total_ch,
            width=width, height=height, font_path=font_path,
        )
        chapter_card_paths.append(cp)

    # End card
    end_card_path: Path | None = None
    end = timeline.get("end_card")
    if end and end.get("show"):
        end_card_path = cached_card(
            kind="end_card",
            inputs={
                "msg": end.get("message"),
                "next": end.get("next_episode_title"),
                "channel": channel_name,
                "w": width, "h": height, "font": font_path,
            },
            cache_dir=cards_dir,
            renderer=render_end_card,
            message=end.get("message"),
            next_episode_title=end.get("next_episode_title"),
            channel_name=channel_name,
            width=width, height=height, font_path=font_path,
        )

    # ── Plan all segments in order ─────────────────────────────────────────
    @dataclass_lite
    class Seg:
        name: str
        image: Path
        audio: Path | None
        duration: float
        color_grade: str | None = None

    segs: list[Seg] = []

    if intro and intro.get("show"):
        assert logo_card_path and title_card_path
        segs.append(Seg(
            name="00_intro_welcome",
            image=logo_card_path,
            audio=project_root / intro["welcome_audio_path"],
            duration=float(intro["welcome_duration_sec"]),
        ))
        segs.append(Seg(
            name="01_intro_title",
            image=title_card_path,
            audio=project_root / intro["title_audio_path"],
            duration=float(intro["title_duration_sec"]),
        ))

    for i, ch in enumerate(timeline["chapters"]):
        seg_no = i * 10 + 10  # 10, 20, 30, ...  leaves room for sub-segments
        if ch.get("show_title_card") and chapter_card_paths[i]:
            segs.append(Seg(
                name=f"{seg_no:02d}_{ch['id']}_card",
                image=chapter_card_paths[i],
                audio=None,
                duration=float(ch["title_card_duration_sec"]),
            ))
        for j, b in enumerate(ch["blocks"]):
            segs.append(Seg(
                name=f"{seg_no:02d}_{ch['id']}_b{j+1}",
                image=project_root / b["image_path"],
                audio=project_root / b["audio_path"],
                duration=float(b["duration_sec"]),
                color_grade=b.get("color_grade"),
            ))

    if end_card_path and end:
        segs.append(Seg(
            name="99_end_card",
            image=end_card_path,
            audio=None,
            duration=float(end["duration_sec"]),
        ))

    # ── Build segments in parallel ──────────────────────────────────────────
    # Content-address the segment filename: if the source image or audio
    # changes (e.g. you re-render the logo card or edit a narration block),
    # the resulting filename changes and a new segment file is built. Old
    # ones linger until ./clean sweeps them.
    sem = asyncio.Semaphore(MAX_PARALLEL_SEGMENTS)
    log.info(f"building {len(segs)} segments (concurrency={MAX_PARALLEL_SEGMENTS})...")

    def _seg_filename(s: "Seg") -> str:
        key = canon_hash({
            "image": s.image.name,
            "audio": s.audio.name if s.audio else None,
            "duration": round(s.duration, 4),
            "w": width, "h": height, "fps": fps,
            "grade": s.color_grade,
        })
        return f"{s.name}_{key}.mp4"

    tasks = [
        _build_segment(
            image_path=s.image,
            audio_path=s.audio,
            duration_sec=s.duration,
            width=width, height=height, fps=fps,
            out_path=work_dir / _seg_filename(s),
            sem=sem,
            color_grade_eq=_eq_for_grade(s.color_grade),
        )
        for s in segs
    ]
    segment_paths = await asyncio.gather(*tasks)

    # ── Concat into raw.mp4 ─────────────────────────────────────────────────
    log.info(f"concatenating {len(segment_paths)} segments -> {out_path.name}")
    return await _concat_segments(segment_paths, out_path)


# ─────────────────────────────────────────────────────────────────────────────
# Tiny dataclass shim (avoids an extra import for one use site)
# ─────────────────────────────────────────────────────────────────────────────

def dataclass_lite(cls):
    """Like @dataclass but without the import. We only need __init__."""
    from dataclasses import dataclass
    return dataclass(cls)


__all__ = ["compose_video"]
