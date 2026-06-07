"""
Pydantic schema for thai-novel episode JSON.

The JSON in `in/*.json` is either:
  - a single Episode object, OR
  - a list of Episode objects (batch mode — render N episodes in one run)

See in/example.json for a complete worked example,
and docs/JSON_SCHEMA.md for the field-by-field reference.

Forgiving loader: load_episodes() normalizes common spec drift before
validation (auto-generates missing narration_block ids, maps mood/motion
aliases). See _normalize_episode_dict().
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

log = logging.getLogger("thai_novel.spec")

# ─────────────────────────────────────────────────────────────────────────────
# Enums / literals
# ─────────────────────────────────────────────────────────────────────────────

Mood = Literal["cozy", "funny", "romantic", "tense", "melancholy", "playful"]
MotionPreset = Literal[
    "slow_zoom_in",
    "slow_zoom_out",
    "pan_left",
    "pan_right",
    "parallax_depth",
    "subtle_handheld",
    "ken_burns_combo",
    "static",
]
TTSEngine = Literal["edge-tts", "piper"]
ImageEngine = Literal[
    "sdxl-turbo",
    "sdxl-lightning-4step",
    "sdxl-lightning-8step",   # 2× steps, ~2× time, noticeably cleaner output
    "hyper-sdxl-4step",       # ByteDance Hyper-SD LoRA on any SDXL base (incl. anime bases)
    "hyper-sdxl-8step",       # ⭐ best quality-for-time on SDXL — recommended default
    "flux-schnell-4step",     # Black Forest Labs FLUX.1-schnell — highest quality, very slow on M2 Pro
    "z-image-turbo",
]
ImageBackend = Literal["mlx", "coreml", "diffusers-mps"]
ColorGrade = Literal[
    "warm_cozy", "cool_night", "golden_hour", "melancholy_blue", "neutral", "playful_pop"
]

# ─────────────────────────────────────────────────────────────────────────────
# Sub-models
# ─────────────────────────────────────────────────────────────────────────────


class Project(BaseModel):
    id: str = Field(..., description="Stable identifier, used for output filename slug.")
    title: str
    series: str | None = None
    episode: int | None = None
    language: Literal["th"] = "th"
    theme: str | None = None
    resolution: str = "1920x1080"
    fps: int = 30
    target_duration_min: int | None = None

    @field_validator("id")
    @classmethod
    def id_must_be_slug_safe(cls, v: str) -> str:
        if not re.match(r"^[a-z0-9][a-z0-9-_]*$", v):
            raise ValueError(
                f"project.id must be lowercase alphanumeric with - or _, got '{v}'"
            )
        return v

    @field_validator("resolution")
    @classmethod
    def resolution_format(cls, v: str) -> str:
        if not re.match(r"^\d+x\d+$", v):
            raise ValueError(f"resolution must look like '1920x1080', got '{v}'")
        return v

    @property
    def width(self) -> int:
        return int(self.resolution.split("x")[0])

    @property
    def height(self) -> int:
        return int(self.resolution.split("x")[1])


class MoodPause(BaseModel):
    sentence_pause_ms: int | None = None
    paragraph_pause_ms: int | None = None
    rate_override: str | None = None
    pitch_override: str | None = None


class TTSConfig(BaseModel):
    engine: TTSEngine = "edge-tts"
    voice: str = "th-TH-PremwadeeNeural"
    rate: str = "-10%"
    pitch: str = "+0Hz"
    sentence_pause_ms: int = 200
    paragraph_pause_ms: int = 800
    mood_pauses: dict[Mood, MoodPause] = Field(default_factory=dict)


class ImageGeneration(BaseModel):
    engine: ImageEngine = "sdxl-lightning-4step"
    backend: ImageBackend = "mlx"
    steps: int = 4
    guidance: float = 1.5
    seed: int | None = None
    # Per-spec: generate at 1024x576 (16:9 native), upscale to export resolution.
    gen_width: int = 1024
    gen_height: int = 576
    upscaler: Literal["realesrgan", "lanczos", "none"] = "realesrgan"
    # Optional override of the SDXL base checkpoint. Used by `hyper-sdxl-4step`
    # to point at an anime base (e.g. "cagliostrolab/animagine-xl-3.1").
    # Other engines ignore it.
    base_model: str | None = None

    @model_validator(mode="after")
    def gen_size_is_16_9(self) -> ImageGeneration:
        ratio = self.gen_width / self.gen_height
        if abs(ratio - 16 / 9) > 0.01:
            raise ValueError(
                f"gen_width x gen_height should be 16:9; got {self.gen_width}x{self.gen_height}"
            )
        return self


Tone = Literal["realistic", "anime"]


class VisualStyle(BaseModel):
    # High-level aesthetic. Drives:
    #   - automatic prompt-keyword injection (realistic → "photograph, photorealistic, ..."
    #     vs anime → "anime style, illustration, ...")
    #   - automatic base_model selection when image_generation.base_model is unset
    #     (realistic → SDXL base 1.0;  anime → cagliostrolab/animagine-xl-3.1)
    # Override either knob explicitly (base_model in image_generation, or extra
    # keywords in base_prompt) and your override wins.
    tone: Tone = "realistic"
    base_prompt: str = ""
    negative_prompt: str = "low quality, blurry, bad anatomy, text, watermark"
    color_grade: ColorGrade = "warm_cozy"


class CharacterSpec(BaseModel):
    name: str | None = None
    appearance: str
    wardrobe: str | None = None
    voice_notes: str | None = None


class MusicBed(BaseModel):
    default: str | None = None                              # library://music/cozy_piano_01
    by_mood: dict[Mood, str] = Field(default_factory=dict)
    volume_db: float = -22.0
    crossfade_ms: int = 1500
    duck_during_dialogue_db: float = -6.0


class Ambience(BaseModel):
    default: str | None = None
    by_mood: dict[Mood, str] = Field(default_factory=dict)
    volume_db: float = -28.0


class AudioConfig(BaseModel):
    music_bed: MusicBed = Field(default_factory=MusicBed)
    ambience: Ambience = Field(default_factory=Ambience)


class SubtitleConfig(BaseModel):
    enabled: bool = False                                    # off by default — subs overlay can crowd the cinematic frame
    font: str = "Sarabun"
    size_px: int = 48
    max_chars_per_line: int = 38
    style: Literal["soft_drop_shadow", "stroke", "backdrop"] = "soft_drop_shadow"
    position: Literal["bottom_center", "bottom_left", "top_center"] = "bottom_center"
    karaoke_reveal: bool = True
    emphasize_character_names: bool = True


class VisualAnchor(BaseModel):
    """
    Either reference a library asset (`ref`) OR generate one (`prompt`).

    Optional `save_to_library_as` promotes a generated image into the
    library on first render, so subsequent episodes can ref it.
    """

    ref: str | None = None                                   # library://backgrounds/cafe_rainy_night
    prompt: str | None = None
    save_to_library_as: str | None = None                    # e.g. "cafe_rainy_night"
    motion: MotionPreset = "slow_zoom_in"
    color_grade: ColorGrade | None = None                    # overrides project default

    @model_validator(mode="after")
    def must_have_ref_or_prompt(self) -> VisualAnchor:
        if not self.ref and not self.prompt:
            raise ValueError("visual_anchor needs either 'ref' or 'prompt'")
        if self.ref and self.prompt:
            raise ValueError("visual_anchor can't have BOTH 'ref' and 'prompt' — pick one")
        if self.ref and not self.ref.startswith("library://"):
            raise ValueError(f"ref must start with 'library://', got '{self.ref}'")
        if self.save_to_library_as and not self.prompt:
            raise ValueError("save_to_library_as only makes sense with a 'prompt'")
        return self


class SFXCue(BaseModel):
    at_sec: float
    ref: str                                                  # library://sfx/cup_clink
    volume_db: float = -12.0


class NarrationBlock(BaseModel):
    id: str
    mood: Mood = "cozy"
    duration_hint_sec: int | None = None                      # advisory only
    narration: str = Field(..., min_length=1)
    subtitle_emphasis: list[str] = Field(default_factory=list)
    music_override: str | None = None
    ambience_override: str | None = None
    anchor_override: VisualAnchor | None = None
    sfx_cues: list[SFXCue] = Field(default_factory=list)

    @field_validator("id")
    @classmethod
    def block_id_is_slug(cls, v: str) -> str:
        if not re.match(r"^[a-z0-9][a-z0-9_]*$", v):
            raise ValueError(f"narration_block.id must be slug-safe, got '{v}'")
        return v


class Chapter(BaseModel):
    id: str
    title: str
    # Default OFF — this is an audiobook. A silent ~4s title card between
    # chapters is dead air for listeners. Set true explicitly per chapter
    # only if you want a visual breath (e.g. a montage interlude).
    show_title_card: bool = False
    title_card_duration_sec: float = 4.0
    visual_anchor: VisualAnchor
    narration_blocks: list[NarrationBlock] = Field(..., min_length=1)

    @field_validator("id")
    @classmethod
    def chapter_id_is_slug(cls, v: str) -> str:
        if not re.match(r"^[a-z0-9][a-z0-9_]*$", v):
            raise ValueError(f"chapter.id must be slug-safe, got '{v}'")
        return v


class EndCard(BaseModel):
    show: bool = True
    duration_sec: float = 8.0
    next_episode_title: str | None = None
    message: str | None = None


class IntroConfig(BaseModel):
    """
    Per-episode intro shown BEFORE the first chapter.

    Two stages:
      1. Channel welcome:  "ยินดีต้อนรับสู่ช่อง {channel_name}"  (~5s)
      2. Episode title:    "ตอนที่ {episode}: {title}"           (~4s)

    Both are spoken (edge-tts) and shown on screen with the channel logo
    and a soft background music bed.
    """

    show: bool = True
    channel_name: str = "THAI Novel"
    welcome_narration: str | None = None              # auto: "ยินดีต้อนรับสู่ช่อง <channel>"
    welcome_duration_sec: float = 5.0
    title_narration: str | None = None                # auto: "ตอนที่ <n>: <title>"
    title_card_duration_sec: float = 4.5
    background_music_ref: str | None = "library://music/intro_theme"
    logo_ref: str | None = "library://overlays/channel_logo"
    background_anchor: VisualAnchor | None = None     # optional: background image during welcome


# ─────────────────────────────────────────────────────────────────────────────
# Top-level
# ─────────────────────────────────────────────────────────────────────────────


class Episode(BaseModel):
    project: Project
    tts: TTSConfig = Field(default_factory=TTSConfig)
    image_generation: ImageGeneration = Field(default_factory=ImageGeneration)
    visual_style: VisualStyle = Field(default_factory=VisualStyle)
    characters: dict[str, CharacterSpec] = Field(default_factory=dict)
    audio: AudioConfig = Field(default_factory=AudioConfig)
    subtitles: SubtitleConfig = Field(default_factory=SubtitleConfig)
    intro: IntroConfig = Field(default_factory=IntroConfig)
    chapters: list[Chapter] = Field(..., min_length=1)
    end_card: EndCard | None = Field(default_factory=EndCard)

    # ── Derived stats (not in JSON; computed for reporting) ───────────────────

    @property
    def total_narration_chars(self) -> int:
        return sum(
            len(b.narration)
            for c in self.chapters
            for b in c.narration_blocks
        )

    @property
    def estimated_duration_sec(self) -> float:
        """Sum of duration_hint_sec where present; useful for cost preview."""
        hints = [
            b.duration_hint_sec
            for c in self.chapters
            for b in c.narration_blocks
            if b.duration_hint_sec is not None
        ]
        chapter_card_time = sum(
            c.title_card_duration_sec for c in self.chapters if c.show_title_card
        )
        end_card_time = self.end_card.duration_sec if self.end_card and self.end_card.show else 0
        return sum(hints) + chapter_card_time + end_card_time

    @property
    def anchor_count(self) -> int:
        """Number of unique visual anchors (chapter-level + per-block overrides)."""
        unique: set[tuple[str, str | None]] = set()
        for c in self.chapters:
            a = c.visual_anchor
            unique.add(("ref" if a.ref else "prompt", a.ref or a.prompt))
            for b in c.narration_blocks:
                if b.anchor_override:
                    ao = b.anchor_override
                    unique.add(("ref" if ao.ref else "prompt", ao.ref or ao.prompt))
        return len(unique)


# ─────────────────────────────────────────────────────────────────────────────
# Loading: accepts either a single Episode object or a list
# ─────────────────────────────────────────────────────────────────────────────


# ─────────────────────────────────────────────────────────────────────────────
# Forgiving loader — auto-fix common spec drift before validation
# ─────────────────────────────────────────────────────────────────────────────

# Cowork-generated specs sometimes use near-miss names. Rather than reject them
# and force manual file edits, we normalize them silently at load time. Any
# remap is logged at INFO level so authors can see what was fixed.

_MOOD_ALIASES = {
    "melancholic": "melancholy",
    "sad":         "melancholy",
    "happy":       "playful",
    "calm":        "cozy",
    "neutral":     "cozy",
    "angry":       "tense",
    "scared":      "tense",
}

_MOTION_ALIASES = {
    # User-friendly variants that aren't in our official preset list
    "slow_pan_left":  "pan_left",
    "slow_pan_right": "pan_right",
    "slow_pan_up":    "pan_left",   # closest equivalent (the composer ignores motion anyway)
    "slow_pan_down":  "pan_right",
    "fade_in":        "static",
    "fade_out":       "static",
    "none":           "static",
    "":               "static",
}


def _normalize_episode_dict(raw: dict, source: str = "<spec>") -> dict:
    """
    Pre-process raw JSON to fix common AI-generated discrepancies before
    Pydantic validation. Modifications:
      - Auto-generate `narration_block.id` if missing (e.g. 'chapter_001_b1')
      - Auto-generate `chapter.id` if missing (e.g. 'ch_01')
      - Remap known `mood` aliases (e.g. melancholic → melancholy)
      - Remap known `motion` aliases (e.g. slow_pan_left → pan_left)
    Always logs (INFO) what was changed so the author can clean their source.
    """
    if not isinstance(raw, dict):
        return raw

    fixes: list[str] = []

    for ci, ch in enumerate(raw.get("chapters", []) or []):
        if not isinstance(ch, dict):
            continue

        # Chapter id (rare miss, but cheap to handle)
        if not ch.get("id"):
            new_id = f"ch_{ci+1:02d}"
            fixes.append(f"chapter[{ci}].id ← '{new_id}' (was missing)")
            ch["id"] = new_id

        # Chapter visual_anchor.motion
        va = ch.get("visual_anchor") or {}
        if isinstance(va, dict) and "motion" in va and va["motion"] in _MOTION_ALIASES:
            old = va["motion"]
            va["motion"] = _MOTION_ALIASES[old]
            fixes.append(f"chapter[{ci}].visual_anchor.motion: '{old}' → '{va['motion']}'")

        # Narration blocks
        for bi, b in enumerate(ch.get("narration_blocks", []) or []):
            if not isinstance(b, dict):
                continue
            # Block id
            if not b.get("id"):
                new_id = f"{ch['id']}_b{bi+1}"
                fixes.append(f"chapter[{ci}].narration_blocks[{bi}].id ← '{new_id}' (was missing)")
                b["id"] = new_id
            # Mood
            if "mood" in b and b["mood"] in _MOOD_ALIASES:
                old = b["mood"]
                b["mood"] = _MOOD_ALIASES[old]
                fixes.append(f"chapter[{ci}].narration_blocks[{bi}].mood: '{old}' → '{b['mood']}'")
            # anchor_override.motion (per-scene image)
            ao = b.get("anchor_override") or {}
            if isinstance(ao, dict) and "motion" in ao and ao["motion"] in _MOTION_ALIASES:
                old = ao["motion"]
                ao["motion"] = _MOTION_ALIASES[old]
                fixes.append(
                    f"chapter[{ci}].narration_blocks[{bi}].anchor_override.motion: "
                    f"'{old}' → '{ao['motion']}'"
                )

    if fixes:
        log.info(f"[{source}] auto-normalized {len(fixes)} field(s):")
        for f in fixes[:20]:  # cap log spam
            log.info(f"  - {f}")
        if len(fixes) > 20:
            log.info(f"  ... and {len(fixes) - 20} more")

    return raw


def load_episodes(path: Path) -> list[Episode]:
    """
    Load one or more Episode objects from a JSON file.

    Pre-normalizes common AI-generated quirks (missing block ids, mood/motion
    aliases) so specs that are 'almost right' validate instead of erroring out.
    See _normalize_episode_dict() for the full list of auto-fixes.

    Raises pydantic.ValidationError with a multi-line, human-readable message
    if anything is malformed beyond what the normalizer can repair. The CLI's
    `validate` command catches this and pretty-prints with rich.
    """
    raw: Any = json.loads(path.read_text(encoding="utf-8"))
    source = path.name
    if isinstance(raw, list):
        return [Episode.model_validate(_normalize_episode_dict(item, source)) for item in raw]
    if isinstance(raw, dict):
        return [Episode.model_validate(_normalize_episode_dict(raw, source))]
    raise ValueError(
        f"Top-level JSON must be either an Episode object or a list of Episodes; "
        f"got {type(raw).__name__}"
    )
