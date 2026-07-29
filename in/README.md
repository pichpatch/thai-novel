# `./in/` — story bible and episode spec JSON

Start each new story with `ep0.json`, then add one or more `epNN.json` files.
From the project root, run `./generate` and the active episodes are grouped
into publication videos of up to 10 source episodes per MP4.

## Reference and control files

| File | What |
| --- | --- |
| `ep0.json` | Story bible and prompt handoff. Contains the whole-story summary, poster prompt, shared image style prompt, characters, and per-episode image prompts. It is skipped by render. |
| `template.example.json` | A template with **inline `_doc` comments** explaining every field, tagged by tier: `FIXED` (set once per channel) vs `PER_SERIES` (set once per series) vs `PER_EPISODE` (changes each episode). Copy this when authoring a new episode. |

`ep0.json`, `*.example.json`, and files starting with `_` are skipped by
auto-pick. To work from the template:

```bash
cp in/template.example.json in/ep01.json
$EDITOR in/ep01.json   # fill in PER_EPISODE fields
./generate
```

The `_doc` / `_note` / `_README` / `_characters_doc` fields in the template
are JSON comments — Pydantic silently ignores any key starting with `_`,
so you can leave them in your edited copy or strip them out, either way works.

## New story workflow

1. Fill `in/ep0.json` with the whole-story summary, prompts, and `open_ai_instruction`.
2. Generate the shared story poster with OpenAI/Codex and save it as `novels/poster/background.png`. Reuse this same poster for every YouTube post for the story. The poster should summarize the whole story, not just one episode.
3. For each source episode, generate one image with OpenAI/Codex and save it as:

```text
library/visuals/backgrounds/<series-slug>_epNN.png
```

Each episode image should look like an episode key visual/poster: summarize that
episode, show the relevant characters and setting/event, and include readable
text for `{story_name}` plus `ตอนที่ N {ep_title}`.

4. In each `epNN.json`, use one chapter only and reference the image:

```jsonc
"visual_anchor": {
  "ref": "library://backgrounds/<series-slug>_epNN",
  "motion": "static"
}
```

5. Run `./generate`. The pipeline groups up to 10 source episodes into one MP4.

## Grouped video sequence

For a grouped video such as `ep01` through `ep10`, the visible and spoken flow is:

```text
1. Spoken: ยินดีต้อนรับเข้าสู่ช่อง T H A I Novel ขอให้สนุกกับการรับฟังครับ
   Visual: channel image / channel logo

2. Spoken: เรื่อง {story_name} ตอนที่ 1 {ep01_title}
   Visual: episode title moment

3. Spoken: ep01 narration
   Visual: library://backgrounds/<series-slug>_ep01

4. Spoken: เรื่อง {story_name} ตอนที่ 2 {ep02_title}
   Visual: episode title moment

5. Spoken: ep02 narration
   Visual: library://backgrounds/<series-slug>_ep02
```

The pattern repeats until the grouped video reaches 10 episodes. The poster is
not the only video image; it is the shared story/posting asset.

For YouTube, each grouped output should provide:

- The same shared poster for every post in the story
- One `final.mp4`
- One `description.txt` containing up to 10 episode titles, short descriptions,
  a character relationship tree, current-state notes, and small details for
  characters who appear in that group

## Two ways to provide many source episodes

**Multiple files** — drop several `.json` files into `./in/`. They render
in **alphabetical order**, then group into publication videos:

```
in/
  ep0.json                    ← story bible, skipped
  ep01.json                   ← video 1
  ep02.json                   ← video 1
  ...
  ep10.json                   ← video 1
  ep11.json                   ← video 2
  _draft.json                 ← underscore-prefixed = ignored
```

**Multiple episodes in one file** — wrap them in a JSON array:

```jsonc
[
  { "project": { "id": "devil-cafe-ep01", ... }, "chapters": [...] },
  { "project": { "id": "devil-cafe-ep02", ... }, "chapters": [...] }
]
```

Both forms can be mixed — file order first, then array order within each file.
The CLI flattens everything into one queue and chunks it into groups of up to
10 source episodes. Use `./generate --group-size 1` to force one MP4 per source
episode.

Inactive specs are prefixed with underscore (`_old-idea.json`) so the
CLI skips them without you having to delete or move them.

Generated episode filenames should be plain `epNN.json` with a two-digit
episode number only. Do not put the story title in the filename. The
`project.id` inside the JSON still controls the output folder under `novels/`.
In automatic batch mode, grouped output ids become `<series-slug>-ep01-ep10`,
`<series-slug>-ep11-ep20`, and so on.

---

## Top-level Episode fields

| Field | Type | Required | Default |
| --- | --- | --- | --- |
| `project` | object | yes | — |
| `tts` | object | no | edge-tts / af_heart equivalent |
| `image_generation` | object | no | hyper-sdxl-8step, MLX, 1024×576 |
| `visual_style` | object | no | cinematic romantic anime |
| `characters` | dict | no | `{}` |
| `subtitles` | object | no | Sarabun, karaoke reveal |
| `chapters` | array | **yes** | exactly one chapter per source episode |
| `end_card` | object | no | shown for 8s |

---

## `project`

```jsonc
{
  "id": "devil-cafe-ep01",          // slug-safe; becomes the output filename
  "title": "...",                    // human-readable
  "series": "ร้านกาแฟของคุณปีศาจ",   // optional grouping
  "episode": 1,                      // optional
  "short_description": "...",         // Thai YouTube description paragraph
  "description_context": "...",       // optional Thai relationship tree + character notes for grouped description.txt
  "language": "th",
  "theme": "romantic comedy fantasy",
  "resolution": "1920x1080",
  "target_duration_min": 32          // advisory; actual = sum of audio
}
```

## `tts`

```jsonc
{
  "engine": "edge-tts",                       // or "piper" (uses voices/*.onnx)
  "voice": "th-TH-PremwadeeNeural",
  "rate": "-10%",
  "pitch": "+0Hz",
  "sentence_pause_ms": 320,
  "paragraph_pause_ms": 800,
  "mood_pauses": {
    "cozy":      { "sentence_pause_ms": 380 },
    "tense":     { "sentence_pause_ms": 320, "paragraph_pause_ms": 950, "rate_override": "-12%" },
    "funny":     { "sentence_pause_ms": 220, "rate_override": "-5%" },
    "romantic":  { "sentence_pause_ms": 460, "rate_override": "-15%" },
    "melancholy":{ "sentence_pause_ms": 500, "rate_override": "-18%" }
  }
}
```

Per-mood overrides let you slow down for tense or romantic peaks and speed up for funny beats.
Narration text may use explicit newlines to control audiobook pacing: normal
sentence boundaries use `sentence_pause_ms`, while a newline between narration
paragraphs uses `paragraph_pause_ms`.

## `image_generation`

```jsonc
{
  "engine": "hyper-sdxl-8step",
  "backend": "mlx",                  // or "coreml", "diffusers-mps"
  "steps": 8,                        // 8 = better quality; use hyper-sdxl-4step for drafts
  "guidance": 0,
  "seed": 20240115,                  // pin for reproducibility
  "gen_width": 1024,                 // 16:9 native generation
  "gen_height": 576,
  "upscaler": "realesrgan"           // or "lanczos", "none"
}
```

## `characters`

Used by image prompts (appearance + wardrobe are interpolated), subtitle
emphasis (names get bolded automatically), and — when `reference_image` is set —
by **IP-Adapter** for face/look consistency across episodes. The dict key is
free-form; `male_lead` and `female_lead` are convention.

```jsonc
{
  "male_lead": {
    "id":              "thana",                                 // NEW — used by visual_anchor.characters; defaults to slot name
    "name":            "ธนภัทร",
    "name_th":         "ธนภัทร",                                 // NEW (optional) — for bilingual docs
    "appearance":      "young Thai man, mid-20s, short side-parted dark hair, narrow nose, warm brown eyes",
    "appearance_th":   "ชายไทยอายุปลายยี่สิบกว่า ผมสั้นแสกข้าง...", // NEW (optional)
    "wardrobe":        "navy linen button-down, slim trousers, leather strap watch",
    "reference_image": "library://characters/thana"             // NEW — IP-Adapter ref; resolves to library/visuals/characters/thana.{png,jpg,webp}
  },
  "female_lead": {
    "id":              "phim",
    "name":            "พิมพ์นารา",
    "appearance":      "beautiful Thai woman, mid-20s, shoulder-length wavy dark hair, sharp bright eyes",
    "wardrobe":        "cream blouse, pencil skirt, single gold serpent ring",
    "reference_image": "library://characters/phim"
  }
}
```

### Character `id` field (NEW)

- **Optional but recommended.** Slug-safe key used by `visual_anchor.characters`.
- Defaults to the slot key if absent — e.g. omitted `id` on `male_lead` is treated as `id="male_lead"`.
- **Stable across episodes.** If you rename a character's `id` mid-series, the IP-Adapter cache invalidates for that character.

### Character `reference_image` field (NEW)

- **Optional.** A `library://characters/<name>` URI pointing at a PNG/JPG/WEBP under `library/visuals/characters/`.
- When **set** AND a chapter lists this character's `id` in `visual_anchor.characters`, the pipeline auto-loads **IP-Adapter Plus SDXL** and conditions on this image → same face every episode.
- When the file is **missing on disk**, the field is silently ignored (the prompt still describes the character; just no IP conditioning).
- **`./clean --refs`** wipes `library/visuals/characters/`. Standard `./clean` preserves it.

### Multi-character scenes

- `visual_anchor.characters` accepts up to **4 ids per scene**. Beyond 4, IP-Adapter quality degrades.
- For tight close-ups, list 1 character. For 2-shot dialogue, list 2. Don't list characters who are not visible in the frame.

## Fixed background audio

Episodes do not contain background-audio keys. The final mux always loops
`library/audio/background.mp3` from the channel intro through the end card and
automatically ducks it under narration. Rendering stops with a clear error if
that file is missing.

## `chapters[]`

New workflow: each source episode has exactly one chapter, and that chapter has
the episode's only visual anchor. Use multiple narration blocks inside the
chapter when the episode is long or mood changes.

```jsonc
{
  "id": "ch_01",
  "title": "ภาพหลักของตอน",
  "show_title_card": false,
  "title_card_duration_sec": 4,
  "visual_anchor": { ... },          // see below
  "narration_blocks": [ ... ]        // see below
}
```

### `visual_anchor`

Either `ref` a library asset OR `prompt` a new one. Not both.

Preferred: generate the image with OpenAI/Codex first, save it in
`library/visuals/backgrounds/`, then use `ref`.

```jsonc
// Library reference (preferred — reuse is success):
{
  "ref": "library://backgrounds/cafe_rainy_night_exterior",
  "motion": "slow_zoom_in",
  "color_grade": "warm_cozy"
}

// New generation, with promotion to library on first render:
{
  "prompt": "small cozy cafe at night, rain on window, warm amber light, cinematic",
  "save_to_library_as": "cafe_rainy_night_exterior",
  "motion": "slow_zoom_in",
  "color_grade": "warm_cozy"
}
```

Motion presets: `slow_zoom_in`, `slow_zoom_out`, `pan_left`, `pan_right`,
`parallax_depth`, `subtle_handheld`, `ken_burns_combo`, `static`.

Color grades: `warm_cozy`, `cool_night`, `golden_hour`, `melancholy_blue`,
`neutral`, `playful_pop`.

### `narration_blocks[]`

```jsonc
{
  "id": "ch01_b1",
  "mood": "cozy",                    // see Mood table in CLAUDE.md
  "duration_hint_sec": 180,          // advisory; actual = TTS output length
  "narration": "...",                // 1500–3000 Thai chars per block is the sweet spot
  "subtitle_emphasis": ["นที"],     // these strings get bolded in subs
  "anchor_override": { ... },        // optional per-block visual swap (rare)
  "sfx_cues": [
    { "at_sec": 12, "ref": "library://sfx/cup_clink", "volume_db": -12 }
  ]
}
```

One `epNN` source episode should target roughly 8,000-10,000 Thai
characters. In practice, write multiple narration blocks until the episode
lands in that range. Recap must stay within 1-3 short sentences per episode,
appear inside an active scene, and affect a present decision. Do not add generic
summary paragraphs or reuse recap wording. Before delivery, scan every active
episode for duplicate paragraphs, sentences, and long shared text fragments.
Run `segment_thai_with_pauses()` and keep every segment at 400 characters or
less. Use paragraph breaks for real thought/action/time turns, not every sentence.

---

## After editing the JSON

```bash
./novel validate            # schema check + pacing warnings
./novel render              # full pipeline → novels/<id>/output/final.mp4
```

That's it. The script regenerates everything, synthesizes narration, generates
or looks up images, renders the video, and muxes the final MP4. Takes 8–12
minutes cold on M2 Pro 32GB; 2–3 minutes warm (after editing).

The render also writes `novels/<id>/output/description.txt`, ready to paste
into YouTube:

```text
เรื่อง {series}
ตอนที่ N {title}

{short_description}

ผังความสัมพันธ์และตัวละครที่เกี่ยวข้อง
{description_context}

ขอบคุณที่รับฟังกันนะครับ
#นิยายเสียง 
```

Use `project.description_context` for a paste-ready Thai relationship tree that explains:

- Relationships carried from previous episodes
- What changes in the current episode or 10-episode publication group
- The latest relationship status after the episode/group
- Small identifying details for characters who appear in the group

Example:

```text
ลูฟี่
├─ โคบี้: ก่อนหน้าเป็นเพื่อนที่แยกทางกัน; ในชุดนี้โคบี้เริ่มฝึกใต้การดูแลของการ์ป; สถานะล่าสุดยังนับถือกันแต่ยืนคนละฝั่งหน้าที่
│  └─ การ์ป: ผู้ฝึกของโคบี้; เป็นปู่ของลูฟี่
└─ โซโล: เริ่มจากการชวนเข้ากลุ่ม; สถานะล่าสุดเป็นเพื่อนร่วมทางและลูกเรือคนแรก
```

---

## `ep0.json` story bible

`ep0.json` validates as a `StoryBible`, not an `Episode`. It should include:

- `whole_story_summary`
- `poster_prompt`
- `episode_image_style_prompt`
- `open_ai_instruction` with exact poster and episode-image output paths/prompts
- `characters`
- `episode_plan[]` with `episode`, `title`, `short_description`, optional
  `description_context`, and `image_prompt`

Validate it with `./novel validate ep0`. Render commands skip it automatically.
