"""
Transform `in/ตอนที่ N - X.md` files for the ปาฏิหาริย์ใต้ร่มธรรม series
into valid episode JSONs at `in/pdtm-epNN.json`.

Source format (audited from all 17 files):
  # ปาฏิหาริย์ใต้ร่มธรรม
  ## ตอนที่ N — <episode title>
  *(optional italic context note)*
  ### <chapter title>
  ... Thai prose ...
  ### <chapter title>
  ... Thai prose ...

Mode B rules (per the skill):
  - DON'T rewrite the prose. Map it 1:1 into narration_blocks.
  - Split chapters whose prose > 3000 chars at paragraph boundaries.
  - Detect mood from Thai emotional cue words.
  - Detect characters by scanning prose for their names.
  - Generate English visual_anchor.prompts per chapter (subject/setting/lighting only — no style words).
  - Copy ALL FIXED fields from in/template.example.json.

Series: ปาฏิหาริย์ใต้ร่มธรรม (subtitle: เด็กวัดพันล้าน)
Characters from synopsis: ปราชญ์, พิม, หลวงพ่อพรหม, บอย, ภาคิน, คุณวิทยา, ครูวิภา, คุณยายแสง, เสี่ยสมพล
"""

from __future__ import annotations

import json
import re
import glob
from copy import deepcopy
from pathlib import Path


# ─────────────────────────────────────────────────────────────────────────────
# Series-wide constants (PER_SERIES)
# ─────────────────────────────────────────────────────────────────────────────

SERIES_NAME = "ปาฏิหาริย์ใต้ร่มธรรม"
SERIES_SUBTITLE = "เด็กวัดพันล้าน"
SERIES_THEME = "drama coming-of-age + light romance — feel-good inspiration"
SERIES_ID_PREFIX = "pdtm"  # ปาฏิหาริย์ใต้ร่มธรรม → pdtm

# Character bible — from synopsis section "ตัวละครหลัก"
CHARACTERS = {
    "lead_male": {
        "id": "prach",
        "name": "ปราชญ์ (ปรัชญา บุญรอด)",
        "name_th": "ปราชญ์",
        "appearance": "Thai teenage boy, lean build, close-cropped dark hair, calm watchful eyes, simple temple-boy clothes, gentle hands trained for herbal medicine",
        "appearance_th": "เด็กชายไทย ผอมเพรียว ผมสั้น ดวงตาสงบลึก ใบหน้านุ่มนวล ใส่เสื้อผ้าเรียบๆ สีอ่อน มือเรียวที่ดูฉลาดเกินวัย",
        "wardrobe": "loose cream cotton shirt and dark trousers when at the temple; second-hand school uniform in town",
        "voice_notes": "narrator only — Prach speaks softly, polite, uses ผม/ครับ",
        "reference_image": "library://characters/prach",
    },
    "lead_female": {
        "id": "phim",
        "name": "พิม (พิมพ์มาดา)",
        "name_th": "พิม",
        "appearance": "Thai teenage girl, mid-teens, glossy shoulder-length dark hair, bright sharp eyes, confident posture, daughter-of-wealth grooming",
        "appearance_th": "สาวไทยวัยรุ่น ผมตรงสีดำสนิทยาวประบ่า ตาคมใส รอยยิ้มมั่นใจ ลุคลูกสาวคหบดี",
        "wardrobe": "private school uniform with crisp white blouse; designer casual at home",
        "voice_notes": "narrator only — Phim is sharp-tongued, uses หนู/ค่ะ, soft-hearted underneath",
        "reference_image": "library://characters/phim",
    },
    "monk_master": {
        "id": "luangpor",
        "name": "หลวงพ่อพรหม",
        "name_th": "หลวงพ่อพรหม",
        "appearance": "elderly Thai Buddhist monk, lean tanned face deeply lined, shaved head, bright still eyes, simple ochre robes, hands of a traditional herbalist",
        "appearance_th": "หลวงพ่อพระแก่ ร่างผอมบาง ผิวคล้ำแดด ใบหน้ามีริ้วรอย ดวงตาใสนิ่ง ห่มจีวรสีกรัก",
        "wardrobe": "saffron monastic robes, simple alms bowl, herbal pouch",
        "voice_notes": "narrator only — Luangpor speaks slowly with monastic vocabulary (อาตมา / โยม)",
    },
    "best_friend": {
        "id": "boy",
        "name": "บอย",
        "name_th": "บอย",
        "appearance": "Thai teenage boy, slightly chubby, messy hair, glasses, hoodie-and-headphones look, IT-geek energy",
        "appearance_th": "เด็กชายไทยวัยรุ่น รูปร่างท้วม ผมยุ่ง สวมแว่น ลุคเด็กเนิร์ดสายไอที",
        "wardrobe": "school uniform with a hoodie underneath; phone always in hand",
        "voice_notes": "narrator only — Boy is the loyal IT geek friend, casual ภาษา",
    },
    "rival": {
        "id": "pakin",
        "name": "ภาคิน",
        "name_th": "ภาคิน",
        "appearance": "Thai teenage boy, athletic build, sharp-featured handsome, expensive watch, confident sneer of a rich kid",
        "appearance_th": "เด็กชายไทยวัยรุ่น รูปร่างสูงสมส่วน ใบหน้าหล่อคม นาฬิกาแพง รอยยิ้มเย่อหยิ่งของลูกคนรวย",
        "wardrobe": "tailored school uniform, designer sneakers, branded backpack",
        "voice_notes": "narrator only — Pakin's antagonist, sharp and mocking tone",
    },
    "phims_father": {
        "id": "withaya",
        "name": "คุณวิทยา",
        "name_th": "คุณวิทยา",
        "appearance": "Thai man in his 50s, sharp business suit, silver-streaked hair, cold appraising eyes, financier's poise",
        "appearance_th": "ชายไทยวัย 50 ใส่สูทเข้ม ผมเริ่มขาว ดวงตาเย็นชา ลุคนักการเงินผู้สำเร็จ",
        "wardrobe": "tailored navy or charcoal suit, leather briefcase, gold watch",
        "voice_notes": "narrator only — cold, precise, uses ผม/ครับ",
    },
    "teacher": {
        "id": "kru_wipa",
        "name": "ครูวิภา",
        "name_th": "ครูวิภา",
        "appearance": "Thai woman in her 40s, warm face, hair tied back simply, modest blouse, kind teacher's smile",
        "appearance_th": "ครูหญิงไทยวัย 40 ใบหน้าอบอุ่น ผมเก็บเรียบ แต่งกายเรียบร้อย รอยยิ้มของครูที่ห่วงใย",
        "wardrobe": "modest blouse and skirt, glasses on a chain, well-worn satchel",
        "voice_notes": "narrator only — Kru Wipa is warm and encouraging, uses ครู/ค่ะ",
    },
    "old_lady": {
        "id": "yai_saeng",
        "name": "คุณยายแสง",
        "name_th": "คุณยายแสง",
        "appearance": "elderly Thai woman, thin and small, white hair in a simple bun, weathered hands, traditional sarong",
        "appearance_th": "หญิงชราไทย รูปร่างผอมเล็ก ผมขาวเก็บเป็นมวย มือเหี่ยวย่น นุ่งโจงกระเบนแบบโบราณ",
        "wardrobe": "simple cotton blouse and sarong, herbal basket always nearby",
        "voice_notes": "narrator only — Yai Saeng is gentle and slow-spoken, uses ยาย/จ้ะ",
    },
    "villain": {
        "id": "sia_somphon",
        "name": "เสี่ยสมพล",
        "name_th": "เสี่ยสมพล",
        "appearance": "Thai man in his 50s, stocky build, gold chain visible at collar, smile that doesn't reach the eyes, developer's swagger",
        "appearance_th": "ชายไทยวัย 50 รูปร่างล่ำ สวมสร้อยทอง รอยยิ้มที่ไม่ถึงดวงตา ลุคนายทุนหน้าเลือด",
        "wardrobe": "polo shirts with brand logos, gold chains, luxury SUV keys",
        "voice_notes": "narrator only — Sia Somphon is the antagonist real-estate developer",
    },
}

# Searchable name → character id  (for visual_anchor.characters detection)
NAME_TO_ID = {
    "ปราชญ์": "prach",   "ปรัชญา": "prach",
    "พิม": "phim",       "พิมพ์มาดา": "phim",
    "หลวงพ่อพรหม": "luangpor", "หลวงพ่อ": "luangpor",
    "บอย": "boy",
    "ภาคิน": "pakin",
    "คุณวิทยา": "withaya",
    "ครูวิภา": "kru_wipa", "ครู": "kru_wipa",
    "คุณยายแสง": "yai_saeng", "ยายแสง": "yai_saeng",
    "เสี่ยสมพล": "sia_somphon",
}


# Mood cue words → mood label. First match wins; ordered by specificity.
MOOD_CUES = [
    ("melancholy", ["มรณภาพ", "สูญเสีย", "ร้องไห้", "น้ำตา", "คำสั่งเสีย", "งานศพ",
                    "ฝนพรำ", "เหงา", "เศร้า", "เสียดาย", "อาลัย", "วันสุดท้าย"]),
    ("tense",      ["โกรธ", "ขัดแย้ง", "ทะเลาะ", "ศัตรู", "ผิดหวัง", "อันตราย",
                    "บีบบังคับ", "ขู่", "นายทุน", "สมคบ", "แอบ"]),
    ("romantic",   ["จับมือ", "หัวใจ", "ใกล้ชิด", "แอบมอง", "ห่วงใย", "ตื้นตัน",
                    "หน้าแดง", "เขิน", "คิดถึง"]),
    ("funny",      ["ขำกลิ้ง", "หัวเราะ", "ปนเป", "งี่เง่า", "สะดุ้ง", "ตลก"]),
    ("playful",    ["แซว", "ล้อ", "เล่นพิเรน", "ยิ้ม", "สดใส", "ตื่นเต้น"]),
]


# ─────────────────────────────────────────────────────────────────────────────
# English visual_anchor prompts (hand-crafted per chapter title hint)
# ─────────────────────────────────────────────────────────────────────────────

# Map common chapter-title keywords → generic scene prompt template.
# Fallback when no keyword matches: a temple/character generic scene.
SCENE_TEMPLATES = {
    "แม่น้ำ":          "an elderly Thai monk standing at a misty riverbank at dawn, looking down at a tiny bundle caught against tree roots, mist over the water, soft early light",
    "ต้นโพธิ์":        "an elderly Thai monk and a small Thai boy sitting under a huge old bodhi tree in a quiet rural temple courtyard at afternoon, dappled light through leaves",
    "ตำรายา":          "an elderly Thai monk reading an ancient palm-leaf medicine manuscript by oil-lamp light at night inside a wooden temple kuti, a young boy beside him watching with rapt attention",
    "สมุนไพร":         "wooden temple workbench covered with dried Thai medicinal herbs and roots in small bamboo trays, golden afternoon light through a window, hands sorting them",
    "คอมพิวเตอร์":     "a Thai teenage boy in a small dim school library at night, hunched over an old desktop computer monitor, soft blue screen glow on his face, stacks of textbooks beside him",
    "ปาฏิหาริย์":      "an elderly Thai monk and a teenage boy quietly tending to a sick child on a temple mat, herbal poultices in clay bowls, family watching anxiously, soft warm lamp light",
    "หลวงพ่อ":         "elderly Thai monk on a simple wooden meditation platform inside an old temple hall, dim morning light, peaceful expression, hands folded in his lap",
    "มรณภาพ":          "a quiet temple hall at dusk, monks and villagers in mourning whites kneeling around a covered bier, candles flickering, somber stillness",
    "คำสั่งเสีย":      "an elderly dying Thai monk on a temple sleeping mat speaking softly to a kneeling teenage boy, oil lamp glow, deep evening blue beyond the window",
    "งานศพ":           "a rural Thai temple cremation ceremony at evening, white-robed monks chanting, villagers in white kneeling, lanterns and incense smoke",
    "โรงเรียน":        "a Thai teenager in white school uniform walking through the open courtyard of a large city high school, other students passing in groups, morning sun",
    "เมือง":           "a Thai teenager with a small backpack stepping off a provincial bus into a crowded Bangkok bus terminal, morning rush, slightly overwhelmed expression",
    "เพื่อน":          "two Thai teenagers walking together along a school corridor at break time, chatting easily, sunlight slanting through tall windows",
    "ห้องสมุด":        "a quiet Thai school library at afternoon, rows of bookshelves, an old computer on a small desk near the window, a teenage boy sitting alone working",
    "ตลาดหุ้น":        "a Thai teenager studying a glowing screen showing stock market charts in a dim school library at night, focused expression, notebook of handwritten formulas beside him",
    "อัลกอริทึม":      "a Thai teenager typing intensely on an old computer keyboard at midnight in a dim library, code on the screen reflected in his glasses-less calm eyes, single lamp",
    "ความโลภ":         "a Thai teenager sitting cross-legged in a dark temple hall at night, eyes closed in meditation, a single oil lamp casting long shadows, expression of quiet reckoning",
    "เงิน":            "an envelope of cash being placed quietly on a temple altar at dusk by an unseen hand, gold-leaf statue dim in background, intimate warm light",
    "วัด":             "rural Thai forest temple at golden hour, modest wooden buildings, large bodhi tree, a small monk and a teenage boy in the courtyard, river behind them",
    "บูรณะ":           "construction workers and villagers raising a new wooden temple roof in midday sun, scaffolding and timber, dust in the air, sense of communal effort",
    "ความลับ":         "a Thai teenager alone in a dim school library late at night, single old computer monitor casting blue light, quiet uneasy expression",
    "หัวใจ":           "two Thai teenagers on a quiet school rooftop at dusk, standing close at the railing not quite touching, city lights beginning to glow beyond, soft tender mood",
    "บ้าน":            "interior of a wealthy modern Bangkok living room at evening, expensive furniture, polished floors, a teenage girl standing in the foreground looking out at her teenage friend in the doorway",
    "ที่ดิน":          "a tense outdoor confrontation at a rural temple — a stocky middle-aged Thai businessman with sleek suv talks to villagers near the temple gate, monk watching quietly from a distance",
    "ศัตรู":           "a Thai schoolboy in a dim corridor face to face with a richer schoolboy who is sneering at him, other students watching from the edges, tense afternoon light",
    "เกม":             "shadowy figures meeting in a hotel lobby at night, briefcase being passed, conspiratorial tone, low warm lighting",
    "ความจริง":        "an emotional confession between a Thai teenage boy and girl in an empty school classroom at dusk, golden window light, both standing close, breath held",
    "ความรัก":         "a Thai teenage boy and girl quietly holding hands on a temple bench at sunset, river behind them, warm golden light, peaceful intimacy",
    "คำสัญญา":         "a young Thai man in modest clothes standing in a freshly restored temple courtyard at morning, monks and villagers gathered around, sunlight on the new roof, sense of fulfillment",
    "อนาคต":           "a young Thai man standing at sunrise on a hilltop overlooking his home temple in the valley below, river winding past it, soft golden new-day light",
}


def detect_scene_prompt(title: str, first_chars: str = "") -> str:
    """Pick the best-matching scene template from chapter title keywords."""
    haystack = (title + " " + first_chars[:200]).lower()
    for keyword, prompt in SCENE_TEMPLATES.items():
        if keyword in haystack:
            return prompt
    # Generic fallback
    return ("an elderly Thai monk and a Thai teenage boy in a quiet rural forest temple courtyard, "
            "afternoon golden light filtering through trees, peaceful traditional atmosphere")


def detect_mood(text: str) -> str:
    """First-match-wins mood detection from cue words."""
    for mood, cues in MOOD_CUES:
        if any(cue in text for cue in cues):
            return mood
    return "cozy"


def detect_characters(text: str, max_chars: int = 4) -> list[str]:
    """Scan prose for character names; return up to max_chars unique ids."""
    found: list[str] = []
    for name, cid in NAME_TO_ID.items():
        if name in text and cid not in found:
            found.append(cid)
            if len(found) >= max_chars:
                break
    return found


def split_into_blocks(prose: str, target_chars: int = 2200, max_chars: int = 3000,
                      min_tail_chars: int = 1200) -> list[str]:
    """
    Split a chapter's prose into ~target_chars blocks at paragraph boundaries.
    Never exceeds max_chars per block. Preserves paragraph breaks (\n\n).

    Tail-merge: if the final block ends up shorter than min_tail_chars and
    merging it back into the previous block stays under max_chars + 20% slack,
    merge. This avoids pacing-warning short tail blocks like "next chapter
    starts here in 300 chars".
    """
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", prose) if p.strip()]
    blocks: list[list[str]] = [[]]
    block_len = 0
    for para in paragraphs:
        para_len = len(para)
        # If adding this paragraph would exceed max, start a new block
        # (unless the current block is empty — single huge paragraph must go in alone)
        if blocks[-1] and block_len + para_len > max_chars:
            blocks.append([])
            block_len = 0
        # If we've passed target and there's natural break coming, start fresh
        if blocks[-1] and block_len >= target_chars:
            blocks.append([])
            block_len = 0
        blocks[-1].append(para)
        block_len += para_len + 2  # +2 for "\n\n"

    joined = ["\n\n".join(b) for b in blocks if b]

    # Tail-merge: if the last block is small, fold it back into the prior one.
    if len(joined) >= 2 and len(joined[-1]) < min_tail_chars:
        merged_len = len(joined[-2]) + 2 + len(joined[-1])
        if merged_len <= int(max_chars * 1.20):
            joined[-2] = joined[-2] + "\n\n" + joined[-1]
            joined.pop()

    return joined


# ─────────────────────────────────────────────────────────────────────────────
# Transform one .md → episode dict
# ─────────────────────────────────────────────────────────────────────────────


def transform_episode(md_path: Path, template: dict) -> dict:
    raw = md_path.read_text(encoding="utf-8")

    # Episode meta
    m = re.search(r"^##\s+ตอนที่\s+(\d+)\s*[—\-–]\s*(.+?)\s*$", raw, re.MULTILINE)
    if not m:
        raise RuntimeError(f"no '## ตอนที่ N — title' header in {md_path.name}")
    ep_num = int(m.group(1))
    ep_title = m.group(2).strip()

    # Strip italic context notes like *(รวมเนื้อหาเดิม...)*
    raw = re.sub(r"^\s*\*\([^)]+\)\*\s*$", "", raw, flags=re.MULTILINE)

    # Split into chapters by ### headings (everything after the first ### up to the next ###)
    sections = re.split(r"^###\s+(.+?)\s*$", raw, flags=re.MULTILINE)
    # sections layout: [preamble, ch1_title, ch1_body, ch2_title, ch2_body, ...]
    if len(sections) < 3:
        raise RuntimeError(f"no '### ' chapter headings in {md_path.name}")
    chapter_pairs = list(zip(sections[1::2], sections[2::2]))

    # Build episode dict from template (deep copy)
    ep = deepcopy(template)

    # PER_EPISODE fields
    ep_id = f"{SERIES_ID_PREFIX}-ep{ep_num:02d}"
    ep["project"]["id"] = ep_id
    ep["project"]["title"] = ep_title
    ep["project"]["series"] = SERIES_NAME
    ep["project"]["episode"] = ep_num
    ep["project"]["theme"] = SERIES_THEME
    # Vary the seed per episode for image diversity but stay deterministic
    ep["image_generation"]["seed"] = 20240115 + ep_num

    # Intro narration auto-format:
    #   - channel_name stays "T-H-A-I Novel" (FIXED — copied from template)
    #   - title_narration is auto-generated by the pipeline as
    #     "{series} ตอนที่ {N} {title}" — don't override here
    ep["intro"].pop("title_narration", None)
    # channel_name already comes from template; do NOT overwrite with series name

    # PER_SERIES — character bible (overwrites template's example characters)
    ep["characters"] = deepcopy(CHARACTERS)

    # Build chapters
    chapters = []
    for i, (ch_title, ch_body) in enumerate(chapter_pairs, start=1):
        ch_title = ch_title.strip()
        ch_body = ch_body.strip()
        # Skip empty bodies
        if not ch_body:
            continue

        # Slug for save_to_library_as — use the chapter index, deterministic
        slug = f"{SERIES_ID_PREFIX}_ep{ep_num:02d}_ch{i:02d}"

        # Visual anchor — derive from chapter title + first 200 chars of body
        prompt = detect_scene_prompt(ch_title, ch_body)
        # Detect characters appearing in this chapter (not used outside the anchor)
        ch_char_ids = detect_characters(ch_body)

        # Color grade — pick based on chapter title cues
        color_grade = "warm_cozy"
        if any(w in ch_title for w in ("มรณภาพ", "คำสั่งเสีย", "งานศพ", "เศร้า")):
            color_grade = "melancholy_blue"
        elif any(w in ch_title for w in ("ศัตรู", "ความลับ", "เกมสกปรก", "มรสุม")):
            color_grade = "cool_night"
        elif any(w in ch_title for w in ("เงิน", "หัวใจ", "ความรัก", "อนาคต", "ปาฏิหาริย์", "คำสัญญา")):
            color_grade = "golden_hour"

        # Split prose into narration blocks
        block_texts = split_into_blocks(ch_body, target_chars=2200, max_chars=3000)
        narration_blocks = []
        for j, btext in enumerate(block_texts, start=1):
            mood = detect_mood(btext)
            narration_blocks.append({
                "id": f"ch{i:02d}_b{j}",
                "mood": mood,
                "duration_hint_sec": min(280, max(120, len(btext) // 12)),  # rough
                "narration": btext,
            })

        chapters.append({
            "id": f"ch_{i:02d}",
            "title": ch_title,
            "show_title_card": False,
            "title_card_duration_sec": 4,
            "visual_anchor": {
                "prompt": prompt,
                "save_to_library_as": slug,
                "motion": "static",
                "color_grade": color_grade,
                "characters": ch_char_ids,
            },
            "narration_blocks": narration_blocks,
        })

    ep["chapters"] = chapters

    # End card — next episode pointer
    next_ep_num = ep_num + 1
    ep["end_card"] = {
        "show": True,
        "duration_sec": 8,
        "next_episode_title": f"ตอนที่ {next_ep_num} — โปรดติดตามตอนต่อไป",
        "message": f"ขอบคุณที่รับฟังตอนที่ {ep_num} ของซีรีส์ {SERIES_NAME} หากชื่นชอบ อย่าลืมกดติดตามเพื่อรับฟังตอนต่อไป",
    }

    return ep


# ─────────────────────────────────────────────────────────────────────────────
# Strip _doc fields recursively (template has them; output shouldn't)
# ─────────────────────────────────────────────────────────────────────────────


def strip_doc(obj):
    if isinstance(obj, dict):
        return {k: strip_doc(v) for k, v in obj.items() if not k.startswith("_")}
    if isinstance(obj, list):
        return [strip_doc(x) for x in obj]
    return obj


# ─────────────────────────────────────────────────────────────────────────────
# Main loop
# ─────────────────────────────────────────────────────────────────────────────


def main():
    tmpl = strip_doc(json.loads(Path("in/template.example.json").read_text(encoding="utf-8")))
    tmpl_ep = tmpl[0] if isinstance(tmpl, list) else tmpl

    md_files = sorted(glob.glob("in/ตอนที่ *.md"))
    print(f"Found {len(md_files)} episode .md files")

    for md_path in md_files:
        p = Path(md_path)
        try:
            ep = transform_episode(p, tmpl_ep)
        except Exception as e:
            print(f"  ✗ {p.name}: {e}")
            continue
        out_path = Path("in") / f"{ep['project']['id']}.json"
        out_path.write_text(json.dumps([ep], ensure_ascii=False, indent=2), encoding="utf-8")
        ch_count = len(ep["chapters"])
        block_count = sum(len(c["narration_blocks"]) for c in ep["chapters"])
        char_count = sum(len(b["narration"]) for c in ep["chapters"] for b in c["narration_blocks"])
        print(f"  ✓ {p.name} → {out_path.name}  ({ch_count} ch, {block_count} blocks, {char_count:,} chars)")


if __name__ == "__main__":
    main()
