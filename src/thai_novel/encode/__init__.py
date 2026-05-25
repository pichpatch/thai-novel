"""
Phase E: final mux.

Takes the Remotion render (video + narration baked in) and adds:
  - music bed track (sidechain-ducked under narration)
  - ambience track (under everything)
  - loudness normalization to -14 LUFS (YouTube standard)
  - SRT + chapter_markers exports

Output: novels/<id>/output/final.mp4 + subtitles.srt + chapter_markers.txt
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from ..images.library import resolve as resolve_lib

log = logging.getLogger("thai_novel.encode")


async def _run_ff(args: list[str]) -> tuple[int, bytes]:
    create = asyncio.create_subprocess_exec  # bound name
    proc = await create(
        "ffmpeg", *args,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.PIPE,
    )
    _, err = await proc.communicate()
    return proc.returncode or 0, err


def _format_srt_time(t: float) -> str:
    h = int(t // 3600)
    m = int((t % 3600) // 60)
    s = int(t % 60)
    ms = int((t - int(t)) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def write_srt(timeline: dict, project_root: Path, out_path: Path) -> Path:
    """SRT from per-block cues (absolute timestamps)."""
    lines: list[str] = []
    idx = 1
    for ch in timeline["chapters"]:
        for b in ch["blocks"]:
            base = float(b["start_sec"])
            for cue in b["subtitles"]:
                start = base + float(cue["start_sec"])
                end = base + float(cue["end_sec"])
                lines.append(str(idx))
                lines.append(f"{_format_srt_time(start)} --> {_format_srt_time(end)}")
                lines.append(cue["text"].strip())
                lines.append("")
                idx += 1
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines), encoding="utf-8")
    return out_path


def write_chapter_markers(timeline: dict, out_path: Path) -> Path:
    """YouTube chapter markers: HH:MM:SS Title, one per line."""
    lines: list[str] = []
    if timeline.get("intro") and timeline["intro"]["show"]:
        lines.append("00:00 Intro")
    for ch in timeline["chapters"]:
        t = float(ch["start_sec"])
        h = int(t // 3600); m = int((t % 3600) // 60); s = int(t % 60)
        stamp = f"{h:02d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"
        lines.append(f"{stamp} {ch['title']}")
    if timeline.get("end_card") and timeline["end_card"]["show"]:
        t = float(timeline["end_card"]["start_sec"])
        h = int(t // 3600); m = int((t % 3600) // 60); s = int(t % 60)
        stamp = f"{h:02d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"
        lines.append(f"{stamp} Outro")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines), encoding="utf-8")
    return out_path


async def finalize(
    remotion_mp4: Path,
    timeline: dict,
    project_root: Path,
    out_dir: Path,
) -> dict:
    """
    Mux: video (from remotion_mp4) + music_bed (looped) + ambience (looped) + loudnorm.

    Returns: {"mp4": Path, "srt": Path, "chapters_txt": Path}
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    final_mp4 = out_dir / "final.mp4"

    mb = timeline["audio_config"]["music_bed"]
    amb = timeline["audio_config"]["ambience"]
    library_root = project_root / "library"

    music_path = None
    if mb.get("default"):
        music_path = resolve_lib(mb["default"], library_root)
    if music_path is None and mb.get("by_mood"):
        for ref in mb["by_mood"].values():
            music_path = resolve_lib(ref, library_root)
            if music_path:
                break

    ambience_path = None
    if amb.get("default"):
        ambience_path = resolve_lib(amb["default"], library_root)

    duration = float(timeline["total_duration_sec"])

    args = ["-y", "-hide_banner", "-loglevel", "warning"]
    args += ["-i", str(remotion_mp4)]

    filter_lines: list[str] = []
    audio_inputs = ["[0:a]"]
    next_idx = 1

    if music_path:
        args += ["-stream_loop", "-1", "-t", f"{duration:.3f}", "-i", str(music_path)]
        filter_lines.append(
            f"[{next_idx}:a]volume={mb['volume_db']}dB,aresample=22050[mraw]"
        )
        filter_lines.append(
            f"[mraw][0:a]sidechaincompress=threshold=0.05:ratio=8:attack=10:release=400[mducked]"
        )
        audio_inputs.append("[mducked]")
        next_idx += 1

    if ambience_path:
        args += ["-stream_loop", "-1", "-t", f"{duration:.3f}", "-i", str(ambience_path)]
        filter_lines.append(
            f"[{next_idx}:a]volume={amb['volume_db']}dB,aresample=22050[amb]"
        )
        audio_inputs.append("[amb]")
        next_idx += 1

    mix_inputs = "".join(audio_inputs)
    filter_lines.append(
        f"{mix_inputs}amix=inputs={len(audio_inputs)}:duration=longest:normalize=0[mixed]"
    )
    filter_lines.append(
        "[mixed]loudnorm=I=-14:LRA=11:TP=-1.5[aout]"
    )
    args += ["-filter_complex", ";".join(filter_lines)]

    # ── Size-optimized encode ────────────────────────────────────────────────
    # Goal: ~7 MB / minute of video (~900 kbps total).
    # Our content is mostly slow-motion stills, so libx264 with tune=stillimage
    # at CRF 28 yields ~600–800 kbps natively and looks great. We use libx264
    # (not VideoToolbox) because VT can't hit these low bitrates cleanly and
    # the visible quality at CRF 28 stillimage is materially better.
    args += [
        "-map", "0:v:0", "-map", "[aout]",
        "-c:v", "libx264",
        "-preset", "slow",
        "-crf", "28",
        "-tune", "stillimage",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "96k", "-ar", "44100", "-ac", "2",
        "-movflags", "+faststart",
        "-shortest",
        str(final_mp4),
    ]

    log.info("muxing -> final.mp4 (libx264 crf28 tune=stillimage, target ~7 MB/min)")
    rc, stderr = await _run_ff(args)
    if rc != 0:
        raise RuntimeError(
            f"ffmpeg mux failed (rc={rc}):\n{stderr.decode(errors='replace')[-2000:]}"
        )

    srt_path = out_dir / "subtitles.srt"
    chap_path = out_dir / "chapter_markers.txt"
    write_srt(timeline, project_root, srt_path)
    write_chapter_markers(timeline, chap_path)

    return {"mp4": final_mp4, "srt": srt_path, "chapters_txt": chap_path}


__all__ = ["finalize", "write_srt", "write_chapter_markers"]
