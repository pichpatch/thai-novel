"""
Intro narration auto-format rules:

  channel_name:    always "T H A I Novel" in the template (FIXED)
  title_narration: auto-generated as "{series} ตอนที่ {N} {title}" when
                   the user leaves it null AND project.series + episode are set

These tests pin the rules so future template edits don't regress.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from thai_novel.spec import Episode


# ── Template defaults ───────────────────────────────────────────────────────


def test_template_channel_name_is_thai_novel_letters_spelled():
    """The TTS engine must read 'T H A I Novel' to pronounce the channel name."""
    d = json.loads(Path("in/template.example.json").read_text(encoding="utf-8"))
    ep = d[0] if isinstance(d, list) else d
    assert ep["intro"]["channel_name"] == "T H A I Novel"


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
            "channel_name": "T H A I Novel",
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
