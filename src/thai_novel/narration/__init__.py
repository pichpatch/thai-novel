"""Phase B: narration pipeline."""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import asdict, dataclass
from pathlib import Path

from ..channel import NARRATOR_BASE_RATE, WELCOME_NARRATION
from ..spec import Episode, NarrationBlock
from .align import SubtitleCue, align_block
from .segment import segment_thai_with_pauses
from .stitch import stitch_block
from .synthesize import synthesize_many

log = logging.getLogger("thai_novel.narration")


@dataclass
class BlockNarration:
    """The Phase B result for one narration block."""

    block_id: str
    mood: str
    wav_path: Path
    duration_sec: float
    sentences: list[str]
    cues: list[SubtitleCue]

    def to_json_dict(self) -> dict:
        return {
            "block_id": self.block_id,
            "mood": self.mood,
            "wav_path": str(self.wav_path),
            "duration_sec": self.duration_sec,
            "sentences": self.sentences,
            "cues": [
                {
                    "start_sec": c.start_sec,
                    "end_sec": c.end_sec,
                    "text": c.text,
                    "words": c.words or [],
                }
                for c in self.cues
            ],
        }


def _mood_settings(episode: Episode, mood: str) -> tuple[str, str, int, int]:
    """Resolve (rate, pitch, sentence_pause_ms, paragraph_pause_ms)."""
    base = episode.tts
    pause = base.sentence_pause_ms
    paragraph_pause = base.paragraph_pause_ms
    rate = NARRATOR_BASE_RATE
    pitch = base.pitch
    if mood in base.mood_pauses:
        mp = base.mood_pauses[mood]
        if mp.sentence_pause_ms is not None:
            pause = mp.sentence_pause_ms
        if mp.paragraph_pause_ms is not None:
            paragraph_pause = mp.paragraph_pause_ms
        if mp.rate_override:
            rate = mp.rate_override
        if mp.pitch_override:
            pitch = mp.pitch_override
    return rate, pitch, pause, paragraph_pause


async def narrate_block(
    block: NarrationBlock,
    episode: Episode,
    sentence_cache_dir: Path,
    block_wav_dir: Path,
    on_progress=None,
) -> BlockNarration:
    rate, pitch, sentence_pause_ms, paragraph_pause_ms = _mood_settings(episode, block.mood)
    sentences, pause_after_ms = segment_thai_with_pauses(
        block.narration,
        sentence_pause_ms=sentence_pause_ms,
        paragraph_pause_ms=paragraph_pause_ms,
    )

    payloads = [(s, rate, pitch) for s in sentences]
    sentence_wavs = await synthesize_many(payloads, sentence_cache_dir, on_progress=on_progress)

    block_wav = block_wav_dir / f"{block.id}.wav"
    duration = stitch_block(
        sentence_wavs,
        sentence_pause_ms,
        block_wav,
        pause_after_ms=pause_after_ms,
    )

    cues = align_block(block_wav, sentences, language="th")

    return BlockNarration(
        block_id=block.id,
        mood=block.mood,
        wav_path=block_wav,
        duration_sec=duration,
        sentences=sentences,
        cues=cues,
    )


async def narrate_episode(
    episode: Episode,
    project_root: Path,
    on_progress=None,
) -> list[BlockNarration]:
    """
    Synthesize all narration for an episode. Returns one BlockNarration per
    narration_block (including auto-generated intro/title pre-roll blocks).

    Side effects:
      - per-block .wav files in cache/<episode_id>/blocks/
      - manifest at cache/<episode_id>/narration.json
    """
    sentence_cache = project_root / "cache" / "narration"
    ep_cache = project_root / "cache" / episode.project.id
    blocks_dir = ep_cache / "blocks"
    sentence_cache.mkdir(parents=True, exist_ok=True)
    blocks_dir.mkdir(parents=True, exist_ok=True)

    # ── Intro pre-roll blocks (auto-generated from intro config) ────────────
    intro_blocks: list[NarrationBlock] = []
    if episode.intro.show:
        intro_blocks.append(NarrationBlock(
            id="intro_welcome",
            mood="cozy",
            duration_hint_sec=int(episode.intro.welcome_duration_sec),
            narration=WELCOME_NARRATION,
        ))
        ep_num = episode.project.episode
        ep_title = episode.project.title
        ep_series = episode.project.series
        # Auto-format priority:
        #   1. explicit title_narration if user set it
        #   2. "{series} ตอนที่ {N} {title}"    (series + episode number + title)
        #   3. "ตอนที่ {N} {title}"             (no series)
        #   4. just title (no episode number)
        if episode.intro.title_narration:
            title_text = episode.intro.title_narration
        elif ep_series and ep_num is not None:
            title_text = f"{ep_series} ตอนที่ {ep_num} {ep_title}"
        elif ep_num is not None:
            title_text = f"ตอนที่ {ep_num} {ep_title}"
        else:
            title_text = ep_title
        intro_blocks.append(NarrationBlock(
            id="intro_title",
            mood="cozy",
            duration_hint_sec=int(episode.intro.title_card_duration_sec),
            narration=title_text,
        ))

    story_blocks: list[NarrationBlock] = []
    for chapter in episode.chapters:
        story_blocks.extend(chapter.narration_blocks)

    all_blocks = intro_blocks + story_blocks

    results: list[BlockNarration] = []
    for i, block in enumerate(all_blocks):
        log.info(f"narrating {block.id} ({i+1}/{len(all_blocks)}, mood={block.mood})")
        result = await narrate_block(
            block, episode, sentence_cache, blocks_dir, on_progress=on_progress
        )
        results.append(result)

    manifest = {
        "episode_id": episode.project.id,
        "blocks": [r.to_json_dict() for r in results],
        "total_duration_sec": sum(r.duration_sec for r in results),
    }
    (ep_cache / "narration.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    return results


__all__ = ["narrate_episode", "narrate_block", "BlockNarration"]
