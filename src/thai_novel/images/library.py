"""
Reusable visual library.

References use the `library://` URI scheme:
  library://backgrounds/cafe_rainy_night   ->  library/visuals/backgrounds/cafe_rainy_night.{png,jpg,webp}
  library://characters/female_lead_blush   ->  library/visuals/characters/female_lead_blush.png
  library://sfx/cup_clink                   ->  library/audio/sfx/cup_clink.{mp3,wav,ogg}

This module resolves refs to disk paths and promotes generated images into
the library when `save_to_library_as` is set.
"""

from __future__ import annotations

import json
import logging
import shutil
from pathlib import Path

log = logging.getLogger("thai_novel.images.library")

# kind  -> (folder, allowed extensions)
KIND_FOLDERS = {
    "backgrounds":  ("visuals/backgrounds",  (".png", ".jpg", ".jpeg", ".webp")),
    "characters":   ("visuals/characters",   (".png", ".jpg", ".jpeg", ".webp")),
    "overlays":     ("visuals/overlays",     (".png", ".webp")),
    "luts":         ("visuals/luts",         (".cube", ".png")),
    "sfx":          ("audio/sfx",            (".mp3", ".wav", ".ogg", ".flac")),
}


class LibraryRefError(LookupError):
    pass


def parse_ref(ref: str) -> tuple[str, str]:
    """library://<kind>/<name>  ->  (kind, name)"""
    if not ref.startswith("library://"):
        raise LibraryRefError(f"not a library ref: {ref!r}")
    body = ref[len("library://"):]
    if "/" not in body:
        raise LibraryRefError(f"library ref must be <kind>/<name>: {ref!r}")
    kind, name = body.split("/", 1)
    if kind not in KIND_FOLDERS:
        raise LibraryRefError(
            f"unknown library kind {kind!r}; allowed: {sorted(KIND_FOLDERS)}"
        )
    return kind, name


def resolve(ref: str, library_root: Path) -> Path | None:
    """Resolve a library ref to a file path. Returns None if not found."""
    kind, name = parse_ref(ref)
    folder, exts = KIND_FOLDERS[kind]
    base = library_root / folder
    for ext in exts:
        candidate = base / f"{name}{ext}"
        if candidate.exists():
            return candidate
    return None


def require(ref: str, library_root: Path) -> Path:
    """Same as resolve() but raises if not found."""
    p = resolve(ref, library_root)
    if p is None:
        raise LibraryRefError(
            f"library ref not found: {ref!r}\n"
            f"Tried: {library_root / KIND_FOLDERS[parse_ref(ref)[0]][0]}/"
            f"{parse_ref(ref)[1]}.[png|jpg|...]"
        )
    return p


def get_metadata(ref: str, library_root: Path) -> dict | None:
    """
    Return the _index.json metadata entry for a library ref, or None.

    The metadata is written by promote() and contains at minimum:
      - file: the on-disk filename
      - image_key: content-hash of (prompt + style + seed + size + engine ...)
                   used to detect when a promoted image is now stale.
    """
    kind, name = parse_ref(ref)
    folder, _exts = KIND_FOLDERS[kind]
    index_path = library_root / folder / "_index.json"
    if not index_path.exists():
        return None
    try:
        idx = json.loads(index_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    return idx.get(name)


def promote(
    source_image: Path,
    name: str,
    library_root: Path,
    kind: str = "backgrounds",
    metadata: dict | None = None,
) -> Path:
    """
    Copy a generated image into the library and update the kind's _index.json.

    Returns the new path inside the library.
    """
    folder, _exts = KIND_FOLDERS[kind]
    target_dir = library_root / folder
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = target_dir / f"{name}{source_image.suffix.lower()}"
    shutil.copy2(source_image, target_path)

    # Update the kind's index manifest
    index_path = target_dir / "_index.json"
    try:
        index = json.loads(index_path.read_text(encoding="utf-8")) if index_path.exists() else {}
    except json.JSONDecodeError:
        index = {}
    index[name] = {
        "file": target_path.name,
        **(metadata or {}),
    }
    index_path.write_text(
        json.dumps(index, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8"
    )

    log.info(f"promoted -> library://{kind}/{name}  ({target_path.relative_to(library_root)})")
    return target_path
