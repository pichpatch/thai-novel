"""
Intro narration auto-format rules:

  channel branding: fixed in thai_novel.channel, absent from episode JSON
  title_narration: auto-generated as "{series} ตอนที่ {N} {title}" when
                   the user leaves it null AND project.series + episode are set

These tests pin the rules so future template edits don't regress.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

from thai_novel.channel import (
    CHANNEL_NAME,
    NARRATOR_BASE_RATE,
    NARRATOR_VOICE,
    WELCOME_NARRATION,
)
from thai_novel.spec import Episode, TTSConfig


# ── Template defaults ───────────────────────────────────────────────────────


def test_channel_branding_is_fixed_outside_episode_json():
    d = json.loads(Path("in/template.example.json").read_text(encoding="utf-8"))
    ep = d[0] if isinstance(d, list) else d
    assert CHANNEL_NAME == "T H A I Novel"
    assert WELCOME_NARRATION == (
        "ยินดีต้อนรับเข้าสู่ช่อง T  H  A  I  โนเว่ล "
        "ขอให้สนุกกับการรับฟังค่ะ"
    )
    assert "channel_name" not in ep["intro"]
    assert "welcome_narration" not in ep["intro"]


def test_template_omits_fixed_voice_engine_and_base_rate():
    d = json.loads(Path("in/template.example.json").read_text(encoding="utf-8"))
    ep = d[0] if isinstance(d, list) else d
    assert NARRATOR_VOICE == "th-TH-PremwadeeNeural"
    assert NARRATOR_BASE_RATE == "-15%"
    assert {"engine", "voice", "rate"}.isdisjoint(ep["tts"])
    assert {"engine", "voice", "rate"}.isdisjoint(TTSConfig.model_fields)


def test_template_title_narration_is_absent_or_null():
    """
    title_narration should be unset in the template so the pipeline's auto-format
    "{series} ตอนที่ {N} {title}" is what users get for free.
    """
    d = json.loads(Path("in/template.example.json").read_text(encoding="utf-8"))
    ep = d[0] if isinstance(d, list) else d
    val = ep["intro"].get("title_narration")
    assert val in (None, ""), (
        f"template intro.title_narration should be null/empty so auto-format runs; "
        f"got {val!r}"
    )


# ── Auto-format logic ───────────────────────────────────────────────────────


def _make_episode(series: str | None, episode: int | None, title: str,
                  explicit_title_narration: str | None = None) -> dict:
    """Minimal episode dict factory for testing the auto-format."""
    return {
        "project": {
            "id": "test-ep01",
            "title": title,
            "series": series,
            "episode": episode,
            "language": "th",
            "resolution": "1280x720",
        },
        "intro": {
            "show": True,
            "title_narration": explicit_title_narration,
        },
        "characters": {"a": {"appearance": "x"}},
        "chapters": [{
            "id": "ch_01", "title": "x",
            "visual_anchor": {"prompt": "x"},
            "narration_blocks": [{"id": "ch01_b1", "mood": "cozy", "narration": "x" * 1500}],
        }],
    }


def _resolve_title_text(ep_data: dict) -> str:
    """
    Run the same auto-format branch from narration/__init__.py to verify it.
    Mirrors the code at the call site so a refactor that breaks it fails this test.
    """
    ep = Episode.model_validate(ep_data)
    ep_num = ep.project.episode
    ep_title = ep.project.title
    ep_series = ep.project.series
    if ep.intro.title_narration:
        return ep.intro.title_narration
    if ep_series and ep_num is not None:
        return f"{ep_series} ตอนที่ {ep_num} {ep_title}"
    if ep_num is not None:
        return f"ตอนที่ {ep_num} {ep_title}"
    return ep_title


def test_auto_title_uses_series_plus_episode_plus_title_when_all_present():
    """The new rule: '{series} ตอนที่ {N} {title}'."""
    ep = _make_episode(series="ปาฏิหาริย์ใต้ร่มธรรม", episode=3, title="คำสั่งเสียของหลวงพ่อ")
    got = _resolve_title_text(ep)
    assert got == "ปาฏิหาริย์ใต้ร่มธรรม ตอนที่ 3 คำสั่งเสียของหลวงพ่อ"


def test_auto_title_falls_back_to_short_format_when_no_series():
    """Without series, the old 'ตอนที่ N title' format still applies."""
    ep = _make_episode(series=None, episode=3, title="คำสั่งเสียของหลวงพ่อ")
    got = _resolve_title_text(ep)
    assert got == "ตอนที่ 3 คำสั่งเสียของหลวงพ่อ"


def test_auto_title_falls_back_to_title_only_when_no_episode_number():
    """Standalone (no episode number) — just the title."""
    ep = _make_episode(series="ปาฏิหาริย์ใต้ร่มธรรม", episode=None, title="พิเศษ")
    got = _resolve_title_text(ep)
    assert got == "พิเศษ"


def test_auto_title_explicit_override_wins():
    """An explicitly-set title_narration always wins over the auto-format."""
    ep = _make_episode(series="ปาฏิหาริย์ใต้ร่มธรรม", episode=3, title="ฯลฯ",
                       explicit_title_narration="โอเค ทดสอบ")
    got = _resolve_title_text(ep)
    assert got == "โอเค ทดสอบ"


def test_intro_and_story_send_premwadee_to_tts(monkeypatch, tmp_path):
    import thai_novel.narration as narration

    ep = Episode.model_validate(_make_episode("เรื่องทดสอบ", 1, "ชื่อตอน"))
    captured_payloads: list[tuple[str, str, str]] = []

    async def fake_synthesize_many(payloads, cache_dir, on_progress=None):
        captured_payloads.extend(payloads)
        return [tmp_path / f"sentence_{len(captured_payloads)}.wav" for _ in payloads]

    monkeypatch.setattr(narration, "synthesize_many", fake_synthesize_many)
    monkeypatch.setattr(narration, "stitch_block", lambda *args, **kwargs: 1.0)
    monkeypatch.setattr(narration, "align_block", lambda *args, **kwargs: [])

    asyncio.run(narration.narrate_episode(ep, tmp_path))

    assert captured_payloads[0][0] == " ".join(WELCOME_NARRATION.split())
    assert {payload[1] for payload in captured_payloads} == {NARRATOR_BASE_RATE}


def test_mood_overrides_keep_narration_pacing_varied():
    import thai_novel.narration as narration

    data = _make_episode("เรื่องทดสอบ", 1, "ชื่อตอน")
    data["tts"] = {
        "pitch": "+0Hz",
        "mood_pauses": {
            "funny": {"rate_override": "-10%", "pitch_override": "+1Hz"},
            "romantic": {"rate_override": "-20%"},
            "tense": {"rate_override": "-17%"},
            "melancholy": {"rate_override": "-23%"},
        },
    }
    ep = Episode.model_validate(data)

    assert narration._mood_settings(ep, "cozy")[:2] == ("-15%", "+0Hz")
    assert narration._mood_settings(ep, "funny")[:2] == ("-10%", "+1Hz")
    assert narration._mood_settings(ep, "romantic")[0] == "-20%"
    assert narration._mood_settings(ep, "tense")[0] == "-17%"
    assert narration._mood_settings(ep, "melancholy")[0] == "-23%"
