"""Thai sentence segmentation for narration blocks."""

from __future__ import annotations

import re


def segment_thai(text: str) -> list[str]:
    """
    Split Thai narration into TTS-friendly sentences.

    Uses pythainlp's sentence tokenizer when available, falls back to a
    punctuation-based heuristic. Either way, we post-process to:
      - merge fragments shorter than ~40 chars into the previous sentence
      - normalize whitespace
    """
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return []

    try:
        from pythainlp.tokenize import sent_tokenize  # type: ignore

        sents = [s.strip() for s in sent_tokenize(text, engine="crfcut") if s.strip()]
    except Exception:
        # Fallback: split on ฯ / ! / ? / explicit period / newline-as-period.
        sents = [s.strip() for s in re.split(r"(?<=[\.\!\?ฯ])\s+|(?<=\n)", text) if s.strip()]

    # Merge very-short fragments (< 40 chars) into the previous sentence —
    # they're usually trailing connectives that read better attached.
    merged: list[str] = []
    for s in sents:
        if merged and len(s) < 40:
            merged[-1] = merged[-1] + " " + s
        else:
            merged.append(s)
    return merged


def estimate_seconds(text: str, rate: str = "-10%") -> float:
    """Rough duration estimate for Thai TTS at a given rate."""
    # Empirical: Premwadee at -10% reads ~2.5 Thai chars/sec.
    base_cps = 2.5
    rate_multiplier = 1.0
    m = re.match(r"^([+-]?\d+(?:\.\d+)?)\s*%$", rate.strip())
    if m:
        pct = float(m.group(1))
        rate_multiplier = 1.0 + pct / 100.0  # -10% -> 0.9 (slower)
    return len(text) / (base_cps * rate_multiplier)
