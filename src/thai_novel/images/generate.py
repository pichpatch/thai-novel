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

_pipeline = None  # lazy-init singleton


def _get_diffusers_pipeline(models_dir: Path):
    """Lazy-load SDXL Turbo via diffusers+MPS. Returns None if torch missing."""
    global _pipeline
    if _pipeline is not None:
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

    log.info("loading sdxl-turbo (first time downloads ~6.5 GB; cached at ./models/)")
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
    # SDXL Turbo benefits from disabling the safety checker (it can produce
    # false positives on stylized anime art). Comment out if you prefer safety.
    if hasattr(pipe, "safety_checker"):
        pipe.safety_checker = None
    _pipeline = pipe
    return _pipeline


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
) -> tuple[Path, str]:
    """
    Generate an image (or return cached). Returns (path, content_key).

    The full prompt sent to SDXL is style.base_prompt + " " + prompt.
    """
    full_prompt = (style.base_prompt + " " + prompt).strip()
    seed = image_cfg.seed if image_cfg.seed is not None else 0
    key = image_key(
        prompt=full_prompt,
        negative_prompt=style.negative_prompt,
        style_base=style.base_prompt,
        seed=seed,
        steps=image_cfg.steps,
        guidance=image_cfg.guidance,
        width=image_cfg.gen_width,
        height=image_cfg.gen_height,
        engine=image_cfg.engine,
    )
    out_path = cache_dir / f"{key}.png"
    if out_path.exists():
        return out_path, key

    cache_dir.mkdir(parents=True, exist_ok=True)
    pipeline = _get_diffusers_pipeline(models_dir)

    if pipeline is None:
        log.warning(
            "torch+diffusers not installed; writing PLACEHOLDER image for prompt "
            f"'{prompt[:60]}...'. Install with: "
            ".venv/bin/pip install torch diffusers transformers"
        )
        _placeholder_image(full_prompt, image_cfg.gen_width, image_cfg.gen_height, out_path)
        return out_path, key

    import torch

    # SDXL Turbo requires guidance_scale=0.0 (it's the trained value for ADD).
    # The spec's `guidance` field is honored for SD-XL base, but for sdxl-turbo
    # we force 0.0 to avoid the "too noisy / muddy" output that 1.5+ produces.
    effective_guidance = 0.0 if image_cfg.engine == "sdxl-turbo" else image_cfg.guidance

    device = "mps" if torch.backends.mps.is_available() else "cpu"
    generator = torch.Generator(device=device).manual_seed(seed) if seed else None
    image = pipeline(
        prompt=full_prompt,
        negative_prompt=style.negative_prompt,
        num_inference_steps=image_cfg.steps,
        guidance_scale=effective_guidance,
        width=image_cfg.gen_width,
        height=image_cfg.gen_height,
        generator=generator,
    ).images[0]
    image.save(out_path, "PNG", optimize=True)
    log.info(f"generated {image_cfg.gen_width}x{image_cfg.gen_height} -> {out_path.name}")
    return out_path, key
