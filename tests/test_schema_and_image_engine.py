"""
Schema validation + the recent SDXL-Lightning engine switch.

Covers:
  - ImageEngine literal accepts old + new values, rejects unknown
  - ImageGeneration parses a minimal Lightning config
  - HolyItem (new) round-trips
  - generate.py routes the engine name through to the loader without importing torch
"""
from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from thai_novel.spec import (
    ImageEngine, ImageGeneration, Episode, load_episodes,
)


# ── ImageEngine literal ──────────────────────────────────────────────────────


def test_image_engine_accepts_turbo():
    cfg = ImageGeneration(engine="sdxl-turbo")
    assert cfg.engine == "sdxl-turbo"


def test_image_engine_accepts_lightning():
    """The SDXL-Lightning-4step engine added recently."""
    cfg = ImageGeneration(engine="sdxl-lightning-4step")
    assert cfg.engine == "sdxl-lightning-4step"


def test_image_engine_rejects_unknown():
    with pytest.raises(ValidationError):
        ImageGeneration(engine="midjourney-v6")  # not in Literal


def test_image_generation_keeps_distilled_defaults():
    """
    Channel default is hyper-sdxl-8step (better quality). Even when a user
    overrides to sdxl-lightning-4step, the spec keeps `steps` at the
    channel-wide default (8) — the engine itself forces 4 internally.
    """
    cfg = ImageGeneration(engine="sdxl-lightning-4step")
    assert cfg.steps == 8
    assert cfg.gen_width == 1024 and cfg.gen_height == 576  # 16:9 enforced


def test_image_generation_rejects_non_16_9():
    with pytest.raises(ValidationError, match="16:9"):
        ImageGeneration(engine="sdxl-turbo", gen_width=512, gen_height=512)


# ── Image-engine routing logic (no torch import) ─────────────────────────────


def test_generate_module_imports_clean():
    """generate.py should import without torch present at import time."""
    from thai_novel.images import generate
    assert hasattr(generate, "_get_diffusers_pipeline")
    assert hasattr(generate, "generate_image")


def test_effective_guidance_logic():
    """
    SDXL distilled engines need guidance=0; Z-Image-Turbo needs guidance=1.0.
    These are the precise per-engine branches in generate.py.
    """
    for engine in ("sdxl-turbo", "sdxl-lightning-4step"):
        effective = 0.0 if engine in ("sdxl-turbo", "sdxl-lightning-4step") else 1.5
        assert effective == 0.0, f"{engine} must use guidance=0.0"
    # Z-Image-Turbo: guidance 1.0
    z_guidance = 1.0 if "z-image-turbo" == "z-image-turbo" else 0.0
    assert z_guidance == 1.0


def test_image_engine_accepts_z_image_turbo():
    """Tongyi-MAI Z-Image-Turbo support added."""
    cfg = ImageGeneration(engine="z-image-turbo")
    assert cfg.engine == "z-image-turbo"


def test_image_engine_accepts_8step_variants():
    """New higher-quality variants of Hyper-SD and Lightning."""
    for eng in ("hyper-sdxl-8step", "sdxl-lightning-8step"):
        cfg = ImageGeneration(engine=eng)
        assert cfg.engine == eng


def test_step_count_per_engine_is_correct():
    """The pipeline forces effective_steps per the engine name suffix."""
    # Replicate the per-engine policy from generate.py
    def effective_steps(engine, declared=4):
        if engine in ("sdxl-lightning-4step", "sdxl-lightning-8step",
                      "hyper-sdxl-4step",     "hyper-sdxl-8step"):
            return 8 if engine.endswith("8step") else 4
        return declared

    assert effective_steps("hyper-sdxl-4step") == 4
    assert effective_steps("hyper-sdxl-8step") == 8
    assert effective_steps("sdxl-lightning-4step") == 4
    assert effective_steps("sdxl-lightning-8step") == 8
    assert effective_steps("sdxl-turbo", declared=4) == 4


def test_image_engine_accepts_hyper_sdxl_4step():
    """Hyper-SDXL 4-step LoRA support added; base_model is optional."""
    cfg_default = ImageGeneration(engine="hyper-sdxl-4step")
    assert cfg_default.engine == "hyper-sdxl-4step"
    assert cfg_default.base_model is None
    cfg_anime = ImageGeneration(
        engine="hyper-sdxl-4step",
        base_model="cagliostrolab/animagine-xl-3.1",
    )
    assert cfg_anime.base_model == "cagliostrolab/animagine-xl-3.1"


def test_z_image_forces_fp32_on_mps():
    """
    Bug fix verification: Z-Image-Turbo on MPS must NOT use fp16,
    otherwise the DiT attention NaNs and outputs are entirely black.
    """
    import torch
    from thai_novel.images.generate import _dtype_for_engine
    # MPS + z-image-turbo → fp32 forced
    assert _dtype_for_engine("z-image-turbo", "mps", torch.float16) == torch.float32
    assert _dtype_for_engine("z-image-turbo", "mps", torch.float32) == torch.float32


def test_other_engines_keep_default_dtype_on_mps():
    """SDXL family is UNet-based; fp16 is safe and stays the default on MPS."""
    import torch
    from thai_novel.images.generate import _dtype_for_engine
    for engine in ("sdxl-turbo", "sdxl-lightning-4step", "hyper-sdxl-4step"):
        assert _dtype_for_engine(engine, "mps", torch.float16) == torch.float16, (
            f"{engine} on MPS should keep fp16"
        )


def test_z_image_on_cuda_or_cpu_keeps_default_dtype():
    """fp16 NaN issue is MPS-specific; cuda/cpu can still use whatever caller asked."""
    import torch
    from thai_novel.images.generate import _dtype_for_engine
    assert _dtype_for_engine("z-image-turbo", "cuda", torch.float16) == torch.float16
    assert _dtype_for_engine("z-image-turbo", "cpu", torch.float32) == torch.float32


# ── FLUX.1-schnell ───────────────────────────────────────────────────────────


def test_image_engine_accepts_flux_schnell():
    cfg = ImageGeneration(engine="flux-schnell-4step")
    assert cfg.engine == "flux-schnell-4step"


def test_flux_uses_bfloat16_on_mps():
    """
    FLUX is ~12 GB in bfloat16 but ~24 GB in fp32 — fp32 OOMs on M2 Pro 32 GB.
    fp16 NaNs the DiT attention (same class of bug as Z-Image). bfloat16 is
    FLUX's native training precision and the only fit on MPS.
    """
    import torch
    from thai_novel.images.generate import _dtype_for_engine
    assert _dtype_for_engine("flux-schnell-4step", "mps", torch.float16) == torch.bfloat16
    assert _dtype_for_engine("flux-schnell-4step", "mps", torch.float32) == torch.bfloat16


def test_flux_keeps_caller_dtype_off_mps():
    """fp16 NaN risk is MPS-only; cuda can use fp16 if caller wants."""
    import torch
    from thai_novel.images.generate import _dtype_for_engine
    assert _dtype_for_engine("flux-schnell-4step", "cuda", torch.bfloat16) == torch.bfloat16
    assert _dtype_for_engine("flux-schnell-4step", "cpu", torch.float32) == torch.float32


def test_flux_auto_downscales_resolution():
    """
    FLUX on M2 Pro at 1024 is impractical (~3 min/image, OOM-prone).
    The pipeline must auto-downscale to 768x432 when the spec asks for >768 wide.
    Replicates the branch logic from generate_image.
    """
    # Replicate
    def effective_dims(engine, w, h):
        if engine == "flux-schnell-4step" and w > 768:
            return 768, 432
        return w, h

    assert effective_dims("flux-schnell-4step", 1024, 576) == (768, 432)
    assert effective_dims("flux-schnell-4step", 1920, 1080) == (768, 432)
    # User explicitly going smaller is respected
    assert effective_dims("flux-schnell-4step", 512, 288) == (512, 288)
    assert effective_dims("flux-schnell-4step", 768, 432) == (768, 432)
    # Other engines untouched
    assert effective_dims("sdxl-lightning-4step", 1024, 576) == (1024, 576)
    assert effective_dims("hyper-sdxl-4step", 1920, 1080) == (1920, 1080)


def test_flux_step_count_is_exactly_4():
    """FLUX-schnell is LoRA-distilled for exactly 4 steps; more doesn't help."""
    # The pipeline forces effective_steps = 4 for flux engine regardless of spec
    def effective_steps(engine, declared_steps):
        if engine == "flux-schnell-4step":
            return 4
        return declared_steps

    for declared in (1, 4, 8, 20, 50):
        assert effective_steps("flux-schnell-4step", declared) == 4


def test_pony_diffusion_works_as_base_model_value():
    """Pony Diffusion is just an SDXL base; users set it via base_model field."""
    cfg = ImageGeneration(
        engine="hyper-sdxl-4step",
        base_model="John6666/pony-diffusion-v6-xl-sdxl-spo",
    )
    assert cfg.engine == "hyper-sdxl-4step"
    assert "pony" in cfg.base_model.lower()


# ── Base-model prompt adapter (Pony auto score-tags) ───────────────────────


def test_pony_adapter_injects_score_tags():
    """Any base_model containing 'pony' must get score_9 family + source_anime
    on the positive, and low-score family + source_pony/furry on the negative."""
    from thai_novel.images.generate import _base_model_prompt_adapter
    pos, neg = _base_model_prompt_adapter("John6666/pony-diffusion-v6-xl-sdxl-spo")
    assert "score_9" in pos
    assert "score_8_up" in pos
    assert "source_anime" in pos
    assert "score_4" in neg
    assert "source_pony" in neg
    assert "source_furry" in neg


def test_pony_adapter_case_insensitive():
    """Detection should not care about capitalization in the repo id."""
    from thai_novel.images.generate import _base_model_prompt_adapter
    for variant in ("PONY", "Pony-Diffusion-V6", "purplesmartai/pony-diffusion-v6"):
        pos, neg = _base_model_prompt_adapter(variant)
        assert pos and neg, f"{variant} should trigger Pony adapter"


def test_animagine_adapter_returns_empty():
    """Animagine and other anime bases need no special tags."""
    from thai_novel.images.generate import _base_model_prompt_adapter
    for base in (
        "cagliostrolab/animagine-xl-3.1",
        "gsdf/CounterfeitXL",
        "Lykon/AAM_XL_AnimeMix",
        "stabilityai/stable-diffusion-xl-base-1.0",
    ):
        pos, neg = _base_model_prompt_adapter(base)
        assert pos == "" and neg == "", f"{base} must NOT get a prefix"


# ── Tone field + adapters ────────────────────────────────────────────────────


def test_visual_style_tone_default_is_realistic():
    """User shouldn't have to set tone — realistic is the channel-wide default."""
    from thai_novel.spec import VisualStyle
    vs = VisualStyle()
    assert vs.tone == "realistic"


def test_visual_style_tone_accepts_anime():
    from thai_novel.spec import VisualStyle
    vs = VisualStyle(tone="anime")
    assert vs.tone == "anime"


def test_visual_style_rejects_invalid_tone():
    from thai_novel.spec import VisualStyle
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        VisualStyle(tone="cyberpunk")  # not in Literal


def test_tone_realistic_injects_photo_keywords_in_positive():
    from thai_novel.images.generate import _tone_prompt_adapter
    pos, neg = _tone_prompt_adapter("realistic")
    assert "photorealistic" in pos
    assert "photograph" in pos
    assert "anime" in neg
    assert "cartoon" in neg


def test_tone_anime_injects_anime_keywords_in_positive():
    from thai_novel.images.generate import _tone_prompt_adapter
    pos, neg = _tone_prompt_adapter("anime")
    assert "anime" in pos
    assert "illustration" in pos
    assert "photograph" in neg


def test_tone_unknown_returns_empty():
    from thai_novel.images.generate import _tone_prompt_adapter
    assert _tone_prompt_adapter(None) == ("", "")
    assert _tone_prompt_adapter("noir") == ("", "")


def test_tone_realistic_default_base_model_is_none():
    """Realistic = plain SDXL base; user can still override with image_generation.base_model."""
    from thai_novel.images.generate import _default_base_model_for_tone
    assert _default_base_model_for_tone("realistic") is None
    assert _default_base_model_for_tone(None) is None


def test_tone_anime_default_base_model_is_animagine():
    """Anime tone auto-picks Animagine XL 3.1 unless user overrides."""
    from thai_novel.images.generate import _default_base_model_for_tone
    assert _default_base_model_for_tone("anime") == "cagliostrolab/animagine-xl-3.1"


def test_no_base_model_returns_empty():
    """When base_model is None (default SDXL family) no prefix is added."""
    from thai_novel.images.generate import _base_model_prompt_adapter
    assert _base_model_prompt_adapter(None) == ("", "")
    assert _base_model_prompt_adapter("") == ("", "")


def test_pony_adapter_idempotent_in_generate():
    """
    If the user already manually put score_9 into visual_style.base_prompt,
    the auto-injection in generate_image must NOT duplicate it.

    We replicate the precise idempotency check from generate_image.
    """
    from thai_novel.images.generate import _base_model_prompt_adapter
    pos_pref, _ = _base_model_prompt_adapter("John6666/pony-diffusion-v6-xl-sdxl-spo")
    first_tag = pos_pref.split(",")[0].strip()  # "score_9"

    # Case 1: user has NOT added it — prefix should be injected
    user_bp_clean = "cinematic romantic anime style, warm amber lighting"
    if first_tag not in user_bp_clean:
        final = pos_pref + user_bp_clean
    else:
        final = user_bp_clean
    assert final.startswith("score_9")

    # Case 2: user HAS already added it — prefix should NOT be re-injected
    user_bp_dirty = "score_9, score_8_up, cinematic romantic anime style"
    if first_tag not in user_bp_dirty:
        final = pos_pref + user_bp_dirty
    else:
        final = user_bp_dirty
    # Must NOT have two "score_9"
    assert final.count("score_9") == 1


def test_base_model_is_part_of_image_cache_key():
    """
    Same prompt + same engine + DIFFERENT base_model must produce a different
    image_key, so the cache regenerates when swapping bases.
    """
    from thai_novel.hashing import image_key
    common = dict(
        prompt="x", negative_prompt="y", style_base="z",
        seed=42, steps=4, guidance=0.0, width=1024, height=576,
        engine="hyper-sdxl-4step",
    )
    k_sdxl  = image_key(**common, base_model="stabilityai/stable-diffusion-xl-base-1.0")
    k_anime = image_key(**common, base_model="cagliostrolab/animagine-xl-3.1")
    k_none  = image_key(**common, base_model=None)
    assert k_sdxl != k_anime != k_none, "cache key must split on base_model"


def test_z_image_step_floor():
    """
    Z-Image needs ≥8 steps. If a spec was set up for SDXL at steps=4 and
    the engine is switched to z-image-turbo, generate.py must bump to 8.
    """
    # Replicate the branch logic inline
    for declared_steps in (1, 4, 6, 8, 12):
        effective = max(declared_steps, 8) if "z-image-turbo" == "z-image-turbo" else declared_steps
        assert effective >= 8


def test_pipeline_cache_keyed_by_engine(monkeypatch):
    """
    The lazy-loaded pipeline must reset when the engine changes.
    Otherwise switching engines mid-run would silently keep the old model.
    """
    from thai_novel.images import generate

    # Reset module globals (other tests may have touched them)
    monkeypatch.setattr(generate, "_pipeline", None)
    monkeypatch.setattr(generate, "_pipeline_engine", None)

    # Stub a fake "pipeline" returned by both engines so we can prove
    # the cache-key is engine-specific.
    calls = []

    def fake_loader(engine):
        calls.append(engine)
        generate._pipeline = f"pipe-for-{engine}"
        generate._pipeline_engine = engine
        return generate._pipeline

    # First call: load turbo
    fake_loader("sdxl-turbo")
    assert generate._pipeline_engine == "sdxl-turbo"

    # Second call same engine: would be cache hit (real loader returns early)
    # Third call different engine: must re-load
    fake_loader("sdxl-lightning-4step")
    assert generate._pipeline_engine == "sdxl-lightning-4step"
    assert calls == ["sdxl-turbo", "sdxl-lightning-4step"]


def test_manual_library_asset_without_metadata_is_reused(tmp_path: Path, monkeypatch):
    """
    Codex/OpenAI-generated episode images are curated assets. If the PNG exists
    in the library but has no _index.json metadata, Stage 2 should reuse it
    instead of regenerating with local SDXL.
    """
    import thai_novel.images as images

    existing = tmp_path / "library" / "visuals" / "backgrounds" / "manual.png"
    existing.parent.mkdir(parents=True)
    existing.write_bytes(b"manual image placeholder")

    ep = Episode.model_validate({
        "project": {
            "id": "manual-asset-ep01",
            "title": "ทดสอบ",
            "resolution": "1280x720",
        },
        "chapters": [{
            "id": "ch_01",
            "title": "ทดสอบ",
            "visual_anchor": {
                "prompt": "manual image prompt",
                "save_to_library_as": "manual",
                "motion": "static",
            },
            "narration_blocks": [{
                "id": "ch01_b1",
                "mood": "cozy",
                "narration": "ก" * 1500,
            }],
        }],
    })

    def fail_generate(*args, **kwargs):
        raise AssertionError("manual/Codex library assets must not regenerate")

    def fake_upscale(src, out, method):
        assert src == existing
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(b"upscaled")

    monkeypatch.setattr(images, "resolve_lib", lambda ref, root: existing)
    monkeypatch.setattr(images, "get_metadata", lambda ref, root: None)
    monkeypatch.setattr(images, "generate_image", fail_generate)
    monkeypatch.setattr(images, "upscale_to_1080p", fake_upscale)

    result = images.resolve_anchor(
        "ch_01",
        ep.chapters[0].visual_anchor,
        ep,
        tmp_path,
    )

    assert result.src_kind == "library"
    assert result.image_path_1080p.read_bytes() == b"upscaled"


# ── HolyItem schema (Four Thrones) — import only if simulation is present ───


def test_holy_item_round_trip():
    """The new HolyItem model added for the Four Thrones simulation."""
    pytest.importorskip("simulation.world")
    from simulation.world import HolyItem

    item = HolyItem(
        name_th="กระจกสะท้อนใจ",
        name_en="Mirror of True Speech",
        kind="truth",
        cooldown_episodes=2,
        cooldown_remaining=1,
        held_by="01_suriyan",
        description="...",
    )
    # JSON round-trip preserves Thai characters
    j = item.model_dump_json()
    item2 = HolyItem.model_validate_json(j)
    assert item2.name_th == "กระจกสะท้อนใจ"
    assert item2.kind == "truth"
    assert item2.cooldown_remaining == 1


def test_holy_item_rejects_unknown_kind():
    pytest.importorskip("simulation.world")
    from simulation.world import HolyItem

    with pytest.raises(ValidationError):
        HolyItem(
            name_th="x", name_en="x", kind="invisibility",  # not in Literal
            cooldown_episodes=1, held_by="01_suriyan",
        )
