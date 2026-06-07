"""
Storyteller — the 4000-char floor user requirement.

The storyteller must guarantee at least 4000 Thai narration chars total
per episode. If the natural beats produce less, it pads from a filler pool
without exceeding the per-block 3000-char ceiling.
"""
from __future__ import annotations

import pytest

pytest.importorskip("simulation.storyteller")


def test_min_chars_floor_constant():
    from simulation import storyteller as st
    assert st.EPISODE_MIN_CHARS == 4000


def test_enforce_min_chars_pads_short_episode():
    """A near-empty chapter set should grow to ≥4000 chars."""
    from simulation.storyteller import _enforce_min_chars

    chapters = [
        {
            "id": "ch_01",
            "title": "ทดสอบ",
            "show_title_card": False,
            "visual_anchor": {"prompt": "x", "save_to_library_as": "x", "motion": "static"},
            "narration_blocks": [{
                "id": "ch01_b1", "mood": "cozy", "duration_hint_sec": 60,
                "narration": "ครั้งหนึ่ง...",  # very short
            }],
        }
    ]
    padded = _enforce_min_chars(chapters, 4000)
    total = sum(
        len(b["narration"])
        for c in padded for b in c["narration_blocks"]
    )
    assert total >= 4000, f"floor not enforced: total={total}"


def test_enforce_min_chars_respects_per_block_max():
    """No single block should exceed 3000 chars even when padding."""
    from simulation.storyteller import _enforce_min_chars

    chapters = [{
        "id": "ch_01", "title": "x", "show_title_card": False,
        "visual_anchor": {"prompt": "x", "save_to_library_as": "x", "motion": "static"},
        "narration_blocks": [{
            "id": "ch01_b1", "mood": "cozy", "duration_hint_sec": 60,
            "narration": "",
        }],
    }]
    padded = _enforce_min_chars(chapters, 4000)
    for c in padded:
        for b in c["narration_blocks"]:
            assert len(b["narration"]) <= 3000, "per-block ceiling violated"


def test_enforce_min_chars_pads_shortest_first():
    """Padding should land on the shortest block, not the longest."""
    from simulation.storyteller import _enforce_min_chars

    long_block = "ก" * 2500  # near the per-block ceiling
    short_block = "ข" * 100

    chapters = [{
        "id": "ch_01", "title": "x", "show_title_card": False,
        "visual_anchor": {"prompt": "x", "save_to_library_as": "x", "motion": "static"},
        "narration_blocks": [
            {"id": "ch01_b1", "mood": "cozy", "narration": long_block},
            {"id": "ch01_b2", "mood": "cozy", "narration": short_block},
        ],
    }]
    before_short = len(short_block)
    padded = _enforce_min_chars(chapters, 4000)
    after_short = len(padded[0]["narration_blocks"][1]["narration"])
    after_long  = len(padded[0]["narration_blocks"][0]["narration"])
    # Short block grew; long block barely touched
    assert after_short > before_short
    assert after_long < after_short + 500  # long stayed near its original


def test_enforce_min_chars_already_above_floor_no_op():
    """If we're already at floor, padding shouldn't add anything significant."""
    from simulation.storyteller import _enforce_min_chars

    chapters = [{
        "id": "ch_01", "title": "x", "show_title_card": False,
        "visual_anchor": {"prompt": "x", "save_to_library_as": "x", "motion": "static"},
        "narration_blocks": [{
            "id": "ch01_b1", "mood": "cozy",
            "narration": "ก" * 2500,
        }, {
            "id": "ch01_b2", "mood": "cozy",
            "narration": "ข" * 2500,
        }],
    }]
    before = sum(len(b["narration"]) for b in chapters[0]["narration_blocks"])
    padded = _enforce_min_chars(chapters, 4000)
    after = sum(len(b["narration"]) for b in padded[0]["narration_blocks"])
    assert before == after, "no padding needed when already over floor"
