"""
Character reference system — schema, pipeline routing, clean handling, template.

Three layers tested:
  1. Pydantic schema accepts the new fields (id, name_th, appearance_th,
     reference_image on CharacterSpec; characters on VisualAnchor).
  2. The canonical template (in/template.example.json) demonstrates the new
     fields so writers see them by example.
  3. Library resolution of `library://characters/<name>` works correctly.

Pipeline integration (IP-Adapter actually loading weights, conditioning the
diffusion model, etc.) is NOT covered here — that requires the real torch +
diffusers + ~700 MB weights and a render. Schema/wiring tests are enough to
catch the kinds of regressions that prevent the system from working at all.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from thai_novel.spec import (
    CharacterSpec, VisualAnchor, Episode,
)


# ── CharacterSpec — new fields ──────────────────────────────────────────────


def test_character_spec_accepts_id_field():
    """id is the slug used by visual_anchor.characters."""
    c = CharacterSpec(id="thana", appearance="Thai man")
    assert c.id == "thana"


def test_character_spec_id_is_optional():
    """Backward compat — old episode JSONs without id still parse."""
    c = CharacterSpec(appearance="Thai man")
    assert c.id is None


def test_character_spec_accepts_name_th_and_appearance_th():
    """Bilingual fields for docs that need Thai descriptions."""
    c = CharacterSpec(
        id="thana",
        name="Thana",
        name_th="ธน",
        appearance="Thai man",
        appearance_th="ชายไทย",
    )
    assert c.name_th == "ธน"
    assert c.appearance_th == "ชายไทย"


def test_character_spec_accepts_reference_image():
    """library:// URI that points at the canonical face/look reference."""
    c = CharacterSpec(
        id="thana", appearance="Thai man",
        reference_image="library://characters/thana",
    )
    assert c.reference_image == "library://characters/thana"


def test_character_spec_reference_image_is_optional():
    c = CharacterSpec(id="thana", appearance="Thai man")
    assert c.reference_image is None


# ── VisualAnchor — new `characters` list ───────────────────────────────────


def test_visual_anchor_accepts_characters_list():
    a = VisualAnchor(prompt="a scene", characters=["thana", "phim"])
    assert a.characters == ["thana", "phim"]


def test_visual_anchor_characters_defaults_to_empty():
    """Old episode JSONs without `characters` still parse — backward compat."""
    a = VisualAnchor(prompt="a scene")
    assert a.characters == []


def test_visual_anchor_characters_capped_at_4():
    """IP-Adapter degrades beyond 4 simultaneous refs — schema enforces."""
    with pytest.raises(ValidationError, match="at most 4"):
        VisualAnchor(prompt="too crowded",
                     characters=["a", "b", "c", "d", "e"])


def test_visual_anchor_one_character_ok():
    """Single-character close-ups are the common case — explicit test."""
    a = VisualAnchor(prompt="closeup of thana", characters=["thana"])
    assert a.characters == ["thana"]


# ── Template (in/template.example.json) — must demonstrate the new fields ──


def test_template_parses_with_new_fields():
    """Canonical template must round-trip through Pydantic."""
    d = json.loads(Path("in/template.example.json").read_text(encoding="utf-8"))
    ep_dict = d[0] if isinstance(d, list) else d
    ep = Episode.model_validate(ep_dict)
    assert isinstance(ep, Episode)


def test_template_demonstrates_character_id_field():
    """
    Template should set `id` on both leads so writers can see the pattern.
    If this fails, the template was reverted and writers won't know the field exists.
    """
    d = json.loads(Path("in/template.example.json").read_text(encoding="utf-8"))
    ep_dict = d[0] if isinstance(d, list) else d
    chars = ep_dict["characters"]
    assert chars["male_lead"].get("id") == "male_lead", \
        "template's male_lead must have explicit id"
    assert chars["female_lead"].get("id") == "female_lead", \
        "template's female_lead must have explicit id"


def test_template_first_chapter_demonstrates_characters_list():
    """Template's first chapter visual_anchor should show how to list characters."""
    d = json.loads(Path("in/template.example.json").read_text(encoding="utf-8"))
    ep_dict = d[0] if isinstance(d, list) else d
    first_va = ep_dict["chapters"][0]["visual_anchor"]
    assert "characters" in first_va, "template chapter should demo the characters field"
    assert isinstance(first_va["characters"], list)
    assert len(first_va["characters"]) > 0


# ── Library resolution of character references ─────────────────────────────


def test_library_resolves_characters_uri(tmp_path):
    """library://characters/<name> resolves under library/visuals/characters/."""
    from thai_novel.images.library import resolve, parse_ref

    # Create a fake library tree
    (tmp_path / "visuals" / "characters").mkdir(parents=True)
    (tmp_path / "visuals" / "characters" / "thana.png").write_bytes(b"\x89PNG\r\n")

    kind, name = parse_ref("library://characters/thana")
    assert kind == "characters" and name == "thana"

    p = resolve("library://characters/thana", tmp_path)
    assert p is not None
    assert p.name == "thana.png"


def test_library_resolves_to_none_when_missing(tmp_path):
    """Missing reference image returns None — pipeline must skip silently."""
    from thai_novel.images.library import resolve
    (tmp_path / "visuals" / "characters").mkdir(parents=True)
    p = resolve("library://characters/missing", tmp_path)
    assert p is None


# ── Pipeline helper: _resolve_character_references ──────────────────────────


def test_resolve_character_references_returns_empty_for_no_ids():
    """No ids → no refs → IP-Adapter not engaged (silent no-op)."""
    from thai_novel.images.generate import _resolve_character_references
    out = _resolve_character_references([], {}, Path("/tmp"))
    assert out == []


def test_resolve_character_references_skips_missing_files(tmp_path):
    """
    Refs that point at missing files are silently skipped — pipeline still
    runs without IP-Adapter for that scene rather than crashing the render.
    """
    from thai_novel.images.generate import _resolve_character_references
    ep_chars = {
        "male_lead": {
            "id": "thana",
            "appearance": "Thai man",
            "reference_image": "library://characters/thana",  # file doesn't exist
        }
    }
    (tmp_path / "visuals" / "characters").mkdir(parents=True)  # empty dir
    refs = _resolve_character_references(["thana"], ep_chars, tmp_path)
    assert refs == []


def test_resolve_character_references_falls_back_to_slot_id(tmp_path):
    """
    A character without explicit `id` should match by slot-key as a fallback.
    This preserves backward compat for episodes that haven't added id yet.
    """
    from PIL import Image
    from thai_novel.images.generate import _resolve_character_references

    # Set up a real PNG so resolve succeeds
    char_dir = tmp_path / "visuals" / "characters"
    char_dir.mkdir(parents=True)
    Image.new("RGB", (10, 10), (100, 100, 100)).save(char_dir / "male_lead.png")

    ep_chars = {
        "male_lead": {
            "appearance": "Thai man",
            "reference_image": "library://characters/male_lead",
            # NOTE: no explicit `id`
        }
    }
    refs = _resolve_character_references(["male_lead"], ep_chars, tmp_path)
    assert len(refs) == 1
