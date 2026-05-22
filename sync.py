"""Pre-fetch / refresh every model this project uses.

Run via `./sync`. Idempotent — first call downloads everything, later calls
only pull files that changed upstream.

What gets cached (all under ~/.cache/huggingface/hub/ by default):

  • Tongyi-MAI/Z-Image-Turbo          — image model, ~12 GB
  • VIZINTZOR/VachanaTTS              — all four Thai voices (th_f_1, th_m_1,
                                        th_f_2, th_m_2) + speaker_config.json,
                                        a few MB total

The optional `--voices-only` flag skips the big Z-Image download — useful
when you just want all Thai voices available offline.

The optional `--refresh-pip` flag also runs `pip install -U -r requirements.txt`.
"""
from __future__ import annotations

import argparse
import logging
import subprocess
import sys
from pathlib import Path

log = logging.getLogger("sync")

HERE = Path(__file__).resolve().parent

VACHANA_REPO = "VIZINTZOR/VachanaTTS"
VACHANA_VOICES = ["th_f_1", "th_m_1", "th_f_2", "th_m_2"]
Z_IMAGE_REPO = "Tongyi-MAI/Z-Image-Turbo"


def _hf_download_file(repo_id: str, filename: str) -> None:
    from huggingface_hub import hf_hub_download
    path = hf_hub_download(repo_id=repo_id, filename=filename)
    log.info("  cached %s → %s", filename, path)


def _hf_snapshot(repo_id: str) -> None:
    from huggingface_hub import snapshot_download
    log.info("Pulling full snapshot: %s", repo_id)
    path = snapshot_download(repo_id=repo_id)
    log.info("  → %s", path)


def sync_voices() -> None:
    log.info("Caching all Vachana Thai voices ...")
    _hf_download_file(VACHANA_REPO, "speaker_config.json")
    for voice in VACHANA_VOICES:
        _hf_download_file(VACHANA_REPO, f"voices/{voice}.onnx")


def sync_image_model() -> None:
    log.info("Caching Z-Image-Turbo (~12 GB, first time only) ...")
    _hf_snapshot(Z_IMAGE_REPO)


def refresh_pip() -> None:
    pip = HERE / ".venv" / "bin" / "pip"
    if not pip.exists():
        log.warning("No .venv yet — run ./run first; skipping pip refresh.")
        return
    log.info("Upgrading pip deps to latest in requirements.txt ...")
    subprocess.check_call([str(pip), "install", "-U", "-r", str(HERE / "requirements.txt")])


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Refresh local caches for thai-novel.")
    ap.add_argument("--voices-only", action="store_true",
                    help="Skip the big Z-Image-Turbo download; only refresh Thai voices.")
    ap.add_argument("--refresh-pip", action="store_true",
                    help="Also run pip install -U -r requirements.txt")
    args = ap.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s | %(message)s",
        datefmt="%H:%M:%S",
    )

    try:
        sync_voices()
        if not args.voices_only:
            sync_image_model()
        if args.refresh_pip:
            refresh_pip()
    except Exception as exc:
        log.error("Sync failed: %s", exc)
        return 1

    log.info("✅ Cache up to date. Subsequent ./make runs are fully offline.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
