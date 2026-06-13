# `./in/` — episode spec JSON

Drop one or more `.json` files in this folder. Then from the project root
run `./generate` and you'll get `./novels/<id>/output/final.mp4` for each.

## Two reference files (auto-skipped by `./generate`)

| File | What |
| --- | --- |
| `example.json` | A complete working episode (ร้านกาแฟของคุณปีศาจ ตอน 1). Use it to see what a finished spec looks like. |
| `template.example.json` | A template with **inline `_doc` comments** explaining every field, tagged by tier: `FIXED` (set once per channel) vs `PER_SERIES` (set once per series) vs `PER_EPISODE` (changes each episode). Copy this when authoring a new episode. |

Both are skipped by auto-pick (the CLI ignores `*.example.json` and any file
starting with `_`). To work from the template:

```bash
cp in/template.example.json in/ep02.json
$EDITOR in/ep02.json   # fill in PER_EPISODE fields
./generate
```

The `_doc` / `_note` / `_README` / `_characters_doc` fields in the template
are JSON comments — Pydantic silently ignores any key starting with `_`,
so you can leave them in your edited copy or strip them out, either way works.

## Two ways to batch many episodes

**Multiple files** — drop several `.json` files into `./in/`. They render
in **alphabetical order**, one episode at a time:

```
in/
  ep01.json                   ← rendered first
  ep02.json                   ← rendered second
  ep03.json                   ← rendered third
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
The CLI flattens everything into one queue and renders sequentially.

Inactive specs are prefixed with underscore (`_old-idea.json`) so the
CLI skips them without you having to delete or move them.

See `example.json` for a complete worked example: ร้านกาแฟของคุณปีศาจ
ตอนที่ 1, ~32 minutes, 5 chapters.

Ask Cowork: *"fill in `in/ep02.json` for ตอนที่ 2"* and it will
write the whole spec.

Generated episode filenames should be plain `epNN.json` with a two-digit
episode number only. Do not put the story title in the filename. The
`project.id` inside the JSON still controls the output folder under `novels/`.

---

## Top-level Episode fields

| Field | Type | Required | Default |
| --- | --- | --- | --- |
| `project` | object | yes | — |
| `tts` | object | no | edge-tts / af_heart equivalent |
| `image_generation` | object | no | hyper-sdxl-8step, MLX, 1024×576 |
| `visual_style` | object | no | cinematic romantic anime |
| `characters` | dict | no | `{}` |
| `audio` | object | no | rain ambience, cozy piano |
| `subtitles` | object | no | Sarabun, karaoke reveal |
| `chapters` | array | **yes** | — |
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
    "funny":     { "sentence_pause_ms": 220, "rate_override": "-5%" },
    "romantic":  { "sentence_pause_ms": 460, "rate_override": "-15%" },
    "melancholy":{ "sentence_pause_ms": 500, "rate_override": "-18%" }
  }
}
```

Per-mood overrides let you slow down for romantic peaks and speed up for funny beats.

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

## `audio`

```jsonc
{
  "music_bed": {
    "default":   "library://music/cozy_piano_01_ai",
    "by_mood": {
      "romantic": "library://music/strings_warm_02_ai",
      "funny":    "library://music/playful_uke_01_ai"
    },
    "volume_db": -22,
    "crossfade_ms": 1500,
    "duck_during_dialogue_db": -6   // sidechain duck during narration
  },
  "ambience": {
    "default": "library://ambience/rain_soft_ai",
    "volume_db": -28
  }
}
```

## `chapters[]`

Each chapter has its own visual anchor and one or more narration blocks.

```jsonc
{
  "id": "ch_01",
  "title": "คืนฝนตกที่ร้านกาแฟ",
  "show_title_card": true,
  "title_card_duration_sec": 4,
  "visual_anchor": { ... },          // see below
  "narration_blocks": [ ... ]        // see below
}
```

### `visual_anchor`

Either `ref` a library asset OR `prompt` a new one. Not both.

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
  "narration": "...",                // 1500–3000 Thai chars is the sweet spot
  "subtitle_emphasis": ["นที"],     // these strings get bolded in subs
  "music_override": null,            // optional per-block music swap
  "ambience_override": null,
  "anchor_override": { ... },        // optional per-block visual swap (rare)
  "sfx_cues": [
    { "at_sec": 12, "ref": "library://sfx/cup_clink", "volume_db": -12 }
  ]
}
```

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

ขอบคุณที่รับฟังกันนะครับ
#นิยายเสียง 
```

---

## A note on the array form

The current `example.json` uses an array `[ {...} ]` containing one episode.
That's intentional — the array form is forward-compatible with multi-episode
files, and the schema treats `{...}` and `[{...}]` identically. Either is fine.
