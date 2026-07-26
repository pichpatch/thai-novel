"""Phase D-1: timeline compiler — Episode + narration + anchors -> timeline.json."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from ..narration import BlockNarration
from ..images import ResolvedAnchor
from ..spec import Episode

log = logging.getLogger("thai_novel.timeline")


def compile_timeline(
    episode: Episode,
    blocks: list[BlockNarration],
    anchors: list[ResolvedAnchor],
    project_root: Path,
) -> Path:
    """
    Build the timeline.json that the pure-ffmpeg composer reads.

    Layout:
      [0,           W]       intro welcome card
      [W,        W+T]       episode title card
      [W+T,        ...]      chapter title cards + visual anchors + subtitles
      [end-E,    end]       end card

    Returns the path to the written timeline.json.
    """
    anchor_by_id = {a.anchor_id: a for a in anchors}
    block_by_id = {b.block_id: b for b in blocks}

    cursor = 0.0

    # ── Intro ───────────────────────────────────────────────────────────────
    intro_section: dict | None = None
    if episode.intro.show:
        welcome_block = block_by_id.get("intro_welcome")
        title_block = block_by_id.get("intro_title")
        if welcome_block is None or title_block is None:
            raise RuntimeError("Intro narration missing — run `./novel narrate` first.")

        welcome_dur = max(welcome_block.duration_sec, episode.intro.welcome_duration_sec)
        title_dur = max(title_block.duration_sec, episode.intro.title_card_duration_sec)

        intro_section = {
            "show": True,
            "channel_name": episode.intro.channel_name,
            "welcome_text": (
                episode.intro.welcome_narration
                or f"ยินดีต้อนรับสู่ช่อง {episode.intro.channel_name}"
            ),
            "title_text": episode.intro.title_narration or (
                f"ตอนที่ {episode.project.episode} — {episode.project.title}"
                if episode.project.episode is not None else episode.project.title
            ),
            "welcome_start_sec": cursor,
            "welcome_duration_sec": welcome_dur,
            "title_start_sec": cursor + welcome_dur,
            "title_duration_sec": title_dur,
            "welcome_audio_path": str(welcome_block.wav_path.relative_to(project_root)),
            "title_audio_path": str(title_block.wav_path.relative_to(project_root)),
            "background_music_ref": episode.intro.background_music_ref,
            "logo_ref": episode.intro.logo_ref,
            "background_image_path": (
                str(anchor_by_id["intro_background"].image_path_1080p.relative_to(project_root))
                if "intro_background" in anchor_by_id else None
            ),
        }
        cursor += welcome_dur + title_dur

    # ── Chapters ────────────────────────────────────────────────────────────
    chapter_sections: list[dict] = []
    for ch in episode.chapters:
        ch_start = cursor
        title_card_dur = ch.title_card_duration_sec if ch.show_title_card else 0.0
        if ch.show_title_card:
            cursor += title_card_dur

        block_sections: list[dict] = []
        chapter_blocks_duration = 0.0
        for b in ch.narration_blocks:
            bn = block_by_id[b.id]
            block_start = cursor
            dur = bn.duration_sec

            if b.anchor_override is not None:
                ax = anchor_by_id[f"{ch.id}/{b.id}"]
                motion = b.anchor_override.motion
                color_grade = b.anchor_override.color_grade or episode.visual_style.color_grade
            else:
                ax = anchor_by_id[ch.id]
                motion = ch.visual_anchor.motion
                color_grade = ch.visual_anchor.color_grade or episode.visual_style.color_grade

            block_sections.append({
                "id": b.id,
                "mood": b.mood,
                "start_sec": block_start,
                "duration_sec": dur,
                "audio_path": str(bn.wav_path.relative_to(project_root)),
                "image_path": str(ax.image_path_1080p.relative_to(project_root)),
                "motion": motion,
                "color_grade": color_grade,
                "music_ref": (
                    b.music_override
                    or episode.audio.music_bed.by_mood.get(b.mood)
                    or episode.audio.music_bed.default
                ),
                "ambience_ref": (
                    b.ambience_override
                    or episode.audio.ambience.by_mood.get(b.mood)
                    or episode.audio.ambience.default
                ),
                "subtitles": [
                    {
                        "start_sec": cue.start_sec,
                        "end_sec": cue.end_sec,
                        "text": cue.text,
                        "words": cue.words or [],
                    }
                    for cue in bn.cues
                ],
                "subtitle_emphasis": b.subtitle_emphasis,
                "sfx_cues": [
                    {"at_sec": s.at_sec, "ref": s.ref, "volume_db": s.volume_db}
                    for s in b.sfx_cues
                ],
            })
            cursor += dur
            chapter_blocks_duration += dur

        chapter_sections.append({
            "id": ch.id,
            "title": ch.title,
            "show_title_card": ch.show_title_card,
            "title_card_duration_sec": title_card_dur,
            "start_sec": ch_start,
            "duration_sec": title_card_dur + chapter_blocks_duration,
            "blocks": block_sections,
        })

    # ── End card ────────────────────────────────────────────────────────────
    end_card_section: dict | None = None
    if episode.end_card and episode.end_card.show:
        end_card_section = {
            "show": True,
            "start_sec": cursor,
            "duration_sec": episode.end_card.duration_sec,
            "next_episode_title": episode.end_card.next_episode_title,
            "message": episode.end_card.message,
        }
        cursor += episode.end_card.duration_sec

    timeline = {
        "version": 1,
        "episode_id": episode.project.id,
        "title": episode.project.title,
        "series": episode.project.series,
        "episode": episode.project.episode,
        "short_description": episode.project.short_description,
        "description_context": episode.project.description_context,
        "language": episode.project.language,
        "width": episode.project.width,
        "height": episode.project.height,
        "fps": episode.project.fps,
        "total_duration_sec": cursor,
        "subtitles_config": episode.subtitles.model_dump(),
        "visual_style": episode.visual_style.model_dump(),
        "characters": {k: v.model_dump() for k, v in episode.characters.items()},
        "audio_config": episode.audio.model_dump(),
        "intro": intro_section,
        "chapters": chapter_sections,
        "end_card": end_card_section,
    }

    out_path = project_root / "cache" / episode.project.id / "timeline.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(timeline, ensure_ascii=False, indent=2), encoding="utf-8")
    log.info(f"timeline compiled: {timeline['total_duration_sec']:.1f}s -> {out_path}")
    return out_path


__all__ = ["compile_timeline"]
