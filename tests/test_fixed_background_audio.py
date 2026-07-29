from __future__ import annotations

import json
import asyncio
from pathlib import Path

import pytest

from thai_novel.channel import NARRATOR_VOICE
from thai_novel.encode import BACKGROUND_AUDIO_PATH, finalize
from thai_novel.spec import Episode, IntroConfig, NarrationBlock, TTSConfig


def test_channel_uses_premwadee_by_default() -> None:
    assert NARRATOR_VOICE == "th-TH-PremwadeeNeural"
    assert "voice" not in TTSConfig.model_fields


def test_audio_selection_is_not_part_of_episode_schema() -> None:
    assert "audio" not in Episode.model_fields
    assert "background_music_ref" not in IntroConfig.model_fields
    assert "music_override" not in NarrationBlock.model_fields
    assert "ambience_override" not in NarrationBlock.model_fields
    assert "sfx_cues" not in NarrationBlock.model_fields


def test_template_has_no_background_audio_keys() -> None:
    project_root = Path(__file__).resolve().parents[1]
    episodes = json.loads((project_root / "in/template.example.json").read_text(encoding="utf-8"))
    assert episodes
    for episode in episodes:
        assert {"engine", "voice", "rate"}.isdisjoint(episode["tts"])
        assert "audio" not in episode
        assert "background_music_ref" not in episode["intro"]
        for chapter in episode["chapters"]:
            for block in chapter["narration_blocks"]:
                assert "music_override" not in block
                assert "ambience_override" not in block
                assert "sfx_cues" not in block


def test_finalize_requires_the_fixed_background(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="library/audio/background.mp3"):
        asyncio.run(
            finalize(
                tmp_path / "raw.mp4",
                {"total_duration_sec": 1.0},
                tmp_path,
                tmp_path / "output",
            )
        )


def test_finalize_loops_one_fixed_background(monkeypatch, tmp_path: Path) -> None:
    background = tmp_path / BACKGROUND_AUDIO_PATH
    background.parent.mkdir(parents=True)
    background.write_bytes(b"test")
    captured: list[str] = []

    async def fake_run_ff(args: list[str]) -> tuple[int, bytes]:
        captured.extend(args)
        Path(args[-1]).write_bytes(b"mp4")
        return 0, b""

    monkeypatch.setattr("thai_novel.encode._run_ff", fake_run_ff)
    timeline = {
        "total_duration_sec": 12.5,
        "title": "ตอนทดสอบ",
        "series": "เรื่องทดสอบ",
        "episode": 1,
        "short_description": "เรื่องย่อ",
        "description_context": "",
        "intro": None,
        "chapters": [],
        "end_card": None,
    }

    asyncio.run(finalize(tmp_path / "raw.mp4", timeline, tmp_path, tmp_path / "output"))

    assert captured.count("-stream_loop") == 1
    assert str(background) in captured
    filter_graph = captured[captured.index("-filter_complex") + 1]
    assert "sidechaincompress" in filter_graph
    assert "amix=inputs=2" in filter_graph
