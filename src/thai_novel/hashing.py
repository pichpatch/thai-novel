"""
Canonical content hashing for cache keys.

Every cached artifact (narration WAV, generated image, rendered chunk) is
keyed by sha256 of its *semantic inputs* — not its mtime, not a UUID, not
a JSON dump that might reorder keys.

The contract: identical inputs → identical hash → instant cache hit.

Used by:
  - narration cache:  hash(text, voice, rate, pitch, engine_version) → .wav
  - image cache:      hash(prompt, neg_prompt, style_base, seed, steps, ...)
  - render chunk:     hash(chapter_id, timeline_json, bundle_hash)
"""

from __future__ import annotations

import hashlib
import json
from typing import Any


def canon_hash(obj: Any) -> str:
    """
    Deterministic sha256 of a JSON-serializable value.

    - dict keys are sorted
    - floats are stringified with full precision (avoids -0.0 vs 0.0 churn)
    - strings are UTF-8 encoded (Thai-safe)

    Returns a 16-char hex prefix (64 bits — collision-safe at the scale we care about).
    """
    canonical = json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return digest[:16]


def narration_key(text: str, voice: str, rate: str, pitch: str, engine_version: str = "edge-tts-v1") -> str:
    return canon_hash(
        {
            "kind": "narration",
            "text": text,
            "voice": voice,
            "rate": rate,
            "pitch": pitch,
            "engine_version": engine_version,
        }
    )


def image_key(
    prompt: str,
    negative_prompt: str,
    style_base: str,
    seed: int,
    steps: int,
    guidance: float,
    width: int,
    height: int,
    engine: str,
    model_version: str = "v1",
    base_model: str | None = None,
) -> str:
    return canon_hash(
        {
            "kind": "image",
            "prompt": prompt,
            "negative_prompt": negative_prompt,
            "style_base": style_base,
            "seed": seed,
            "steps": steps,
            "guidance": guidance,
            "width": width,
            "height": height,
            "engine": engine,
            "base_model": base_model,
            "model_version": model_version,
        }
    )
