"""In-process Z-Image-Turbo loader and generator.

Adapted from the standalone Text2Image project (https://huggingface.co/Tongyi-MAI/Z-Image-Turbo).
We hold the pipeline in module-level state so all scenes in one render reuse
the same warm model. The process exits when pipeline.py finishes — no server
to start, no port to manage, no cleanup needed.

Apple Silicon notes (MPS):
  - default dtype is bfloat16; fp16 produces black images on current MPS
  - VAE is forced to fp32 at decode time for numerical stability
  - guidance_scale must be 0.0 (Turbo requirement)
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

log = logging.getLogger(__name__)

# Make sure ops not yet on MPS fall back to CPU silently.
os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")

MODEL_ID = os.environ.get("Z_IMAGE_MODEL_ID", "Tongyi-MAI/Z-Image-Turbo")
HF_TOKEN = os.environ.get("HF_TOKEN")
_DTYPE_OVERRIDE = os.environ.get("Z_IMAGE_DTYPE", "").strip().lower()

_pipe = None  # diffusers ZImagePipeline | None


def _parse_dtype(name: str):
    import torch
    return {
        "float32": torch.float32, "fp32": torch.float32,
        "float16": torch.float16, "fp16": torch.float16,
        "bfloat16": torch.bfloat16, "bf16": torch.bfloat16,
    }.get(name)


def _pick_device():
    import torch
    if torch.cuda.is_available():
        return "cuda", _parse_dtype(_DTYPE_OVERRIDE) or torch.bfloat16
    if torch.backends.mps.is_available():
        # bfloat16 default: float16 produces NaN/black images for Z-Image on MPS.
        return "mps", _parse_dtype(_DTYPE_OVERRIDE) or torch.bfloat16
    import torch as _t
    return "cpu", _parse_dtype(_DTYPE_OVERRIDE) or _t.float32


def load_pipeline():
    """Load the model into memory. Idempotent — returns the cached pipeline."""
    global _pipe
    if _pipe is not None:
        return _pipe
    import torch  # noqa: F401  (we want a clear ImportError if torch missing)
    from diffusers import ZImagePipeline

    device, dtype = _pick_device()
    log.info("Loading %s on %s (%s) — first load takes ~40s once weights are cached.", MODEL_ID, device, dtype)
    pipe = ZImagePipeline.from_pretrained(MODEL_ID, torch_dtype=dtype, token=HF_TOKEN)
    pipe.to(device)

    if device == "mps":
        # Classic Apple Silicon black-image fix: VAE in fp32 for decode stability.
        if hasattr(pipe, "vae") and pipe.vae is not None:
            log.info("Forcing VAE to float32 (MPS stability).")
            pipe.vae.to(dtype=torch.float32)
        pipe.enable_attention_slicing()

    _pipe = pipe
    return _pipe


def generate(
    prompt: str,
    out_path: Path,
    width: int = 1024,
    height: int = 576,
    steps: int = 9,
    seed: int | None = None,
) -> Path:
    """Render one PNG. Width/height must be multiples of 64.

    Defaults to 1024×576 — close to 16:9 and ~2-3 min per image on M2 Pro.
    """
    import torch
    pipe = load_pipeline()
    device, _ = _pick_device()

    generator = None
    if seed is not None:
        # MPS generator must live on CPU per PyTorch's current behaviour.
        gen_device = "cpu" if device == "mps" else device
        generator = torch.Generator(device=gen_device).manual_seed(int(seed))

    log.info("Image: %s", prompt[:90])
    result = pipe(
        prompt=prompt,
        width=width,
        height=height,
        num_inference_steps=steps,
        guidance_scale=0.0,  # Turbo requires 0
        generator=generator,
    )
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    result.images[0].save(out_path)
    return out_path
