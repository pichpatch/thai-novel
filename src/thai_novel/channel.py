"""Channel-wide settings that are intentionally not configurable per episode."""

from pathlib import Path

CHANNEL_NAME = "T H A I Novel"
NARRATOR_VOICE = "th-TH-PremwadeeNeural"
NARRATOR_BASE_RATE = "-15%"
WELCOME_NARRATION = (
    "ยินดีต้อนรับเข้าสู่ช่อง T  H  A  I  โนเว่ล "
    "ขอให้สนุกกับการรับฟังค่ะ"
)
BACKGROUND_AUDIO_PATH = Path("library/audio/background.mp3")
BACKGROUND_VOLUME_DB = -22.0
