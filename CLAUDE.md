# CLAUDE.md — thai-novel project context

Read by any AI assistant working on this project. Read top to bottom on session start; it covers what the project is, the current architecture, the decisions you must not undo, and the authoring rules.

> **TL;DR.** Cinematic Thai audiobook pipeline. `in/ep0.json` is the non-rendered story bible and prompt handoff. `in/epNN.json` files are source episodes with exactly one image each. `./generate` groups up to 10 source episodes into one MP4 at `novels/<series>-ep01-ep10/output/final.mp4`. Pure Python + ffmpeg, no Node, no Chrome. Edge-tts for narration, OpenAI/Codex-generated library images by workflow, local SDXL as fallback, libx264 for encoding.

---

## 1. What this project IS

- A **cinematic Thai audiobook pipeline**, not animation.
- Output: YouTube-bound MP4s, default 1280×720 @ 24 fps, with up to 10 source episodes per publication video.
- Narration + atmosphere are the product. Visuals are **one cinematic anchor per source episode**.
- New-story workflow: one shared poster for YouTube posts, then one OpenAI/Codex-generated image per episode saved into `library/visuals/backgrounds/`.
- In grouped videos, the poster is not the only video image; the video changes to the current episode image at each episode boundary.
- Target: **MacBook Pro Apple Silicon, M2 Pro 32 GB**. Everything runs locally.

## What this project is NOT

- Not a slideshow tool.
- Not action-heavy or visually busy.
- Not English-first. Narration is Thai. Image prompts are English (SDXL/CLIP handle English much better).
- Not Cloud-based. Not Node/Remotion-based (was, no longer — see §3).

---

## 2. Architecture — 5 stages, pure Python + ffmpeg

```
ep0 story bible + epNN JSON specs
   │
   ├──► Stage 1  Narrate         edge-tts, 3 parallel, content-cached per sentence
   │              pythainlp segmentation + mood-aware pauses + loudnorm
   │              → cache/<id>/blocks/*.wav
   │
   ├──► Stage 2  Images          OpenAI/Codex-generated library refs by default
   │              Local SDXL fallback via diffusers+MPS when JSON uses prompt
   │              → cache/<id>/anchors/*.png  (and promotions to library/)
   │
   ├──► Stage 3  Compile timeline    Python dataframe-y shaping
   │              → cache/<id>/timeline.json
   │
   ├──► Stage 4  Compose video       Pure ffmpeg, NO Chrome, NO JavaScript
   │              PIL pre-renders cards (logo, episode title, chapter cards, end card)
   │              4 parallel ffmpeg segment builds, content-addressed cache
   │              Stream-copy concat → raw.mp4
   │
   └──► Stage 5  Final mux           ffmpeg loops fixed background.mp3 + sidechain + loudnorm
                  libx264 crf 28 tune=stillimage (not VideoToolbox — see §3)
                  → novels/<id>/output/final.mp4
```

Stages 1–3 are content-addressable cached. Edit one sentence → only that sentence re-synthesizes, only the affected segment rebuilds, ~40s total turnaround.

---

## 3. Decisions you must NOT undo (real history, real reasons)

These come from rounds of "we tried it and learned":

| Decision | Why it sticks |
| --- | --- |
| **No Remotion, no Node, no Chrome** | Was using Remotion 4.x for compositing. Removed because: (a) Chrome rendering was 10× slower than ffmpeg for static images, (b) `calculateMetadata` was unreliable across point releases, (c) `node_modules/` added 700 MB. Pure ffmpeg gets us to ~3 min renders. `package.json`, `tsconfig.json`, `remotion.config.ts`, `remotion/`, `scripts/render.mjs` — all deleted. **Don't add them back.** |
| **libx264 crf 28 tune=stillimage, NOT VideoToolbox** | VideoToolbox is 3× faster but produces visibly muddy output at the bitrates we target (~7 MB/min). libx264 with `tune=stillimage` is purpose-built for slow-motion content and looks materially better. |
| **Default resolution: 1280×720 @ 24 fps** | 1080p30 produced 400+ MB files and added ~30s of render. 720p24 with static frames lands at ~14 MB for 9 minutes. Bump to 1920×1080 in JSON if needed. |
| **One image per source episode** | New workflow: each `epNN.json` has exactly one chapter and one visual anchor. Each episode image must look like an episode key visual: summarize that episode, show the relevant characters/settings, and include exactly one readable title set for the story name and episode title, with no duplicate title layer, logo, signature, random text, or watermark. `./generate` groups up to 10 source episodes, so a publication video contains up to 10 episode images. |
| **Grouped video sequence** | Start with spoken welcome `ยินดีต้อนรับเข้าสู่ช่อง T H A I Novel ขอให้สนุกกับการรับฟังครับ` while showing the channel image. Then for each source episode: speak `เรื่อง {story_name} ตอนที่ N {ep_title}`, show that episode's image, and read that episode's narration. Repeat through at most 10 episodes. |
| **Grouped description context** | A grouped `description.txt` must include episode titles, short descriptions, and a character relationship tree for the included episodes. Put paste-ready Thai tree text in `project.description_context`: previous relationships, what changes in this episode/group, latest relationship status, and small details for characters who appear. |
| **All images: `motion: "static"`** | The composer (Stage 4) **does not implement motion**. The field is kept in the schema for future, but currently every preset (`slow_zoom_in`, etc.) renders identically to `static`. Setting motion has zero render effect today — just keeps the spec future-proof. |
| **Subtitles default OFF** | `subtitles.enabled = false` in schema default + example. Overlay text crowded the cinematic frames. SRT is still exported next to `final.mp4` (upload as YT captions). |
| **Chapter title cards default OFF** | `Chapter.show_title_card = false`. This is an AUDIOBOOK — listeners are not looking at the screen, so a silent ~4s card between chapters is dead air. A previous attempt to narrate the chapter title on top of the card was rolled back: the user explicitly wants chapter transitions to be seamless audio. Keep chapter count low rather than re-enabling the card. Set `true` per chapter only for deliberate visual interludes. |
| **Logo welcome card: full-screen edge-to-edge** | `render_logo_splash` uses cover semantics — scales the logo to fill the entire 720×1280 frame. The user's 1672×941 logo is 16:9, so it fills cleanly with no crop. No gradient backdrop, no welcome text. |
| **Concurrency = 4 (was 3)** | Static images + 720p drop Chrome-equivalent worker RAM from 5 GB → 3.5 GB. 4 ffmpeg workers × 3.5 GB = 14 GB peak, safe on 32 GB. |
| **Library is never deleted by `./clean`** | Library backgrounds are real GPU output (~5s each). Treated as user content. `./clean --library` flag was REMOVED; if you really need to drop one: `rm library/visuals/backgrounds/<name>.png` by hand. |
| **Smart library short-circuit by image_key** | `library/visuals/backgrounds/_index.json` stores the image_key (sha256 of prompt+seed+style+size). On next run, generated assets reuse only if the key matches; edit the prompt in JSON → it regenerates. Manually/Codex-created images already in `library/visuals/backgrounds/` without metadata are treated as curated assets and reused instead of regenerated. |
| **Auto-normalizer on `load_episodes()`** | Cowork-generated specs sometimes use mood aliases (`melancholic`, `sad`), motion aliases (`slow_pan_left`, `fade_in`), or forget block IDs. The normalizer fixes these silently with INFO logs. See `src/thai_novel/spec.py:_normalize_episode_dict`. |
| **Default voice: th-TH-PremwadeeNeural** | Warm Thai female narrator. Rate −10%. |
| **One fixed background track** | `library/audio/background.mp3` is the only music/ambience bed. It loops across intro and narration and ducks under speech. Episode JSON has no background-audio keys; a missing file stops the render. |
| **No `./novel preview`** | Removed when Remotion was removed. The render loop is fast enough that "edit JSON → `./generate` → play MP4" works as the preview. For audio-only checks, run `./novel narrate` and listen to `cache/<id>/blocks/*.wav` directly. |

---

## 4. File layout

```
thai-novel/
├── novel                          # CLI wrapper (executable bash)
├── generate                       # shorthand for `./novel render` (executable)
├── clean                          # cache/output cleanup (executable)
├── pyproject.toml                 # Python project — see §5
├── .gitignore                     # cache/, models/, in/, library/visuals/backgrounds/, etc.
│
├── in/                            # your JSON specs go here
│   ├── ep0.json                   # StoryBible: whole-story summary + poster/episode prompts, skipped by render
│   ├── README.md                  # field-by-field schema reference
│   ├── template.example.json      # annotated template with FIXED/PER_SERIES/PER_EPISODE _doc tags
│   └── epNN.json                  # renderable source episode, exactly one image/chapter
│
├── novels/<id>/                   # per-episode outputs (gitignored)
│   ├── output/
│   │   ├── final.mp4              # THE FINAL VIDEO
│   │   ├── subtitles.srt          # for YT manual captions
│   │   ├── chapter_markers.txt    # paste into YT description
│   │   └── description.txt        # YouTube description template
│   └── _work/                     # intermediate raw.mp4 (pre-mux)
│
├── library/                       # reusable, user-curated assets (NEVER deleted by ./clean)
│   ├── visuals/
│   │   ├── backgrounds/           # SDXL-generated + promoted (_index.json with image_key)
│   │   ├── characters/            # if you ever generate per-character portraits
│   │   ├── overlays/              # channel_logo.png lives here
│   │   └── luts/
│   ├── audio/
│   │   ├── background.mp3         # fixed CC0 real-piano Chopin recording
│   │   ├── SOURCE.md              # recording provenance and CC0 evidence
│   │   └── sfx/                   # optional cue effects referenced by library://sfx/...
│   └── fonts/                     # optional .ttf/.otf override; macOS defaults work
│
├── cache/                         # content-addressed (gitignored; `./clean` wipes)
│   ├── narration/                 # per-sentence WAVs by hash
│   ├── images/                    # per-prompt PNGs by hash
│   └── <episode-id>/
│       ├── blocks/                # per-block stitched WAVs
│       ├── anchors/               # upscaled per-chapter PNGs
│       ├── cards/                 # PIL-rendered cards (logo, title, chapter, end)
│       ├── segments/              # per-block ffmpeg segments (content-addressed)
│       ├── timeline.json
│       └── narration.json
│
├── models/                        # SDXL Turbo weights (~6.5 GB, auto-downloaded)
│   └── diffusers-hf/
│
├── src/thai_novel/                # the Python pipeline
│   ├── cli.py                     # Typer CLI — doctor/validate/new/narrate/images/render
│   ├── spec.py                    # Pydantic schema + auto-normalizer
│   ├── hashing.py                 # content-hash helpers (narration_key, image_key)
│   ├── narration/                 # Stage 1
│   │   ├── segment.py             # pythainlp Thai sentence segmentation
│   │   ├── synthesize.py          # edge-tts parallel, sem=3, per-sentence cache
│   │   ├── stitch.py              # concat + mood pauses + loudnorm
│   │   └── align.py               # whisper-mlx (optional) or even-distribute fallback
│   ├── images/                    # Stage 2
│   │   ├── library.py             # library:// ref resolution + promotion + metadata
│   │   ├── generate.py            # SDXL Turbo via diffusers+MPS
│   │   └── upscale.py             # Real-ESRGAN if available, else Lanczos
│   ├── timeline/                  # Stage 3
│   │   └── __init__.py            # compile_timeline()
│   ├── compose/                   # Stage 4 (pure ffmpeg, replaces former remotion/)
│   │   ├── __init__.py            # compose_video()
│   │   └── cards.py               # PIL renderers for logo/title/chapter/end cards
│   └── encode/                    # Stage 5
│       └── __init__.py            # finalize() — mux + loudnorm + SRT + chapter_markers + description
│
├── .claude/skills/
│   └── json-transform/
│       └── SKILL.md               # Project skill: create OR transform Thai stories to JSON
│
├── intro/                         # user's pre-existing logo (intro/logo.png)
├── music/                         # user's pre-existing music
├── cover/                         # user's pre-existing cover art
├── voices/                        # legacy Piper TTS .onnx voice models (optional fallback)
├── manuscripts/                   # user's raw Thai chapter sources (.json or .md)
├── LICENSE                        # Apache 2.0
└── README.md                      # complete project README (~250 lines, 11 sections)
```

---

## 5. CLI reference

The one command 99% of the time:

```bash
./generate [<id>]                 # full pipeline, batches active epNN into groups of up to 10
./generate --group-size 1         # one MP4 per source episode
./generate --skip-narrate         # text unchanged → skip Stage 1
./generate --skip-images          # images unchanged → skip Stage 2
```

Sub-commands (`./novel <verb>` — same venv, finer control):

| Verb | What |
| --- | --- |
| `./novel doctor` | Check Python ≥ 3.11, ffmpeg + VideoToolbox, Thai font, folder layout |
| `./novel validate [<id>]` | Schema check + pacing warnings, no render |
| `./novel new <id>` | Scaffold `in/<id>.json` from `in/template.example.json` |
| `./novel narrate [<id>]` | Stage 1 only — synthesize WAVs to `cache/<id>/blocks/` |
| `./novel images [<id>] [--force]` | Stage 2 only — resolve/generate visual anchors |
| `./novel render [<id>]` | Full pipeline (alias for `./generate`) |
| `./novel version` | Print version |

Cleanup:

```bash
./clean              # wipe cache/ + novels/<id>/output/ + novels/<id>/_work/ + remotion/public/
./clean --models     # also wipe SDXL weights (~6.5 GB redownload)
./clean --yes        # skip confirmation
```

**`./clean` NEVER deletes**: `library/`, `models/` (unless `--models`), `.venv/`, `in/`, `manuscripts/`, `intro/`, `music/`, `voices/`, `cover/`.

The CLI auto-skips files in `./in/` whose name:
- starts with `_` (archived/disabled), e.g. `_old-draft.json`
- ends with `.example.json` (templates), e.g. `template.example.json`
- is exactly `ep0.json` (story bible / prompt handoff, not renderable)

---

## 6. Schema essentials

The full schema lives in `src/thai_novel/spec.py`. Quick reference:

### Episode (top-level)

```jsonc
{
  "project":          { "id", "title", "episode?", "series?", "short_description", "description_context?", "resolution", "fps", ... },
  "tts":              { "voice", "rate", "pitch", "mood_pauses", ... },           // FIXED
  "image_generation": { "engine", "steps", "guidance", "seed", "gen_*", ... },   // FIXED
  "visual_style":     { "base_prompt", "negative_prompt", "color_grade" },        // FIXED
  "characters":       { "male_lead": {...}, "female_lead": {...} },               // PER_SERIES
  "subtitles":        { "enabled": false, ... },                                   // FIXED, default off
  "intro":            { "channel_name", "logo_ref" },                             // FIXED
  "chapters":         [ Chapter, Chapter, ... ],                                   // PER_EPISODE — the story
  "end_card":         { "next_episode_title", "message" }                          // PER_EPISODE
}
```

### Chapter

```jsonc
{
  "id": "ch_01",
  "title": "<Thai chapter title>",
  "show_title_card": false,         // default off — audiobook, silent cards are dead air
  "title_card_duration_sec": 4,     // only used if show_title_card is true
  "visual_anchor": {              // ONE per chapter (default)
    "prompt": "<English SDXL prompt>",
    "save_to_library_as": "<series>_ep<N>_<slug>",
    "motion": "static",
    "color_grade": "warm_cozy"
  },
  "narration_blocks": [ NarrationBlock, ... ]
}
```

### NarrationBlock

```jsonc
{
  "id": "ch01_b1",                // required; auto-normalizer fills if missing
  "mood": "cozy",                  // strict Literal — see §7
  "duration_hint_sec": 180,        // advisory; actual = TTS output length
  "narration": "<Thai prose, 1500–3000 chars>",
  "subtitle_emphasis": ["นที"],   // only used if subtitles enabled
  "anchor_override": { ... }       // OPTIONAL per-scene image — use sparingly
}
```

### Mood vocabulary (STRICT Pydantic Literal)

`cozy`, `funny`, `romantic`, `playful`, `tense`, `melancholy`.

**Auto-normalizer aliases** (accepted silently; canonical preferred):
- `melancholic`, `sad` → `melancholy`
- `happy` → `playful`
- `calm`, `neutral` → `cozy`
- `angry`, `scared` → `tense`

### Motion presets (STRICT but ignored)

`slow_zoom_in`, `slow_zoom_out`, `pan_left`, `pan_right`, `parallax_depth`, `subtle_handheld`, `ken_burns_combo`, `static`.

**Auto-normalizer aliases**: `slow_pan_left/right` → `pan_left/right`, `fade_in/out` → `static`, `none/""` → `static`.

The composer (Stage 4) ignores motion in the current build. All chapter images render static. The field is kept for schema future-proofing.

### Color grades

`warm_cozy`, `cool_night`, `golden_hour`, `melancholy_blue`, `playful_pop`, `neutral`. Set once at `visual_style.color_grade`. Per-anchor `color_grade` override allowed.

---

## 7. The hard rules (don't break)

1. **Never edit generated files.** `cache/<id>/timeline.json`, `cache/<id>/blocks/*.wav`, `novels/<id>/output/final.mp4` — all regenerated. Edit `in/<id>.json`.

2. **Narration blocks: 1500–3000 Thai chars; source episodes target 8000–10000 Thai chars.** A block should stay in the 1500–3000 Thai-char sweet spot, but one `epNN` source episode should contain enough blocks to reach roughly 8000–10000 Thai chars. Recap is limited to 1-3 short sentences per episode, woven into an active scene only when the remembered fact changes a present decision. Never reuse recap wording or add generic summary paragraphs. Before delivery, scan all active episodes for duplicate paragraphs, sentences, and long shared fragments. Run `segment_thai_with_pauses()` and split natural paragraphs until no TTS segment exceeds 400 chars, without making every sentence its own paragraph. `./novel validate` warns at <800 or >4000 per block.

3. **One visual anchor per source episode.** Each `epNN.json` should have exactly one chapter and one visual anchor. Put multiple narration blocks under that chapter when needed. The image itself should be an episode key visual/poster: all relevant visible characters, the dominant setting/event, and exactly one readable title set and no duplicate title layer, logo, signature, random text, or watermark.

4. **Prefer OpenAI/Codex pre-generated images.** `in/ep0.json` must include `open_ai_instruction` with exact output paths and prompts. Generate the shared whole-story poster to `novels/poster/background.png`, and each episode key visual to `library/visuals/backgrounds/<series-slug>_epNN.png`. Episode JSON may keep `prompt` + `save_to_library_as`; when the file already exists, `./generate` reuses it and skips local image generation.

5. **Total unique anchors per source episode: exactly 1.** Publication videos may contain up to 10 images because they group up to 10 source episodes.

   Grouped publication video flow:
   - Welcome narration: `ยินดีต้อนรับเข้าสู่ช่อง T H A I Novel ขอให้สนุกกับการรับฟังครับ`; visual is the channel image/logo.
   - Episode title narration: `เรื่อง {story_name} ตอนที่ N {ep_title}`.
   - Episode narration: show `library://backgrounds/<series-slug>_epNN` while reading.
   - Repeat title + episode image + narration for the next episode until the 10-episode group ends.
   - Grouped `description.txt`: include up to 10 episode titles + short descriptions, then a `ผังความสัมพันธ์และตัวละครที่เกี่ยวข้อง` section sourced from `project.description_context`. Write it as an indented character tree that covers prior relationships, current changes, latest status, and small character details for everyone who appears in the group.

6. **Image prompts are English; narration is Thai.** Don't mix.

7. **Series-prefixed image slugs.** `shadow_dynasty_ep45`, not `cafe`. Prevents collisions across series.

8. **Don't auto-run `./generate`.** The user invokes renders; AI assistants write the JSON.

---

## 8. Authoring rules for Thai romantic-comedy narration

When helping the user write or transform an episode:

- **Describe small physical details.** "เปลือกตาข้างหนึ่งกระตุกเล็กน้อย" beats "เธอประหม่า". Specificity is cozy.
- **Let comedy be deadpan.** Describe chaos in a calm tone — that contrast is the humor.
- **Inner thoughts are gold.** What characters notice but don't say is the whole romance.
- **Awkward pauses are storytelling.** Long sentences with embedded asides read aloud better than choppy short ones in Thai.
- **Resist resolving things.** A scene that ends with characters *not* admitting their feelings is more romantic than one that does.
- **Narrator is third-person.** No fourth-wall breaks. Render dialogue as reported speech (`"เขาบอกว่า ..."`).

The voice and rate are tuned for this tone — adapt the writing, don't change the TTS settings to fit a different tone.

---

## 9. Library system + smart caching

| Layer | What | When invalidated |
| --- | --- | --- |
| **SDXL output cache** | `cache/images/<hash>.png` | Prompt, seed, style, size, engine changes (image_key recomputed) |
| **Library promotion** | `library/visuals/backgrounds/<name>.png` + entry in `_index.json` with `image_key` | Manually deleted; smart short-circuit re-generates if stored `image_key` ≠ current |
| **Per-anchor upscale** | `cache/<id>/anchors/<chapter_id>.png` | Anchor signature changes |
| **Compose segments** | `cache/<id>/segments/<name>_<hash>.mp4` | Image, audio, duration, size, fps, or grade changes |
| **Narration sentences** | `cache/narration/<hash>.wav` | Sentence text, voice, rate, pitch changes |

The smart library short-circuit means: edit a prompt in JSON → that specific anchor regenerates. Same prompt → instant library reuse, zero SDXL cost.

---

## 10. Performance characteristics (M2 Pro 32 GB, default 720p24)

| Operation | Time |
| --- | --- |
| `./novel doctor` | <1s |
| `./novel validate` | <1s |
| Stage 1 narrate (9 min episode, cold) | ~60–90s |
| Stage 1 narrate (warm, all cached) | ~5s |
| Stage 2 images (5 new SDXL anchors, model loaded) | ~25s |
| Stage 2 images (all library hits) | ~3s |
| Stage 3 compile timeline | <1s |
| Stage 4 compose (5 chapters, 8 segments, 4 parallel) | ~30–60s |
| Stage 5 mux (libx264 crf28) | ~30–60s |
| **Cold render, 9-min episode** | **~3–5 min** |
| **Warm render (one paragraph edited)** | **~40s** |
| **Cold render, 30-min episode** | **~10–15 min** |
| **Batch of 10 episodes** | **~40 min sequential** |

Output specs (720p24 default): ~7 MB/min, H.264 + AAC stereo, -14 LUFS YouTube target.

---

## 11. Available skill: json-transform

`.claude/skills/json-transform/SKILL.md` is a project-local Claude Code skill with two modes:

| Trigger | Mode |
| --- | --- |
| "/json-transform create a story about X" | **A** — invent story from premise, write Thai prose, output JSON |
| "/json-transform transform my .md files at <folder>" | **B** — read existing prose files, reshape into JSON without inventing new content |

Either way the output is a valid `in/<name>.json` ready for `./generate`. The skill knows the schema, the normalizer aliases, the voice guidance, and the library convention.

It auto-loads for any Claude Code session opened in this repo — no install step. To use from a different agent (Cowork, etc.), point that agent at the same `SKILL.md` path.

---

## 12. Files to read on session start

In this order:

1. **This file (`CLAUDE.md`)** — orient on the architecture and decisions
2. **`README.md`** — user-facing project overview (11 sections, ~550 lines)
3. **`in/template.example.json`** — canonical schema with inline FIXED/PER_SERIES/PER_EPISODE tags
4. **`in/README.md`** — field-by-field schema reference
5. **`.claude/skills/json-transform/SKILL.md`** — the authoring skill (read before helping with episode JSON)
6. **`src/thai_novel/spec.py`** — Pydantic source of truth, including the `_normalize_episode_dict()` aliases
7. **`in/ep0.json` if present** — story bible and prompt handoff
8. **Any existing `in/epNN.json`** — for series-voice and character continuity

---

## 13. Common operations cheatsheet

```bash
# Render the current spec
./generate

# Validate without rendering
./novel validate <name>

# Just synthesize narration (audio-only check)
./novel narrate <name>
ls cache/<name>/blocks/      # listen to these to QA voice/pacing

# Generate / promote images only
./novel images <name>

# Force regeneration of all images (ignore smart cache + library hit)
./novel images <name> --force

# Nuke caches and outputs to start fresh
./clean

# Reset to empty (keeps library + models + venv)
./clean --yes

# Manually drop a promoted background you want to redo
rm library/visuals/backgrounds/<name>.png
./generate          # next run regenerates that one anchor
```

---

## 14. Things explicitly NOT done (don't add without consensus)

- **No motion implementation in compose.** Schema accepts motion presets but Stage 4 ignores them. Adding zoompan would re-introduce complexity. Discuss before implementing.
- **No subtitle overlay rendering.** Disabled by default after we tried it and decided the cinematic frame should breathe. SRT export remains.
- **No automatic preview server.** Removed with Remotion. The fast warm-render path serves as the preview.
- **No multi-image per scene (slideshow).** Stays one anchor per chapter; per-scene `anchor_override` is the escape hatch and stays capped at ≤4 per episode.
- **No subprocess.exec / shell strings.** Always use `asyncio.create_subprocess_exec` with argv-list to dodge shell injection (and a pre-existing project hook).
- **No `node_modules/`, `package.json`, `remotion/`, `scripts/render.mjs`.** These were removed in the pure-ffmpeg rewrite; don't re-add.
- **No `./novel preview`.** Same reason. The warm-render loop is the preview.
- **No editing `manuscripts/` files programmatically.** That's the user's source material.
