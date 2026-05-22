"""Orchestrator: input JSON → out/<title>.mp4.

Usage:
    python pipeline.py path/to/input.json [--out-dir out] [--no-intro] [--no-bgm]

Flow:
    1. Validate input
    2. For each scene: TTS narration → WAV
    3. For each scene: image gen via lib/text2image/ → PNG
    4. For each scene: build a still-image MP4 the length of its narration
    5. Build (or reuse) intro MP4
    6. Concat intro + scene MP4s → narrated.mp4
    7. Pick a random track from music/ → mix under narrated.mp4 → out/<title>.mp4
"""
from __future__ import annotations

import argparse
import json
import logging
import random
import re
import sys
from pathlib import Path

import image_gen
from intro import ensure_intro
from tts import ThaiTTS
from video import (
    concat_clips,
    ffmpeg_available,
    make_scene_clip,
    mix_bgm,
)

log = logging.getLogger("pipeline")

HERE = Path(__file__).resolve().parent


def _slug(s: str) -> str:
    s = s.strip()
    s = re.sub(r"\s+", "-", s)
    s = re.sub(r"[^\w\-ก-๙]+", "", s, flags=re.UNICODE)
    return s[:80] or "episode"


def _load_input(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if "scenes" not in data or not isinstance(data["scenes"], list) or not data["scenes"]:
        raise ValueError("Input JSON must contain a non-empty 'scenes' array.")
    for i, s in enumerate(data["scenes"]):
        if not isinstance(s, dict):
            raise ValueError(f"Scene #{i} is not an object.")
        if not s.get("narration"):
            raise ValueError(f"Scene #{i} missing 'narration'.")
        if not s.get("image_prompt"):
            raise ValueError(f"Scene #{i} missing 'image_prompt'.")
    data.setdefault("title", path.stem)
    data.setdefault("channel", "Untitled Channel")
    # Optional: how the channel name should be SPOKEN by TTS. Useful when the
    # written form is a stylised brand (e.g. "ThAI Novel") that the TTS would
    # otherwise mispronounce. Falls back to `channel` when not set.
    data.setdefault("channel_spoken", data["channel"])
    data.setdefault("engine", "vachana")  # PyThaiTTS pretrained: vachana | khanomtan | lunarlist_onnx
    data.setdefault("voice", "th_f_1")
    data.setdefault("language", "th")
    # Narration quality knobs (both optional, both default to legacy behaviour):
    data.setdefault("speed", 1.0)             # 1.0 = original; 0.9 = 10% slower; 1.1 = 10% faster
    data.setdefault("sentence_pause_ms", 100)   # 0 = single-shot; 200–400 sounds more natural
    return data


def _pick_music(music_dir: Path) -> Path | None:
    if not music_dir.exists():
        return None
    tracks = [
        p for p in music_dir.iterdir()
        if p.suffix.lower() in {".mp3", ".m4a", ".wav", ".flac", ".ogg"}
    ]
    if not tracks:
        return None
    pick = random.choice(tracks)
    log.info("Background music: %s", pick.name)
    return pick


def run(input_path: Path, out_dir: Path, use_intro: bool, use_bgm: bool) -> Path:
    if not ffmpeg_available():
        raise RuntimeError("ffmpeg/ffprobe not found on PATH. Install via Homebrew: brew install ffmpeg")

    data = _load_input(input_path)
    title = data["title"]
    channel = data["channel"]
    channel_spoken = data["channel_spoken"]
    engine = data["engine"]
    voice = data["voice"]
    speed = data["speed"]
    sentence_pause_ms = data["sentence_pause_ms"]
    slug = _slug(title)

    work = out_dir / "_work" / slug
    work.mkdir(parents=True, exist_ok=True)
    out_dir.mkdir(parents=True, exist_ok=True)

    tts = ThaiTTS(
        engine=engine,
        voice=voice,
        speed=speed,
        sentence_pause_ms=sentence_pause_ms,
    )

    # 1. TTS pass — fast, sequential. Each scene → scene_NNN.wav
    log.info("Stage 1/4: TTS for %d scenes ...", len(data["scenes"]))
    wavs: list[Path] = []
    for i, scene in enumerate(data["scenes"]):
        wav = work / f"scene_{i:03d}.wav"
        if not wav.exists():
            tts.synthesise(scene["narration"], wav)
        else:
            log.info("  scene %03d wav cached", i)
        wavs.append(wav)

    # 2. Image pass — slow, sequential (one warm in-process model).
    #    The model loads on the first generate() call (~40 s after weights are
    #    cached, much longer on the very first run while ~12 GB downloads).
    log.info("Stage 2/4: Images for %d scenes (this is the slow part) ...", len(data["scenes"]))
    pngs: list[Path] = []
    for i, scene in enumerate(data["scenes"]):
        png = work / f"scene_{i:03d}.png"
        if not png.exists():
            image_gen.generate(scene["image_prompt"], png)
        else:
            log.info("  scene %03d png cached", i)
        pngs.append(png)

    # 3. Per-scene clips → scene_NNN.mp4
    log.info("Stage 3/4: Building per-scene clips ...")
    clips: list[Path] = []
    for i, (png, wav) in enumerate(zip(pngs, wavs)):
        clip = work / f"scene_{i:03d}.mp4"
        if not clip.exists():
            make_scene_clip(png, wav, clip)
        clips.append(clip)

    # 4. Intro + concat
    log.info("Stage 4/4: Intro + concat + bgm mix ...")
    final_inputs = list(clips)
    if use_intro:
        intro_mp4 = ensure_intro(
            channel=channel,
            channel_spoken=channel_spoken,
            title=title,
            intro_dir=HERE / "intro",
            tts=tts,
        )
        final_inputs = [intro_mp4] + final_inputs

    narrated = work / "narrated.mp4"
    concat_clips(final_inputs, narrated)

    out_mp4 = out_dir / f"{slug}.mp4"
    if use_bgm:
        track = _pick_music(HERE / "music")
        if track is None:
            log.warning("No music in music/ — skipping bgm mix.")
            narrated.replace(out_mp4)
        else:
            mix_bgm(narrated, track, out_mp4)
    else:
        narrated.replace(out_mp4)

    log.info("Done → %s", out_mp4)
    return out_mp4


def _expand_inputs(paths: list[Path]) -> list[Path]:
    """Turn the raw argv list into a sorted, de-duped list of .json files.

    Rules:
      - A .json file is taken as-is.
      - A directory is expanded to *.json inside it (non-recursive).
      - Non-JSON files are skipped with a warning.
      - Missing paths raise.
    """
    out: list[Path] = []
    seen: set[Path] = set()
    for p in paths:
        if not p.exists():
            raise FileNotFoundError(p)
        candidates: list[Path]
        if p.is_dir():
            candidates = sorted(p.glob("*.json"))
            if not candidates:
                log.warning("No *.json files in directory: %s", p)
        elif p.suffix.lower() == ".json":
            candidates = [p]
        else:
            log.warning("Skipping non-JSON input: %s", p)
            continue
        for c in candidates:
            r = c.resolve()
            if r not in seen:
                seen.add(r)
                out.append(c)
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Render one or more Thai novel JSON files → MP4(s).",
        epilog=(
            "Examples:\n"
            "  ./make in/ep01.json\n"
            "  ./make in/ep01.json in/ep02.json in/ep03.json\n"
            "  ./make in/*.json            # shell glob — renders every JSON in in/\n"
            "  ./make in                   # directory — same as in/*.json\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument(
        "inputs", type=Path, nargs="+",
        help="One or more JSON files, or a directory of JSON files.",
    )
    ap.add_argument("--out-dir", type=Path, default=HERE / "out", help="Output directory")
    ap.add_argument("--no-intro", action="store_true", help="Skip the welcome intro card")
    ap.add_argument("--no-bgm", action="store_true", help="Skip background music")
    ap.add_argument("--stop-on-error", action="store_true",
                    help="Abort the batch on the first failure (default: keep going).")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s | %(message)s",
        datefmt="%H:%M:%S",
    )

    try:
        inputs = _expand_inputs(args.inputs)
    except FileNotFoundError as exc:
        log.error("Input does not exist: %s", exc)
        return 2
    if not inputs:
        log.error("No JSON inputs to render.")
        return 2

    log.info("Batch: %d input(s) to render.", len(inputs))
    succeeded: list[Path] = []
    failed: list[tuple[Path, str]] = []

    for i, inp in enumerate(inputs, 1):
        log.info("───── [%d/%d] %s ─────", i, len(inputs), inp)
        try:
            out_mp4 = run(inp, args.out_dir, use_intro=not args.no_intro, use_bgm=not args.no_bgm)
            succeeded.append(out_mp4)
        except Exception as exc:
            log.error("[%d/%d] failed: %s", i, len(inputs), exc)
            failed.append((inp, str(exc)))
            if args.stop_on_error:
                log.error("Aborting batch (--stop-on-error).")
                break
            if args.verbose:
                import traceback
                traceback.print_exc()

    log.info("═════ Batch summary ═════")
    log.info("  succeeded: %d", len(succeeded))
    for p in succeeded:
        log.info("    ✓ %s", p)
    if failed:
        log.info("  failed: %d", len(failed))
        for p, msg in failed:
            log.info("    ✗ %s — %s", p, msg)
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
