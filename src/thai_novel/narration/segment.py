"""Thai sentence segmentation for narration blocks."""

from __future__ import annotations

import re

from ..channel import NARRATOR_BASE_RATE


_TERMINAL_PUNCT = (".", "!", "?", "ฯ")


def _sentences_in_paragraph(text: str) -> list[str]:
    """Split one paragraph into TTS-friendly sentences."""
    text = re.sub(r"[ \t]+", " ", text).strip()
    if not text:
        return []

    try:
        from pythainlp.tokenize import sent_tokenize  # type: ignore

        raw_sents = [s.strip() for s in sent_tokenize(text, engine="crfcut") if s.strip()]
    except Exception:
        raw_sents = [text]

    sents: list[str] = []
    for raw in raw_sents:
        # Fallback: split on ฯ / ! / ? / explicit period.
        sents.extend(s.strip() for s in re.split(r"(?<=[\.\!\?ฯ])\s+", raw) if s.strip())

    # Merge very-short fragments (< 40 chars) into the previous sentence —
    # they're usually trailing connectives that read better attached.
    merged: list[str] = []
    for s in sents:
        has_intentional_stop = s.endswith(_TERMINAL_PUNCT)
        if merged and len(s) < 40 and not has_intentional_stop:
            merged[-1] = merged[-1] + " " + s
        else:
            merged.append(s)
    return merged


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

    return _sentences_in_paragraph(text)


def segment_thai_with_pauses(
    text: str,
    sentence_pause_ms: int,
    paragraph_pause_ms: int,
) -> tuple[list[str], list[int]]:
    """
    Split Thai narration and preserve author-controlled paragraph breaks.

    Returns `(sentences, pauses_after_ms)`, where `pauses_after_ms[i]` is the
    silence after `sentences[i]`. Blank lines and explicit newlines become
    paragraph pauses; punctuation-only boundaries use the normal sentence pause.
    """
    text = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not text:
        return [], []

    paragraphs = [p.strip() for p in re.split(r"\n+", text) if p.strip()]

    sentences: list[str] = []
    paragraph_end_indexes: set[int] = set()
    for paragraph in paragraphs:
        para_sents = _sentences_in_paragraph(paragraph)
        if not para_sents:
            continue
        sentences.extend(para_sents)
        paragraph_end_indexes.add(len(sentences) - 1)

    pauses: list[int] = []
    for i in range(max(0, len(sentences) - 1)):
        pauses.append(paragraph_pause_ms if i in paragraph_end_indexes else sentence_pause_ms)

    return sentences, pauses


def estimate_seconds(text: str, rate: str = NARRATOR_BASE_RATE) -> float:
    """Rough duration estimate for Thai TTS at a given rate."""
    # Empirical baseline: Premwadee at 0% reads roughly 2.5 Thai chars/sec.
    base_cps = 2.5
    rate_multiplier = 1.0
    m = re.match(r"^([+-]?\d+(?:\.\d+)?)\s*%$", rate.strip())
    if m:
        pct = float(m.group(1))
        rate_multiplier = 1.0 + pct / 100.0  # -15% -> 0.85 (slower)
    return len(text) / (base_cps * rate_multiplier)
