"""
Upscale 1024x576 -> 1920x1080.

Tries Real-ESRGAN via realesrgan-ncnn-vulkan if installed; otherwise uses
Lanczos via Pillow (perfectly fine for slow-motion anchors).
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

log = logging.getLogger("thai_novel.images.upscale")


def upscale_to_1080p(src: Path, dst: Path, method: str = "lanczos") -> Path:
    """
    Upscale src image to 1920x1080 at dst. Returns dst.

    method:
      "realesrgan" - tries realesrgan-ncnn-vulkan binary, falls back to lanczos
      "lanczos"    - PIL Lanczos resize
      "none"       - just copy (assumes src is already 1920x1080)
    """
    dst.parent.mkdir(parents=True, exist_ok=True)

    if method == "none":
        shutil.copy2(src, dst)
        return dst

    if method == "realesrgan" and shutil.which("realesrgan-ncnn-vulkan"):
        # Two-step: ESRGAN at 2x → 2048x1152, then Lanczos to 1920x1080.
        import subprocess
        from PIL import Image

        tmp = dst.with_suffix(".upscaled.png")
        try:
            subprocess.run(
                [
                    "realesrgan-ncnn-vulkan",
                    "-i", str(src),
                    "-o", str(tmp),
                    "-n", "realesrgan-x4plus-anime",
                    "-s", "2",
                ],
                check=True,
                capture_output=True,
            )
            with Image.open(tmp) as im:
                im = im.convert("RGB").resize((1920, 1080), Image.LANCZOS)
                im.save(dst, "PNG", optimize=True)
            tmp.unlink(missing_ok=True)
            return dst
        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            log.warning(f"realesrgan failed ({e}); falling back to lanczos")
            # fall through to lanczos below

    # Lanczos fallback (default)
    from PIL import Image

    with Image.open(src) as im:
        im = im.convert("RGB").resize((1920, 1080), Image.LANCZOS)
        im.save(dst, "PNG", optimize=True)
    return dst
