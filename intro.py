"""Auto-generate a short intro card if intro/intro.mp4 doesn't exist.

The user can override at any time by dropping their own intro.mp4 into the
intro/ folder — we only generate one if none is supplied.

Generated intro: 5 seconds, dark gradient, channel name + episode title
overlaid in white, with a short Thai TTS "ยินดีต้อนรับสู่ช่อง …" voiceover.
"""
from __future__ import annotations

import logging
import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from tts import ThaiTTS
from video import VIDEO_FPS, VIDEO_H, VIDEO_W

log = logging.getLogger(__name__)

INTRO_SECONDS = 5


def _find_thai_font() -> str:
    """Best-effort Thai-capable font lookup on macOS."""
    candidates = [
        "/System/Library/Fonts/Supplemental/Ayuthaya.ttf",
        "/System/Library/Fonts/Supplemental/Krungthep.ttf",
        "/Library/Fonts/Arial Unicode.ttf",
        "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
        "/System/Library/Fonts/ThonburiUI.ttc",
        "/System/Library/Fonts/Thonburi.ttc",
    ]
    for p in candidates:
        if Path(p).exists():
            return p
    return "Helvetica"  # fallback; may not render Thai correctly


_LOGO_NAMES = ("logo.png", "logo.jpg", "logo.jpeg", "logo.webp")
_MAX_LOGO_HEIGHT_FRAC = 0.35  # logo can take up to 35% of card height


def _find_logo(intro_dir: Path) -> Path | None:
    for name in _LOGO_NAMES:
        p = intro_dir / name
        if p.exists():
            return p
    return None


def _render_card(channel: str, title: str, out_png: Path, intro_dir: Path) -> Path:
    img = Image.new("RGB", (VIDEO_W, VIDEO_H), (10, 10, 18))
    # Subtle vertical gradient via horizontal line fill (one line per row).
    draw = ImageDraw.Draw(img)
    for y in range(VIDEO_H):
        v = 10 + int(40 * y / VIDEO_H)
        draw.line([(0, y), (VIDEO_W, y)], fill=(v, v, v + 6))

    font_path = _find_thai_font()
    try:
        font_large = ImageFont.truetype(font_path, 64)
        font_small = ImageFont.truetype(font_path, 36)
    except OSError:
        font_large = ImageFont.load_default()
        font_small = ImageFont.load_default()

    def centered(text: str, font: ImageFont.FreeTypeFont, y: int, fill=(240, 240, 240)) -> None:
        bbox = draw.textbbox((0, 0), text, font=font)
        w = bbox[2] - bbox[0]
        draw.text(((VIDEO_W - w) // 2, y), text, font=font, fill=fill)

    # Optional logo at intro/logo.{png,jpg,jpeg,webp}. If present, scale to
    # max 35% of card height (aspect preserved) and place it above the text.
    logo_path = _find_logo(intro_dir)
    if logo_path is not None:
        log.info("Using logo: %s", logo_path)
        logo = Image.open(logo_path).convert("RGBA")
        max_h = int(VIDEO_H * _MAX_LOGO_HEIGHT_FRAC)
        if logo.height > max_h:
            ratio = max_h / logo.height
            logo = logo.resize((int(logo.width * ratio), max_h), Image.LANCZOS)
        # Cap width too in case it's very wide.
        max_w = int(VIDEO_W * 0.6)
        if logo.width > max_w:
            ratio = max_w / logo.width
            logo = logo.resize((max_w, int(logo.height * ratio)), Image.LANCZOS)

        # Vertical layout when a logo is present:
        #   ┌───────────────────────────┐
        #   │          [logo]           │  top quarter
        #   │      <channel name>       │  centered
        #   │         <title>           │  below channel
        #   └───────────────────────────┘
        logo_y = int(VIDEO_H * 0.18)
        img.paste(logo, ((VIDEO_W - logo.width) // 2, logo_y), logo)
        channel_y = logo_y + logo.height + 40
        title_y = channel_y + 90
        centered(channel, font_large, channel_y)
        centered(title, font_small, title_y, fill=(180, 180, 200))
    else:
        # No logo: original centered text layout.
        centered(channel, font_large, VIDEO_H // 2 - 80)
        centered(title, font_small, VIDEO_H // 2 + 20, fill=(180, 180, 200))

    out_png.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_png)
    return out_png


def ensure_intro(
    channel: str,
    title: str,
    intro_dir: Path,
    tts: ThaiTTS,
    channel_spoken: str | None = None,
) -> Path:
    """Return the intro mp4 path, generating one if the user hasn't supplied it.

    `channel` is what's drawn on the visual card. `channel_spoken` (optional)
    is what TTS reads in the welcome line — defaults to `channel`. Useful
    when the brand is stylised (e.g. "ThAI Novel" displayed, "ที เอช เอ ไอ
    โนเวล" spoken).

    User override: place a file named intro.mp4 in `intro_dir`.
    """
    intro_dir.mkdir(parents=True, exist_ok=True)
    user_mp4 = intro_dir / "intro.mp4"
    if user_mp4.exists():
        log.info("Using user-supplied intro: %s", user_mp4)
        return user_mp4

    log.info("No user intro found — generating a default 5s intro card.")
    card_png = intro_dir / "_generated_card.png"
    _render_card(channel, title, card_png, intro_dir)

    # TTS the welcome line. Use the spoken form for pronunciation control.
    spoken = channel_spoken or channel
    welcome_text = f"ยินดีต้อนรับสู่ช่อง {spoken} วันนี้พบกับ {title}"
    welcome_wav = intro_dir / "_generated_welcome.wav"
    tts.synthesise(welcome_text, welcome_wav)

    # Build a 5s clip; if TTS is shorter, the still image pads to 5s; if
    # longer, we extend to the TTS duration (rounded up) so the voice isn't cut.
    out_mp4 = intro_dir / "_generated_intro.mp4"
    vf = (
        f"scale={VIDEO_W}:{VIDEO_H}:force_original_aspect_ratio=decrease,"
        f"pad={VIDEO_W}:{VIDEO_H}:(ow-iw)/2:(oh-ih)/2:color=black,"
        f"format=yuv420p,fps={VIDEO_FPS}"
    )
    # Decide duration: max(INTRO_SECONDS, tts duration + 0.5s tail).
    from video import probe_duration  # local import to avoid circular at module load
    tts_dur = probe_duration(welcome_wav)
    duration = max(INTRO_SECONDS, tts_dur + 0.5)

    cmd = [
        "ffmpeg", "-y",
        "-loop", "1", "-i", str(card_png),
        "-i", str(welcome_wav),
        "-vf", vf,
        "-c:v", "libx264", "-tune", "stillimage", "-preset", "medium", "-crf", "20",
        "-c:a", "aac", "-b:a", "192k", "-ar", "44100",
        "-t", f"{duration:.2f}",
        "-movflags", "+faststart",
        str(out_mp4),
    ]
    log.debug("intro ffmpeg: %s", " ".join(cmd))
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        log.error("intro ffmpeg stderr:\n%s", p.stderr[-2000:])
        raise RuntimeError("Failed to render intro")
    return out_mp4
