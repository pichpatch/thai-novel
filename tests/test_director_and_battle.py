"""
Director's reasoning-aware battle resolution + holy items + crisis injection.

Critical recent additions:
  - battle.resolve uses wits + intent_quality + holy_item_active
  - battle outcome includes a 'rationale' string
  - _score_intent_quality penalizes anti-quirk decisions (e.g. Anan + assassination)
  - economy.advance_world_state guarantees a forced crisis when no major event
"""
from __future__ import annotations

import random

import pytest

pytest.importorskip("simulation.world")


# ── Battle resolution ──────────────────────────────────────────────────────


def test_battle_resolve_returns_rationale():
    """Director must write a rationale string for every battle."""
    from simulation.rules.battle import resolve, SideInput

    rng = random.Random(42)
    attacker = SideInput(
        name="north", troops=30000, general_stat=8, general_wits=9,
        general_id="03_kanok", terrain_bonus=0, surprise=False,
        morale=70, intent_quality=0.8, holy_item_active=False,
    )
    defender = SideInput(
        name="west", troops=10000, general_stat=6, general_wits=7,
        general_id="25_aroon", terrain_bonus=4, surprise=False,
        morale=60, intent_quality=0.5, holy_item_active=False,
    )
    outcome = resolve(attacker, defender, rng)
    assert "winner" in outcome
    assert "rationale" in outcome
    assert outcome["rationale"].startswith("Director's judgment:")
    assert outcome["winner"] in ("north", "west")


def test_battle_wits_advantage_helps():
    """Higher wits should statistically improve the win rate."""
    from simulation.rules.battle import resolve, SideInput

    def run(att_wits, def_wits, trials=200):
        rng = random.Random(0)
        wins = 0
        for _ in range(trials):
            att = SideInput(name="A", troops=15000, general_stat=6, general_wits=att_wits,
                            terrain_bonus=0, surprise=False, morale=60, intent_quality=0.5)
            df = SideInput(name="B", troops=15000, general_stat=6, general_wits=def_wits,
                           terrain_bonus=0, surprise=False, morale=60, intent_quality=0.5)
            if resolve(att, df, rng)["winner"] == "A":
                wins += 1
        return wins / trials

    smart = run(att_wits=10, def_wits=3)
    dumb  = run(att_wits=3, def_wits=10)
    assert smart > dumb + 0.1, f"wits should matter: smart={smart:.2f}, dumb={dumb:.2f}"


def test_battle_holy_item_tilts_outcome():
    """Holy-item flag should tilt morale meaningfully."""
    from simulation.rules.battle import resolve, SideInput

    def run(attacker_has_item, trials=200):
        rng = random.Random(7)
        wins = 0
        for _ in range(trials):
            att = SideInput(name="A", troops=10000, general_stat=5, general_wits=5,
                            terrain_bonus=0, surprise=False, morale=60, intent_quality=0.5,
                            holy_item_active=attacker_has_item)
            df = SideInput(name="B", troops=10000, general_stat=5, general_wits=5,
                           terrain_bonus=0, surprise=False, morale=60, intent_quality=0.5,
                           holy_item_active=False)
            if resolve(att, df, rng)["winner"] == "A":
                wins += 1
        return wins / trials

    with_item = run(attacker_has_item=True)
    without   = run(attacker_has_item=False)
    assert with_item > without + 0.05, f"holy item must tilt: with={with_item:.2f}, without={without:.2f}"


# ── Director's intent-quality scoring ───────────────────────────────────────


def test_intent_score_penalizes_anti_quirk():
    """
    Director.score_intent_quality must penalize a decision that contradicts
    a character's decision_quirks. Classic case: Anan refusing to order
    assassinations.
    """
    from simulation.director import _score_intent_quality
    from simulation.agents import Decision

    anan = {
        "id": "21_anan",
        "stats": {"diplomacy": 7, "battle": 5, "espionage": 4},
        "decision_quirks": [
            "Cannot order an assassination — has refused twice when Khongtham proposed it"
        ],
        "decision_heuristics": ["Listen to Khongtham; trust the brotherhood"],
    }
    diplomacy_dec = Decision(
        character_id="21_anan", action_type="diplomacy",
        target=None, intent="propose alliance", expected_outcome="signed",
    )
    assassin_dec = Decision(
        character_id="21_anan", action_type="assassination",
        target="01_suriyan", intent="kill the rival", expected_outcome="dead",
    )
    s_good = _score_intent_quality(anan, diplomacy_dec)
    s_bad  = _score_intent_quality(anan, assassin_dec)
    assert s_good > s_bad, f"diplomacy ({s_good}) must score higher than assassination ({s_bad})"
    assert s_bad < 0.4, "assassination violates Anan's quirk → low score"


def test_intent_score_bounded_0_to_1():
    """Score must always live in [0, 1]."""
    from simulation.director import _score_intent_quality
    from simulation.agents import Decision

    char = {"id": "x", "stats": {"battle": 10}, "decision_quirks": [], "decision_heuristics": []}
    dec = Decision(character_id="x", action_type="command_battle", intent="i", expected_outcome="o")
    s = _score_intent_quality(char, dec)
    assert 0.0 <= s <= 1.0


def test_intent_score_no_decision_returns_neutral():
    from simulation.director import _score_intent_quality
    s = _score_intent_quality({}, None)
    assert s == 0.5


# ── Forced crisis injection ─────────────────────────────────────────────────


def test_world_agent_injects_crisis_when_quiet():
    """
    User requirement: every episode must have at least one significant event so
    the people-carers have something to respond to. World Agent forces a
    crisis in the least-stable kingdom when nothing major fires.
    """
    from simulation.world import load_state
    from simulation.rules import economy

    # Load the initial state from disk (uses the real ep00 file)
    state = load_state("world/state_main_ep00.json")

    # Use a seeded RNG to make the test deterministic
    rng = random.Random(12345)
    _state, events = economy.advance_world_state(state, rng=rng)

    # Either a random event fired, or a forced crisis was injected
    forced = [e for e in events if e.get("outcome", {}).get("forced")]
    major = [
        e for e in events
        if e.get("outcome", {}).get("event") in {
            "drought_north", "drought_south", "flood_south", "fire_capital",
            "barbarian_raid", "slave_uprising", "comet_sighted", "rumor_realm",
        }
    ]
    assert forced or major, "every episode must produce at least one major event"


def test_forced_crisis_targets_least_stable_kingdom():
    """
    The forced-crisis path picks the kingdom with the lowest stability.
    East starts at stability=40, the lowest, so it should be most often the target.
    """
    from simulation.world import load_state
    from simulation.rules import economy

    # Run several episodes; track how many forced crises landed on east
    east_forced_count = 0
    total_forced = 0
    for seed in range(50):
        state = load_state("world/state_main_ep00.json")
        rng = random.Random(seed)
        _s, events = economy.advance_world_state(state, rng=rng)
        for e in events:
            out = e.get("outcome", {})
            if out.get("forced"):
                total_forced += 1
                if out.get("kingdom") == "east":
                    east_forced_count += 1

    if total_forced > 0:
        share = east_forced_count / total_forced
        # East starts least stable so should dominate forced crises
        assert share > 0.5, (
            f"east should dominate forced crises (got {share:.0%})"
        )
