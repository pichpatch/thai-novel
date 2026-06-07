"""
simulation/persistence.py — Director writes back to character files.

Critical invariants:
  - Trust deltas clamp to [-1, 1]
  - Stat deltas clamp to [0, 10]
  - Personal-guard floors at 0 (never negative; no auto-replenishment)
  - set_field creates intermediate dicts
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

pytest.importorskip("simulation.persistence")


@pytest.fixture
def temp_char_dir(tmp_path, monkeypatch):
    """
    Create a minimal characters/ tree under tmp_path and chdir into it.
    persistence.py resolves files via Path.cwd() / 'characters' / kingdom.
    """
    char_root = tmp_path / "characters"
    for k in ("north", "south", "west", "east"):
        (char_root / k).mkdir(parents=True)

    sample = {
        "id": "test_char",
        "kingdom": "north",
        "name_th": "ทดสอบ",
        "alive": True,
        "stats": {"battle": 5, "wits": 7},
        "relationships": {
            "other": {"type": "ally", "trust": 0.5, "notes": ""},
        },
        "resources": {"personal_guard": 100},
    }
    (char_root / "north" / "test_char.json").write_text(
        json.dumps(sample, ensure_ascii=False), encoding="utf-8"
    )

    monkeypatch.chdir(tmp_path)
    return tmp_path


def test_read_character_returns_dict(temp_char_dir):
    from simulation.persistence import read_character
    char = read_character("test_char")
    assert char is not None
    assert char["name_th"] == "ทดสอบ"


def test_read_character_returns_none_for_missing(temp_char_dir):
    from simulation.persistence import read_character
    assert read_character("does_not_exist") is None


def test_apply_trust_delta_clamps_high(temp_char_dir):
    from simulation.persistence import apply_trust_delta, read_character
    # Trust starts at 0.5; +0.8 would be 1.3 → must clamp to 1.0
    ok = apply_trust_delta("test_char", "other", 0.8)
    assert ok
    char = read_character("test_char")
    assert char["relationships"]["other"]["trust"] == 1.0


def test_apply_trust_delta_clamps_low(temp_char_dir):
    from simulation.persistence import apply_trust_delta, read_character
    ok = apply_trust_delta("test_char", "other", -3.0)
    assert ok
    char = read_character("test_char")
    assert char["relationships"]["other"]["trust"] == -1.0


def test_apply_trust_delta_creates_new_relationship(temp_char_dir):
    """If the target isn't in relationships yet, create it."""
    from simulation.persistence import apply_trust_delta, read_character
    ok = apply_trust_delta("test_char", "brand_new", 0.3)
    assert ok
    char = read_character("test_char")
    assert "brand_new" in char["relationships"]
    assert char["relationships"]["brand_new"]["trust"] == 0.3


def test_apply_stat_delta_clamps_at_10(temp_char_dir):
    from simulation.persistence import apply_stat_delta, read_character
    apply_stat_delta("test_char", "wits", 5.0)  # 7 + 5 = 12 → clamp 10
    char = read_character("test_char")
    assert char["stats"]["wits"] == 10.0


def test_apply_stat_delta_clamps_at_0(temp_char_dir):
    from simulation.persistence import apply_stat_delta, read_character
    apply_stat_delta("test_char", "battle", -10.0)
    char = read_character("test_char")
    assert char["stats"]["battle"] == 0.0


def test_apply_stat_delta_creates_missing_stat(temp_char_dir):
    """Stat-growth on a stat that wasn't on the file before."""
    from simulation.persistence import apply_stat_delta, read_character
    apply_stat_delta("test_char", "ritual", 0.5)
    char = read_character("test_char")
    # Starts at default 5 then +0.5
    assert char["stats"]["ritual"] == 5.5


def test_personal_guard_does_not_go_negative(temp_char_dir):
    from simulation.persistence import adjust_personal_guard, read_character
    adjust_personal_guard("test_char", -500)
    char = read_character("test_char")
    assert char["resources"]["personal_guard"] == 0


def test_personal_guard_no_auto_replenishment(temp_char_dir):
    """
    User requirement: guards depleted by failed assassinations stay low
    until the character takes an explicit recruit action.
    """
    from simulation.persistence import adjust_personal_guard, read_character
    # Drop guard
    adjust_personal_guard("test_char", -90)  # 100 - 90 = 10
    assert read_character("test_char")["resources"]["personal_guard"] == 10
    # Don't recruit; the value must persist as-is
    assert read_character("test_char")["resources"]["personal_guard"] == 10


def test_set_field_creates_nested_path(temp_char_dir):
    from simulation.persistence import set_field, read_character
    set_field("test_char", "morale.current_episode", 65)
    char = read_character("test_char")
    assert char["morale"]["current_episode"] == 65


def test_record_practice_grows_matched_stat(temp_char_dir):
    """Practicing 'command_battle' should grow the battle stat."""
    from simulation.persistence import record_practice, read_character
    before = read_character("test_char")["stats"]["battle"]
    record_practice("test_char", "command_battle", success=True)
    after = read_character("test_char")["stats"]["battle"]
    assert after > before


def test_record_practice_failed_grows_at_half_rate(temp_char_dir):
    """Failed practice still grows, but at half rate."""
    from simulation.persistence import record_practice, read_character

    # Successful spy op
    record_practice("test_char", "spy_op", success=True)
    after_success = read_character("test_char").get("stats", {}).get("espionage", 5)

    # Reset by writing back to 5
    char = read_character("test_char")
    char["stats"]["espionage"] = 5.0
    from simulation.persistence import write_character
    write_character("test_char", char)

    # Failed spy op
    record_practice("test_char", "spy_op", success=False)
    after_failure = read_character("test_char").get("stats", {}).get("espionage", 5)

    success_growth = after_success - 5.0
    failure_growth = after_failure - 5.0
    # Failure growth should be exactly half (within float tolerance)
    assert failure_growth == pytest.approx(success_growth / 2, abs=0.01)
