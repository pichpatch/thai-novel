from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from thai_novel.cli import _group_for_publication, _resolve_inputs, app
from thai_novel.spec import Episode, StoryBible, load_story_bible


def _episode(n: int) -> Episode:
    return Episode.model_validate({
        "project": {
            "id": f"demo-ep{n:02d}",
            "title": f"ชื่อตอน {n}",
            "series": "เรื่องทดลอง",
            "episode": n,
            "short_description": f"เรื่องย่อตอนที่ {n}",
            "resolution": "1280x720",
        },
        "intro": {"show": True, "channel_name": "T-H-A-I Novel"},
        "chapters": [{
            "id": "ch_01",
            "title": f"บทของตอน {n}",
            "visual_anchor": {
                "ref": f"library://backgrounds/demo_ep{n:02d}",
                "motion": "static",
            },
            "narration_blocks": [{
                "id": "ch01_b1",
                "mood": "cozy",
                "narration": "ก" * 1500,
            }],
        }],
    })


def test_story_bible_schema_round_trips(tmp_path: Path):
    path = tmp_path / "ep0.json"
    path.write_text(json.dumps({
        "kind": "story_bible",
        "series": "เรื่องทดลอง",
        "title": "ชื่อเรื่อง",
        "whole_story_summary": "สรุปทั้งเรื่อง",
        "poster_prompt": "Thai fantasy ensemble poster, dramatic light",
        "episode_image_style_prompt": "consistent cinematic Thai period drama",
        "episode_plan": [{
            "episode": 1,
            "title": "จุดเริ่มต้น",
            "short_description": "คำโปรยตอนแรก",
            "image_prompt": "ancient Thai city at sunrise",
        }],
    }), encoding="utf-8")

    bible = load_story_bible(path)

    assert isinstance(bible, StoryBible)
    assert bible.episode_plan[0].episode == 1


def test_auto_pick_skips_ep0_story_bible(tmp_path: Path, monkeypatch):
    in_dir = tmp_path / "in"
    in_dir.mkdir()
    (in_dir / "ep0.json").write_text("{}", encoding="utf-8")
    (in_dir / "ep01.json").write_text("{}", encoding="utf-8")
    (in_dir / "template.example.json").write_text("{}", encoding="utf-8")

    monkeypatch.setattr("thai_novel.cli.IN_DIR", in_dir)

    assert [p.name for p in _resolve_inputs(None)] == ["ep01.json"]


def test_publication_groups_cap_at_ten():
    pairs = [(Path(f"in/ep{i:02d}.json"), _episode(i)) for i in range(1, 12)]

    groups = _group_for_publication(pairs, group_size=10)

    assert [ep.project.id for _, ep in groups] == ["demo-ep01-ep10", "demo-ep11-ep11"]
    assert [len(ep.chapters) for _, ep in groups] == [10, 1]
    assert groups[0][1].anchor_count == 10
    assert "ตอนที่ 1 ชื่อตอน 1" in groups[0][1].project.short_description
    assert "เรื่องย่อตอนที่ 10" in groups[0][1].project.short_description


def test_validate_accepts_explicit_ep0(tmp_path: Path, monkeypatch):
    project = tmp_path
    in_dir = project / "in"
    in_dir.mkdir()
    (in_dir / "ep0.json").write_text(json.dumps({
        "kind": "story_bible",
        "series": "เรื่องทดลอง",
        "title": "ชื่อเรื่อง",
        "whole_story_summary": "สรุปทั้งเรื่อง",
        "poster_prompt": "Thai fantasy ensemble poster, dramatic light",
        "episode_plan": [],
    }), encoding="utf-8")

    monkeypatch.setattr("thai_novel.cli.PROJECT_ROOT", project)
    monkeypatch.setattr("thai_novel.cli.IN_DIR", in_dir)

    result = CliRunner().invoke(app, ["validate", "ep0"])

    assert result.exit_code == 0
    assert "Story bible valid" in result.output
