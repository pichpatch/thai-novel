"""FFmpeg-based video assembly.

Two stages:

  1. For each scene, build a per-scene MP4: still image displayed for the
     length of the scene's narration WAV, with the narration as audio.
  2. Concatenate all scenes plus an optional intro, then mix a looping
     background music track underneath (ducked to ~15% so voice stays clear).

We shell out to the system `ffmpeg` directly so we don't take a Python
binding dependency (and so the user can debug the exact ffmpeg invocations).
"""
from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path

log = logging.getLogger(__name__)

VIDEO_W = 1280
VIDEO_H = 720
VIDEO_FPS = 30
BGM_VOLUME = 0.15  # 15% of music under voice


def _run(cmd: list[str]) -> None:
    log.debug("ffmpeg: %s", " ".join(cmd))
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        log.error("ffmpeg stderr:\n%s", p.stderr[-3000:])
        raise RuntimeError(f"ffmpeg failed (exit {p.returncode})")


def probe_duration(path: Path) -> float:
    """Return media duration in seconds."""
    out = subprocess.check_output(
        [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        text=True,
    )
    return float(out.strip())


def make_scene_clip(image_path: Path, audio_path: Path, out_path: Path) -> Path:
    """Produce a still-image clip the length of the audio.

    The image is letterboxed to VIDEO_WxVIDEO_H so videos with mixed image
    aspect ratios still concat cleanly.
    """
    out_path.parent.mkdir(parents=True, exist_ok=True)
    vf = (
        f"scale={VIDEO_W}:{VIDEO_H}:force_original_aspect_ratio=decrease,"
        f"pad={VIDEO_W}:{VIDEO_H}:(ow-iw)/2:(oh-ih)/2:color=black,"
        f"format=yuv420p,fps={VIDEO_FPS}"
    )
    _run([
        "ffmpeg", "-y",
        "-loop", "1", "-i", str(image_path),
        "-i", str(audio_path),
        "-vf", vf,
        "-c:v", "libx264", "-tune", "stillimage", "-preset", "medium", "-crf", "20",
        "-c:a", "aac", "-b:a", "192k", "-ar", "44100",
        "-shortest",
        "-movflags", "+faststart",
        str(out_path),
    ])
    return out_path


def concat_clips(clip_paths: list[Path], out_path: Path) -> Path:
    """Concat MP4 clips losslessly via the concat demuxer."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    list_file = out_path.with_suffix(".concat.txt")
    list_file.write_text(
        "\n".join(f"file '{p.resolve()}'" for p in clip_paths) + "\n",
        encoding="utf-8",
    )
    _run([
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0", "-i", str(list_file),
        "-c", "copy",
        "-movflags", "+faststart",
        str(out_path),
    ])
    list_file.unlink(missing_ok=True)
    return out_path


def mix_bgm(video_in: Path, music_path: Path, out_path: Path) -> Path:
    """Loop `music_path` underneath the video's audio at BGM_VOLUME.

    Output duration matches the input video.
    """
    out_path.parent.mkdir(parents=True, exist_ok=True)
    _run([
        "ffmpeg", "-y",
        "-i", str(video_in),
        "-stream_loop", "-1", "-i", str(music_path),
        "-filter_complex",
        f"[1:a]volume={BGM_VOLUME}[bgm];"
        f"[0:a][bgm]amix=inputs=2:duration=first:dropout_transition=0[a]",
        "-map", "0:v",
        "-map", "[a]",
        "-c:v", "copy",
        "-c:a", "aac", "-b:a", "192k",
        "-movflags", "+faststart",
        str(out_path),
    ])
    return out_path


def ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None
