"""
Pre-render text/logo cards as PNGs (one-shot, content-cached).

Replaces the Remotion-based card components. Output: a PNG at the project's
target resolution, ready to feed straight into `ffmpeg -loop 1 -i card.png`.

Cached by content hash so identical cards across episodes are free.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from ..hashing import canon_hash

log = logging.getLogger("thai_novel.compose.cards")


# Thai-capable fonts shipped with macOS, in order of preference.
# User can override by dropping a .ttf/.ttc/.otf into library/fonts/
_FALLBACK_FONTS = [
    "/System/Library/Fonts/Supplemental/Sukhothai.ttf",
    "/System/Library/Fonts/Thonburi.ttc",
    "/System/Library/Fonts/Supplemental/Ayuthaya.ttf",
    "/System/Library/Fonts/Supplemental/Sathu.ttf",
    "/Library/Fonts/Arial Unicode.ttf",
]


def find_font(library_root: Path) -> str:
    """Return a path to a Thai-capable TTF/TTC. Prefer library/fonts/ if present."""
    fonts_dir = library_root / "fonts"
    if fonts_dir.is_dir():
        for ext in (".ttf", ".otf", ".ttc"):
            for f in sorted(fonts_dir.glob(f"*{ext}")):
                return str(f)
    for path in _FALLBACK_FONTS:
        if os.path.isfile(path):
            return path
    raise FileNotFoundError(
        "No Thai-capable font found. Drop a .ttf/.otf into library/fonts/ "
        "(Sarabun, Noto Sans Thai recommended)."
    )


def _font(path: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(path, size=size)


def _scale(value: int, height: int) -> int:
    """Scale a font size that was designed at 1080p down for the target height."""
    return max(8, round(value * height / 1080))


def _draw_centered(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.FreeTypeFont,
    cx: int,
    cy: int,
    fill: tuple[int, int, int],
    shadow: tuple[int, int, int] | None = (0, 0, 0),
    shadow_offset: int = 3,
) -> None:
    bbox = draw.textbbox((0, 0), text, font=font)
    w = bbox[2] - bbox[0]
    h = bbox[3] - bbox[1]
    x = cx - w // 2 - bbox[0]
    y = cy - h // 2 - bbox[1]
    if shadow:
        draw.text((x + shadow_offset, y + shadow_offset), text, fill=shadow, font=font)
    draw.text((x, y), text, fill=fill, font=font)


def _wrap_lines(text: str, font: ImageFont.FreeTypeFont, max_width: int, draw: ImageDraw.ImageDraw) -> list[str]:
    """Naive word-wrap by characters for Thai (Thai doesn't use spaces between words much)."""
    if not text:
        return []
    # Try whitespace split first (handles English title pieces)
    words = text.split()
    if len(words) >= 2:
        lines: list[str] = []
        current = ""
        for w in words:
            trial = (current + " " + w).strip()
            if draw.textlength(trial, font=font) <= max_width:
                current = trial
            else:
                if current:
                    lines.append(current)
                current = w
        if current:
            lines.append(current)
        return lines
    # Thai/no-space text: character-wise
    lines = []
    current = ""
    for ch in text:
        trial = current + ch
        if draw.textlength(trial, font=font) <= max_width:
            current = trial
        else:
            lines.append(current)
            current = ch
    if current:
        lines.append(current)
    return lines


# ─────────────────────────────────────────────────────────────────────────────
# Card renderers
# ─────────────────────────────────────────────────────────────────────────────


def render_logo_splash(
    logo_path: Path | None,
    channel_name: str,
    width: int,
    height: int,
    out_path: Path,
) -> Path:
    """
    Full-screen logo, edge-to-edge. Cover semantics: scales so the logo fills
    the frame in both dimensions, cropping the smaller axis only if needed.

    For a 16:9 logo into a 16:9 frame, this is a clean rescale with no crop.
    For mismatched aspect ratios, the longer axis gets center-cropped.
    """
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if logo_path and logo_path.exists():
        logo = Image.open(logo_path).convert("RGB")
        lw, lh = logo.size
        # Cover: scale by the LARGER of the two ratios so both dims are ≥ target
        scale = max(width / lw, height / lh)
        scaled_size = (round(lw * scale), round(lh * scale))
        logo = logo.resize(scaled_size, Image.LANCZOS)
        # Center-crop to exactly (width, height)
        left = (scaled_size[0] - width) // 2
        top = (scaled_size[1] - height) // 2
        logo = logo.crop((left, top, left + width, top + height))
        logo.save(out_path, "PNG", optimize=True)
    else:
        # Fallback: large channel name on dark background
        img = Image.new("RGB", (width, height), (10, 6, 4))
        draw = ImageDraw.Draw(img)
        font_path = find_font(out_path.parent.parent.parent / "library")
        font = _font(font_path, _scale(160, height))
        _draw_centered(draw, channel_name, font, width // 2, height // 2, (255, 248, 223))
        img.save(out_path, "PNG", optimize=True)

    return out_path


def render_episode_title(
    title_text: str,
    logo_path: Path | None,
    width: int,
    height: int,
    out_path: Path,
    font_path: str,
) -> Path:
    """Episode title card with optional small logo above the title."""
    img = Image.new("RGB", (width, height), (10, 6, 4))
    # Subtle vignette: paint a soft radial dark wash
    overlay = Image.new("L", (width, height), 0)
    od = ImageDraw.Draw(overlay)
    od.ellipse(
        [(-width // 4, -height // 4), (width + width // 4, height + height // 4)],
        fill=40,
    )
    img = Image.composite(Image.new("RGB", (width, height), (50, 30, 18)), img, overlay)

    draw = ImageDraw.Draw(img)
    title_font = _font(font_path, _scale(86, height))

    # Word-wrap the title to max ~85% of frame width
    max_text_width = int(width * 0.85)
    lines = _wrap_lines(title_text, title_font, max_text_width, draw)
    line_height = int(_scale(86, height) * 1.3)
    block_h = line_height * len(lines)

    # Position: vertically centered, with optional logo above
    logo_h = 0
    if logo_path and logo_path.exists():
        logo = Image.open(logo_path).convert("RGBA")
        target = _scale(140, height)
        lw, lh = logo.size
        scale = target / max(lw, lh)
        new_size = (int(lw * scale), int(lh * scale))
        logo = logo.resize(new_size, Image.LANCZOS)
        logo_h = new_size[1]
        margin = _scale(32, height)
        total_h = logo_h + margin + block_h
        top = (height - total_h) // 2
        lx = (width - new_size[0]) // 2
        img.paste(logo, (lx, top), logo)
        text_top = top + logo_h + margin
    else:
        text_top = (height - block_h) // 2

    for i, line in enumerate(lines):
        _draw_centered(
            draw, line, title_font,
            width // 2, text_top + i * line_height + line_height // 2,
            (255, 248, 223),
        )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path, "PNG", optimize=True)
    return out_path


def render_chapter_card(
    title: str,
    chapter_index: int,
    total_chapters: int,
    width: int,
    height: int,
    out_path: Path,
    font_path: str,
) -> Path:
    """Between-chapters breath card: 'CHAPTER 1 / 5' + chapter title."""
    img = Image.new("RGB", (width, height), (14, 8, 5))
    draw = ImageDraw.Draw(img)
    sub_font = _font(font_path, _scale(40, height))
    title_font = _font(font_path, _scale(88, height))

    sub_text = f"chapter {chapter_index} / {total_chapters}"
    sub_y = int(height * 0.36)
    _draw_centered(draw, sub_text, sub_font, width // 2, sub_y, (201, 169, 122))

    # Decorative bar between the chapter label and title
    bar_w = _scale(320, height)
    bar_h = _scale(3, height)
    bar_y = sub_y + _scale(46, height)
    draw.rectangle(
        [
            ((width - bar_w) // 2, bar_y),
            ((width + bar_w) // 2, bar_y + bar_h),
        ],
        fill=(201, 169, 122),
    )

    # Wrap title
    max_text_width = int(width * 0.86)
    lines = _wrap_lines(title, title_font, max_text_width, draw)
    line_height = int(_scale(88, height) * 1.28)
    title_top = bar_y + _scale(48, height)
    for i, line in enumerate(lines):
        _draw_centered(
            draw, line, title_font,
            width // 2, title_top + i * line_height + line_height // 2,
            (255, 248, 223),
        )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path, "PNG", optimize=True)
    return out_path


def render_end_card(
    message: str | None,
    next_episode_title: str | None,
    channel_name: str,
    width: int,
    height: int,
    out_path: Path,
    font_path: str,
) -> Path:
    img = Image.new("RGB", (width, height), (5, 3, 2))
    draw = ImageDraw.Draw(img)

    message_font = _font(font_path, _scale(52, height))
    label_font = _font(font_path, _scale(36, height))
    title_font = _font(font_path, _scale(72, height))
    channel_font = _font(font_path, _scale(32, height))

    blocks: list[tuple[str, ImageFont.FreeTypeFont, tuple[int, int, int]]] = []
    if message:
        blocks.append((message, message_font, (255, 248, 223)))
    if next_episode_title:
        blocks.append(("next episode", label_font, (201, 169, 122)))
        blocks.append((next_episode_title, title_font, (255, 248, 223)))
    blocks.append((channel_name, channel_font, (140, 122, 94)))

    line_heights = [int(font.size * 1.4) for _, font, _ in blocks]
    gap = _scale(28, height)
    total_h = sum(line_heights) + gap * (len(blocks) - 1)
    y = (height - total_h) // 2
    for (text, font, fill), lh in zip(blocks, line_heights, strict=True):
        _draw_centered(draw, text, font, width // 2, y + lh // 2, fill)
        y += lh + gap

    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path, "PNG", optimize=True)
    return out_path


# ─────────────────────────────────────────────────────────────────────────────
# Cache layer
# ─────────────────────────────────────────────────────────────────────────────


def cached_card(
    kind: str,
    inputs: dict,
    cache_dir: Path,
    renderer,
    **renderer_kwargs,
) -> Path:
    """
    Generic content-hash cache wrapper. `inputs` defines the cache key;
    `renderer` is the function that produces the PNG.
    """
    key = canon_hash({"kind": kind, "inputs": inputs})
    out = cache_dir / f"{kind}_{key}.png"
    if out.exists():
        return out
    return renderer(out_path=out, **renderer_kwargs)
