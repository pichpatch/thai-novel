"""Thin wrapper around PyThaiTTS, with two narration-quality upgrades:

  • Sentence-level chunking + inter-sentence silence
        Long paragraphs synthesised in one shot sound rushed and run-on. We
        split on Thai sentence boundaries, synthesise each chunk separately,
        and concat with a configurable silence (default 0 = legacy behaviour).

  • Speed control via ffmpeg `atempo`
        PyThaiTTS has no built-in speed knob. We post-process the WAV with
        `atempo` (pitch-preserving). Range 0.5-2.0 is the sweet spot;
        outside that we chain filters automatically.

Engines (set "engine" in input JSON):
    pretrained="vachana"        speakers: th_f_1 (default), th_m_1, th_f_2, th_m_2
    pretrained="khanomtan"      speaker: "Linda" (default), multilingual prosody
    pretrained="lunarlist_onnx" single voice, fastest
    pretrained="lunarlist"      requires `pip install nemo_toolkit[tts]`
"""
from __future__ import annotations

import logging
import re
import shutil
import subprocess
import tempfile
import wave
from pathlib import Path

log = logging.getLogger(__name__)

DEFAULT_ENGINE = "vachana"
DEFAULT_VOICE = "th_f_1"

# Sentence terminators we'll split on. ๆ (mai yamok) is NOT a sentence break —
# it's a repetition marker that should stay glued to its word.
_SENT_SPLIT_RE = re.compile(r"[.!?…。!?]+|\n{1,}")


def _split_sentences(text: str) -> list[str]:
    """Split narration on Thai/Western sentence terminators.

    Empty / whitespace-only chunks are dropped. If the input has no terminators
    we return it as a single chunk (so behaviour is identical to single-shot).
    """
    raw = _SENT_SPLIT_RE.split(text)
    return [s.strip() for s in raw if s and s.strip()]


def _wav_params(path: Path) -> wave._wave_params:
    with wave.open(str(path), "rb") as w:
        return w.getparams()


def _concat_wavs_with_silence(wav_paths: list[Path], silence_ms: int, out_path: Path) -> None:
    """Glue WAVs together, inserting silence between each pair.

    Pure stdlib — no ffmpeg dependency. Requires all inputs to share the
    same sample rate / channels / sample width (PyThaiTTS produces uniform
    output per engine, so this holds).
    """
    if not wav_paths:
        raise ValueError("concat: no input WAVs")
    params = _wav_params(wav_paths[0])
    silence_frames = int(params.framerate * silence_ms / 1000)
    silence_bytes = b"\x00" * (silence_frames * params.sampwidth * params.nchannels)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(out_path), "wb") as out:
        out.setparams(params)
        for i, p in enumerate(wav_paths):
            with wave.open(str(p), "rb") as w:
                out.writeframes(w.readframes(w.getnframes()))
            if silence_ms > 0 and i < len(wav_paths) - 1:
                out.writeframes(silence_bytes)


def _atempo_chain(speed: float) -> str:
    """ffmpeg atempo accepts 0.5–2.0. Chain filters for values outside that."""
    filters: list[str] = []
    remaining = speed
    while remaining < 0.5:
        filters.append("atempo=0.5")
        remaining /= 0.5
    while remaining > 2.0:
        filters.append("atempo=2.0")
        remaining /= 2.0
    filters.append(f"atempo={remaining:.4f}")
    return ",".join(filters)


def _apply_speed(in_wav: Path, speed: float, out_wav: Path) -> None:
    """Run the WAV through ffmpeg atempo. Preserves pitch."""
    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-i", str(in_wav),
        "-filter:a", _atempo_chain(speed),
        str(out_wav),
    ]
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        log.error("ffmpeg atempo failed: %s", p.stderr)
        raise RuntimeError("Speed adjustment failed")


class ThaiTTS:
    """PyThaiTTS wrapper with chunking + speed post-processing.

    Args:
        engine: PyThaiTTS pretrained name (default "vachana").
        voice:  Speaker idx (default "th_f_1"; valid for vachana only).
        speed:  Playback speed multiplier (1.0 = original; 0.9 = 10% slower).
        sentence_pause_ms: Silence inserted between sentence chunks. 0 turns
            chunking off entirely (single-shot synthesis, legacy behaviour).
    """

    def __init__(
        self,
        engine: str = DEFAULT_ENGINE,
        voice: str = DEFAULT_VOICE,
        speed: float = 1.0,
        sentence_pause_ms: int = 0,
    ):
        self.engine = engine
        self.voice = voice
        self.speed = float(speed)
        self.sentence_pause_ms = int(sentence_pause_ms)
        self._tts = None

    # ── model lifecycle ────────────────────────────────────────────────────

    def _ensure_loaded(self) -> None:
        if self._tts is not None:
            return
        try:
            from pythaitts import TTS  # type: ignore
        except ImportError as exc:
            raise RuntimeError(
                "PyThaiTTS is not installed. Run ./run to set up the venv."
            ) from exc
        log.info(
            "Loading PyThaiTTS pretrained=%s voice=%s speed=%.2f pause_ms=%d (first call only)",
            self.engine, self.voice, self.speed, self.sentence_pause_ms,
        )
        self._tts = TTS(pretrained=self.engine)

    # ── low-level: synthesise one chunk to one WAV ─────────────────────────

    def _synth_one(self, text: str, out_path: Path) -> None:
        assert self._tts is not None
        out_path.parent.mkdir(parents=True, exist_ok=True)
        self._tts.tts(
            text=text,
            filename=str(out_path),
            speaker_idx=self.voice,
            return_type="file",
        )
        if not out_path.exists() or out_path.stat().st_size == 0:
            raise RuntimeError(f"TTS produced no output at {out_path}")

    # ── public API ─────────────────────────────────────────────────────────

    def synthesise(self, text: str, out_path: Path) -> Path:
        """Render `text` to a WAV at `out_path` and return the path.

        Applies sentence chunking (if `sentence_pause_ms > 0`) and speed
        post-processing (if `speed != 1.0`) automatically.
        """
        self._ensure_loaded()
        out_path = Path(out_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)

        # Pick the synthesis path: single-shot vs chunked.
        if self.sentence_pause_ms <= 0:
            raw_target = out_path if self.speed == 1.0 else out_path.with_suffix(".raw.wav")
            self._synth_one(text, raw_target)
        else:
            chunks = _split_sentences(text)
            if len(chunks) <= 1:
                # Nothing useful to chunk — fall back to single shot.
                raw_target = out_path if self.speed == 1.0 else out_path.with_suffix(".raw.wav")
                self._synth_one(chunks[0] if chunks else text, raw_target)
            else:
                with tempfile.TemporaryDirectory() as td:
                    chunk_paths: list[Path] = []
                    for i, chunk in enumerate(chunks):
                        cp = Path(td) / f"chunk_{i:03d}.wav"
                        self._synth_one(chunk, cp)
                        chunk_paths.append(cp)
                    raw_target = out_path if self.speed == 1.0 else out_path.with_suffix(".raw.wav")
                    log.debug("Concatenating %d chunks with %d ms pauses → %s",
                              len(chunk_paths), self.sentence_pause_ms, raw_target)
                    _concat_wavs_with_silence(chunk_paths, self.sentence_pause_ms, raw_target)

        # Speed post-process if requested.
        if self.speed != 1.0:
            log.debug("Applying speed=%.3f via atempo → %s", self.speed, out_path)
            _apply_speed(raw_target, self.speed, out_path)
            raw_target.unlink(missing_ok=True)

        if not out_path.exists() or out_path.stat().st_size == 0:
            raise RuntimeError(f"TTS produced no output at {out_path}")
        return out_path
