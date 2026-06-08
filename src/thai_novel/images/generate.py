"""
SDXL Turbo image generation.

Two backends, picked at runtime based on what's importable:
  1. diffusers + MPS  (default — works on any Apple Silicon with torch)
  2. placeholder      (when torch isn't installed — generates a tasteful
                       gradient PNG with the prompt overlaid so the pipeline
                       can run end-to-end without a 6 GB download)

The diffusers path lazily downloads `stabilityai/sdxl-turbo` on first use
(~6.5 GB). It caches under ./models/diffusers-hf/.
"""

from __future__ import annotations

import logging
import os
import textwrap
from pathlib import Path

from ..hashing import image_key
from ..spec import ImageGeneration, VisualStyle

log = logging.getLogger("thai_novel.images.generate")

_pipeline = None              # lazy-init singleton
_pipeline_engine = None       # which engine the loaded pipeline is for
_pipeline_base_model = None   # which base checkpoint the pipeline is bound to


def _tone_prompt_adapter(tone: str | None) -> tuple[str, str]:
    """
    Map the high-level `visual_style.tone` to prompt prefixes.

    Realistic: pushes the model toward photographic output and explicitly
        rejects anime/cartoon/illustration in negative.
    Anime:     pushes toward anime/illustration and rejects photographic.

    Returns (positive_prefix, negative_prefix). Both empty for unknown tones.
    Pure function — testable without loading models.
    """
    if tone == "realistic":
        return (
            "cinematic photograph, photorealistic, hyperrealistic, ",
            "anime, cartoon, manga, illustration, painting, drawing, sketch, cgi, 3d render, doll-like, plastic, ",
        )
    if tone == "anime":
        return (
            "anime style, illustration, ",
            "photograph, photorealistic, 3d render, real person, ",
        )
    return "", ""


def _default_base_model_for_tone(tone: str | None) -> str | None:
    """
    When `image_generation.base_model` is unset, derive a sensible default
    from the tone. User-set base_model always wins over this default.
    """
    if tone == "anime":
        return "cagliostrolab/animagine-xl-3.1"
    # realistic / unknown → None  (= SDXL base 1.0)
    return None


def _base_model_prompt_adapter(base_model: str | None) -> tuple[str, str]:
    """
    Some base models require prompt-conditioning tokens to produce usable output.
    Return (positive_prefix, negative_prefix) to be PREPENDED to the prompts.

    Known adapters:
      - Pony Diffusion (V6 XL, etc.):
          Trained on rank-tagged data; without score tags the output is garbage.
          Positive: score_9 family + source_anime + quality words.
          Negative: low-score family + source_pony/source_furry to suppress.
      - Animagine XL, Counterfeit XL, AAM XL, etc.:
          Need no prefix; return empty strings.

    Pure function — testable without loading any model. Detection is by
    substring on the base_model repo id (case-insensitive).
    """
    if not base_model:
        return "", ""
    bm = base_model.lower()
    if "pony" in bm:
        return (
            "score_9, score_8_up, score_7_up, source_anime, masterpiece, best quality, ",
            "score_4, score_5, score_6, source_pony, source_furry, ",
        )
    return "", ""


def _dtype_for_engine(engine: str, device: str, default_dtype):
    """
    Per-engine precision policy.

    Apple Silicon MPS + fp16 + diffusion transformers (DiT) NaNs the attention
    layers → completely black output. Z-Image-Turbo is a DiT, so it must run
    in fp32 on MPS. SDXL family is UNet-based and safe in fp16.

    Pure function — easy to unit-test without loading any model.
    """
    import torch
    if engine == "z-image-turbo" and device == "mps":
        return torch.float32
    if engine == "flux-schnell-4step" and device == "mps":
        # FLUX is ~12B params — fp32 (48 GB) would OOM, fp16 NaNs the DiT.
        # bfloat16 (FLUX's native training precision, 24 GB) is the only fit.
        return torch.bfloat16
    return default_dtype


def _get_diffusers_pipeline(
    models_dir: Path,
    engine: str = "sdxl-turbo",
    base_model: str | None = None,
):
    """
    Lazy-load the image pipeline via diffusers+MPS. Cached per (engine, base_model)
    pair (switching either re-loads). Returns None if torch missing.

    Supported engines:
      - "sdxl-turbo"           : Stability's SDXL Turbo (~6.5 GB)
      - "sdxl-lightning-4step" : ByteDance Lightning 4-step UNet on SDXL base
                                 (~6.5 GB base + ~5 GB lightning UNet, first run)
      - "hyper-sdxl-4step"     : ByteDance Hyper-SD 4-step LoRA on top of any
                                 SDXL base. `base_model` selects the base
                                 (default: SDXL-base-1.0). Compatible bases:
                                   - "cagliostrolab/animagine-xl-3.1"  (anime)
                                   - "John6666/pony-diffusion-v6-xl-sdxl-spo"
                                       (Pony Diffusion V6 XL — illustration;
                                       requires special prompt tags, see docs)
                                   - "gsdf/CounterfeitXL"              (painterly)
                                   - "Lykon/AAM_XL_AnimeMix"           (soft anime)
    """
    global _pipeline, _pipeline_engine, _pipeline_base_model
    pipeline_key = (engine, base_model)
    cached_key = (_pipeline_engine, _pipeline_base_model)
    if _pipeline is not None and pipeline_key == cached_key:
        return _pipeline
    try:
        import torch
        from diffusers import AutoPipelineForText2Image
    except ImportError:
        return None

    if torch.backends.mps.is_available():
        device = "mps"
        dtype = torch.float16
    else:
        log.warning("torch.MPS not available — falling back to CPU (will be slow)")
        device = "cpu"
        dtype = torch.float32

    # Keep all HF weights inside the project (./models/diffusers-hf/)
    models_dir.mkdir(parents=True, exist_ok=True)
    os.environ["HF_HOME"] = str(models_dir / "diffusers-hf")
    os.environ.setdefault("TRANSFORMERS_OFFLINE", "0")

    if engine in ("sdxl-lightning-4step", "sdxl-lightning-8step"):
        # SDXL Lightning is a distilled UNet that drops onto the SDXL base.
        # Approach: load SDXL base, swap in the Lightning UNet weights,
        # configure the Euler scheduler with trailing timestep spacing.
        from diffusers import StableDiffusionXLPipeline, UNet2DConditionModel, EulerDiscreteScheduler
        from huggingface_hub import hf_hub_download
        from safetensors.torch import load_file

        n_steps = 8 if engine == "sdxl-lightning-8step" else 4
        log.info(f"loading sdxl-lightning-{n_steps}step (first time downloads ~11 GB; cached at ./models/)")
        base = "stabilityai/stable-diffusion-xl-base-1.0"
        repo = "ByteDance/SDXL-Lightning"
        ckpt = f"sdxl_lightning_{n_steps}step_unet.safetensors"

        unet = UNet2DConditionModel.from_config(base, subfolder="unet").to(device, dtype)
        unet.load_state_dict(load_file(hf_hub_download(repo, ckpt), device=device))
        pipe = StableDiffusionXLPipeline.from_pretrained(
            base, unet=unet, torch_dtype=dtype, variant="fp16", use_safetensors=True,
        ).to(device)
        pipe.scheduler = EulerDiscreteScheduler.from_config(
            pipe.scheduler.config, timestep_spacing="trailing",
        )

    elif engine in ("hyper-sdxl-4step", "hyper-sdxl-8step"):
        # ByteDance Hyper-SD is distributed as a LoRA — it fuses onto any
        # SDXL checkpoint. Pair with an anime base for anime output.
        from diffusers import StableDiffusionXLPipeline, DDIMScheduler
        from huggingface_hub import hf_hub_download

        n_steps = 8 if engine == "hyper-sdxl-8step" else 4
        base = base_model or "stabilityai/stable-diffusion-xl-base-1.0"
        repo = "ByteDance/Hyper-SD"
        lora_ckpt = f"Hyper-SDXL-{n_steps}steps-lora.safetensors"
        log.info(f"loading hyper-sdxl-{n_steps}step on base '{base}' (first time downloads ~7 GB + ~700 MB LoRA)")

        # Some anime bases ship only without an fp16 variant; try fp16 first.
        try:
            pipe = StableDiffusionXLPipeline.from_pretrained(
                base, torch_dtype=dtype, variant="fp16", use_safetensors=True,
            )
        except Exception as e:
            log.warning(f"fp16 variant load failed ({e}); falling back to default precision")
            pipe = StableDiffusionXLPipeline.from_pretrained(
                base, torch_dtype=dtype, use_safetensors=True,
            )
        pipe = pipe.to(device)

        # Apply Hyper-SD LoRA, fuse weights, swap scheduler.
        pipe.load_lora_weights(hf_hub_download(repo, lora_ckpt))
        pipe.fuse_lora()
        pipe.scheduler = DDIMScheduler.from_config(
            pipe.scheduler.config, timestep_spacing="trailing",
        )

    elif engine == "flux-schnell-4step":
        # Black Forest Labs FLUX.1-schnell — 12B-param DiT, distilled to 4 steps.
        # Apache 2.0 licensed, highest open-weights quality at small step counts.
        # ON M2 PRO: needs bfloat16 + model CPU offload to actually fit.
        # Expect ~30-90 s per image at 768x432 — slow but produces excellent output.
        from diffusers import FluxPipeline

        flux_dtype = _dtype_for_engine(engine, device, dtype)
        log.info(f"loading flux-schnell-4step with dtype={flux_dtype} (~24 GB download; SLOW on M2 Pro)")
        pipe = FluxPipeline.from_pretrained(
            "black-forest-labs/FLUX.1-schnell",
            torch_dtype=flux_dtype,
        )
        if device == "mps":
            # Stream model components to MPS on demand. Without this, FLUX OOMs
            # immediately on 32 GB unified memory.
            try:
                pipe.enable_model_cpu_offload(device="mps")
            except TypeError:
                # older diffusers signature
                pipe.enable_model_cpu_offload()
        else:
            pipe = pipe.to(device)

    elif engine == "z-image-turbo":
        # Alibaba Tongyi-MAI Z-Image-Turbo — a 6B-param DiT distilled to 8 steps.
        # MPS-specific: this is a transformer, not a UNet; fp16 attention
        # NaNs on Apple Silicon → black frames. Force fp32 here.
        from diffusers import DiffusionPipeline

        z_dtype = _dtype_for_engine(engine, device, dtype)
        log.info(f"loading z-image-turbo with dtype={z_dtype} (first time downloads ~13 GB)")
        try:
            pipe = DiffusionPipeline.from_pretrained(
                "Tongyi-MAI/Z-Image-Turbo",
                torch_dtype=z_dtype,
                use_safetensors=True,
                trust_remote_code=True,
            ).to(device)
        except Exception as e:
            log.warning(f"trust_remote_code load failed ({e}); retrying without")
            pipe = DiffusionPipeline.from_pretrained(
                "Tongyi-MAI/Z-Image-Turbo",
                torch_dtype=z_dtype,
                use_safetensors=True,
            ).to(device)

        # Defensive: attention slicing eases memory pressure on MPS with fp32.
        if hasattr(pipe, "enable_attention_slicing"):
            pipe.enable_attention_slicing()

    else:
        log.info(f"loading {engine} (first time downloads ~6.5 GB; cached at ./models/)")
        # Try fp16 variant first (smaller download). Fall back to default if not present.
        try:
            pipe = AutoPipelineForText2Image.from_pretrained(
                "stabilityai/sdxl-turbo",
                torch_dtype=dtype,
                variant="fp16",
                use_safetensors=True,
            )
        except Exception as e:
            log.warning(f"fp16 variant load failed ({e}); trying default precision")
            pipe = AutoPipelineForText2Image.from_pretrained(
                "stabilityai/sdxl-turbo",
                torch_dtype=dtype,
                use_safetensors=True,
            )
        pipe = pipe.to(device)

    # Disable safety checker — false positives on stylized art.
    if hasattr(pipe, "safety_checker"):
        pipe.safety_checker = None
    _pipeline = pipe
    _pipeline_engine = engine
    _pipeline_base_model = base_model
    return _pipeline


# ─────────────────────────────────────────────────────────────────────────────
# IP-Adapter — character reference conditioning
# ─────────────────────────────────────────────────────────────────────────────

_ip_adapter_loaded = False  # one-shot lazy load per process

def _ensure_ip_adapter_loaded(pipe, scale: float = 0.7) -> bool:
    """
    Lazy-load IP-Adapter Plus SDXL weights into the pipeline so we can pass
    `ip_adapter_image=...` to maintain character consistency across episodes.

    Returns True on success, False if the load failed (no IP-Adapter weights,
    incompatible pipeline, etc.) — callers should silently skip the IP-Adapter
    path in that case.

    Files downloaded on first use (~700 MB total):
      h94/IP-Adapter/sdxl_models/ip-adapter-plus_sdxl_vit-h.bin   (~700 MB)
      h94/IP-Adapter/models/image_encoder/                         (CLIPVisionModel)
    """
    global _ip_adapter_loaded
    if _ip_adapter_loaded:
        return True
    # Only SDXL family pipelines support IP-Adapter via diffusers.
    # FLUX / Z-Image pipelines don't expose the adapter API in the same way.
    if not hasattr(pipe, "load_ip_adapter"):
        log.warning("pipeline does not support IP-Adapter (engine likely flux/z-image) — skipping character references")
        return False
    try:
        # Image encoder must be loaded separately for IP-Adapter Plus.
        from transformers import CLIPVisionModelWithProjection
        import torch
        if pipe.image_encoder is None:
            pipe.image_encoder = CLIPVisionModelWithProjection.from_pretrained(
                "h94/IP-Adapter",
                subfolder="models/image_encoder",
                torch_dtype=getattr(pipe, "dtype", torch.float16),
            ).to(pipe.device)
        pipe.load_ip_adapter(
            "h94/IP-Adapter",
            subfolder="sdxl_models",
            weight_name="ip-adapter-plus_sdxl_vit-h.bin",
        )
        pipe.set_ip_adapter_scale(scale)
        log.info(f"loaded IP-Adapter Plus (scale={scale}) for character references")
        _ip_adapter_loaded = True
        return True
    except Exception as e:
        log.warning(f"IP-Adapter load failed ({e}); proceeding without character references")
        return False


def _resolve_character_references(
    character_ids: list[str],
    episode_characters: dict,
    library_root: Path,
) -> list:
    """
    Resolve character ids to reference images.

    `episode_characters` is `episode.characters` — a dict keyed by character
    slot (lead_male / lead_female / etc.). Each value has optional `id` and
    `reference_image` fields.

    Returns a list of PIL.Image objects (max 4). Characters with no
    reference_image, or whose ref points at a missing file, are silently
    skipped (the prompt will still describe them; just no IP conditioning).
    """
    from .library import resolve as resolve_lib
    from PIL import Image

    if not character_ids:
        return []

    # Build a lookup from id (or slot-key) → CharacterSpec dict
    by_id: dict[str, dict] = {}
    for slot, spec in (episode_characters or {}).items():
        if isinstance(spec, dict):
            cid = spec.get("id") or slot
            by_id[cid] = spec

    refs = []
    for cid in character_ids[:4]:  # IP-Adapter caps at ~4
        spec = by_id.get(cid)
        if not spec:
            log.info(f"character ref '{cid}' not found in episode.characters — skipping")
            continue
        ref_uri = spec.get("reference_image")
        if not ref_uri:
            continue
        try:
            path = resolve_lib(ref_uri, library_root)
        except Exception as e:
            log.warning(f"failed to resolve character ref {ref_uri!r}: {e}")
            continue
        if not path or not path.exists():
            log.info(f"character ref image missing on disk: {ref_uri} — skipping")
            continue
        refs.append(Image.open(path).convert("RGB"))
    return refs


def _placeholder_image(prompt: str, width: int, height: int, out_path: Path) -> None:
    """
    Tasteful gradient placeholder when SDXL isn't installed. Lets the
    pipeline run end-to-end without the 6.5 GB download.
    """
    from PIL import Image, ImageDraw, ImageFont, ImageFilter

    # Warm-cozy gradient — top: deep amber, bottom: warm brown
    grad = Image.new("RGB", (width, height))
    top = (255, 178, 102)
    bot = (101, 67, 33)
    for y in range(height):
        t = y / height
        r = int(top[0] * (1 - t) + bot[0] * t)
        g = int(top[1] * (1 - t) + bot[1] * t)
        b = int(top[2] * (1 - t) + bot[2] * t)
        for x in range(width):
            grad.putpixel((x, y), (r, g, b))

    # Soft vignette
    grad = grad.filter(ImageFilter.GaussianBlur(radius=2))

    draw = ImageDraw.Draw(grad)
    # Center the prompt text, wrapped
    wrap_chars = max(20, int(width / 16))
    lines = textwrap.wrap(prompt, width=wrap_chars)[:8]
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf", size=max(18, height // 36))
    except (OSError, IOError):
        font = ImageFont.load_default()

    y_text = height // 2 - (len(lines) * (font.size + 6)) // 2
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        line_w = bbox[2] - bbox[0]
        x_text = (width - line_w) // 2
        # soft shadow
        draw.text((x_text + 2, y_text + 2), line, fill=(20, 20, 20), font=font)
        draw.text((x_text, y_text), line, fill=(255, 248, 230), font=font)
        y_text += font.size + 6

    out_path.parent.mkdir(parents=True, exist_ok=True)
    grad.save(out_path, "PNG", optimize=True)


def generate_image(
    prompt: str,
    style: VisualStyle,
    image_cfg: ImageGeneration,
    cache_dir: Path,
    models_dir: Path,
    *,
    character_refs: list | None = None,    # PIL.Image objects (max 4) for IP-Adapter
    character_ids_for_cache: list[str] | None = None,   # ids — go into the cache key
) -> tuple[Path, str]:
    """
    Generate an image (or return cached). Returns (path, content_key).

    The full prompt sent to SDXL is style.base_prompt + " " + prompt.

    `character_refs` — pre-resolved PIL images of characters in this scene.
                      When non-empty, IP-Adapter is loaded and the refs are
                      passed as `ip_adapter_image` so face/look stays consistent
                      across episodes. Only used by SDXL family pipelines.
    `character_ids_for_cache` — the ids that drove the refs. Included in the
                      cache key so swapping references invalidates cleanly.
    """
    # ── Resolve effective base_model from tone (when not explicitly set) ────
    # Explicit image_cfg.base_model wins. Otherwise tone picks the default.
    effective_base_model = image_cfg.base_model or _default_base_model_for_tone(
        getattr(style, "tone", "realistic")
    )

    # ── Auto-inject prompt prefixes ─────────────────────────────────────────
    # Two layered adapters, applied in this order:
    #   1. Tone prefix (realistic → photo keywords / anime → anime keywords)
    #   2. Base-model prefix (e.g. Pony score tags)
    # Both are idempotent — first-token-check guards against double injection.
    base_positive = style.base_prompt
    base_negative = style.negative_prompt
    for pos_pref, neg_pref in (
        _tone_prompt_adapter(getattr(style, "tone", "realistic")),
        _base_model_prompt_adapter(effective_base_model),
    ):
        if pos_pref and pos_pref.split(",")[0].strip() not in base_positive:
            base_positive = pos_pref + base_positive
        if neg_pref and neg_pref.split(",")[0].strip() not in base_negative:
            base_negative = neg_pref + base_negative

    full_prompt = (base_positive + " " + prompt).strip()
    seed = image_cfg.seed if image_cfg.seed is not None else 0
    key = image_key(
        prompt=full_prompt,
        negative_prompt=base_negative,
        style_base=style.base_prompt,
        seed=seed,
        steps=image_cfg.steps,
        guidance=image_cfg.guidance,
        width=image_cfg.gen_width,
        height=image_cfg.gen_height,
        engine=image_cfg.engine,
        base_model=effective_base_model,
        # Including character_ids in the cache key means a chapter whose anchor
        # gains/loses/swaps a reference will regenerate cleanly (cache miss).
        # Sorted for stability — order in the list doesn't change the image.
        model_version=f"v2-chars-{','.join(sorted(character_ids_for_cache or []))}",
    )
    out_path = cache_dir / f"{key}.png"
    if out_path.exists():
        return out_path, key

    cache_dir.mkdir(parents=True, exist_ok=True)
    pipeline = _get_diffusers_pipeline(
        models_dir, engine=image_cfg.engine, base_model=effective_base_model,
    )

    if pipeline is None:
        log.warning(
            "torch+diffusers not installed; writing PLACEHOLDER image for prompt "
            f"'{prompt[:60]}...'. Install with: "
            ".venv/bin/pip install torch diffusers transformers"
        )
        _placeholder_image(full_prompt, image_cfg.gen_width, image_cfg.gen_height, out_path)
        return out_path, key

    import torch

    # Per-engine inference defaults — distilled models have their own sweet spots,
    # and some engines have practical resolution caps on M2 Pro memory.
    effective_width = image_cfg.gen_width
    effective_height = image_cfg.gen_height
    if image_cfg.engine == "sdxl-turbo":
        # SDXL Turbo: guidance MUST be 0 (trained value); ≤4 steps.
        effective_guidance = 0.0
        effective_steps = image_cfg.steps               # spec default 4
    elif image_cfg.engine in ("sdxl-lightning-4step", "sdxl-lightning-8step"):
        # Lightning UNet is hard-trained for an exact step count baked in
        # the engine name. Force it; user's `steps` value is ignored.
        effective_guidance = 0.0
        effective_steps = 8 if image_cfg.engine.endswith("8step") else 4
    elif image_cfg.engine in ("hyper-sdxl-4step", "hyper-sdxl-8step"):
        # Hyper-SD LoRA: same — force the step count the LoRA is trained for.
        effective_guidance = 0.0
        effective_steps = 8 if image_cfg.engine.endswith("8step") else 4
    elif image_cfg.engine == "flux-schnell-4step":
        # FLUX.1-schnell: guidance 0 (distilled, like Turbo); exactly 4 steps.
        # Auto-downscale to 768x432 (16:9) if user has 1024 — FLUX at 1024
        # on M2 Pro takes ~2-3 minutes per image and frequently OOMs.
        effective_guidance = 0.0
        effective_steps = 4
        if image_cfg.gen_width > 768:
            effective_width, effective_height = 768, 432
            log.info(f"flux-schnell: auto-downscaled {image_cfg.gen_width}x{image_cfg.gen_height} → 768x432 for M2 Pro memory")
    elif image_cfg.engine == "z-image-turbo":
        # Z-Image-Turbo uses guidance=1.0 (no CFG) and 8 distilled steps.
        # If the spec accidentally still has steps=4 from an SDXL config,
        # bump to 8 — Z-Image at <8 steps degrades visibly.
        effective_guidance = 1.0
        effective_steps = max(image_cfg.steps, 8)
    else:
        effective_guidance = image_cfg.guidance
        effective_steps = image_cfg.steps

    device = "mps" if torch.backends.mps.is_available() else "cpu"
    generator = torch.Generator(device=device).manual_seed(seed) if seed else None
    # FLUX-schnell doesn't accept negative_prompt (distilled away). Other
    # pipelines do. Branch the call shape accordingly.
    pipe_kwargs = dict(
        prompt=full_prompt,
        num_inference_steps=effective_steps,
        guidance_scale=effective_guidance,
        width=effective_width,
        height=effective_height,
        generator=generator,
    )
    if image_cfg.engine != "flux-schnell-4step":
        pipe_kwargs["negative_prompt"] = base_negative

    # ── Character reference conditioning (IP-Adapter) ─────────────────────────
    # Engaged only when (a) caller passed pre-resolved refs and (b) pipeline
    # supports the IP-Adapter API (SDXL family does; FLUX/Z-Image don't).
    if character_refs:
        if _ensure_ip_adapter_loaded(pipeline, scale=0.7):
            # Diffusers accepts a single PIL image OR a list (multi-character).
            pipe_kwargs["ip_adapter_image"] = (
                character_refs[0] if len(character_refs) == 1 else character_refs
            )

    image = pipeline(**pipe_kwargs).images[0]
    image.save(out_path, "PNG", optimize=True)
    log.info(f"generated {effective_width}x{effective_height} -> {out_path.name}")
    return out_path, key
