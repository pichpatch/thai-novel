from __future__ import annotations

from thai_novel.narration.segment import segment_thai_with_pauses


def test_segment_thai_with_pauses_uses_paragraph_pause_after_newline():
    text = (
        "วันนี้กรุงเทพยังปกติ. คนยังรีบไปทำงาน.\n"
        "แล้วแสงขาวก็กลืนเสียงทั้งเมือง."
    )

    sentences, pauses = segment_thai_with_pauses(
        text,
        sentence_pause_ms=250,
        paragraph_pause_ms=900,
    )

    assert len(sentences) == 3
    assert pauses == [250, 900]


def test_segment_thai_with_pauses_preserves_legacy_sentence_pause_without_newline():
    text = "ไฟดับทั้งเมือง. มีนายืนอยู่กลางถนน. ไม่มีใครอธิบายอะไรได้."

    sentences, pauses = segment_thai_with_pauses(
        text,
        sentence_pause_ms=250,
        paragraph_pause_ms=900,
    )

    assert len(sentences) == 3
    assert pauses == [250, 250]
