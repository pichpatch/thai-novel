# thai-novel

> **Cinematic Thai audiobook production pipeline.**
> Write a JSON. Run `./generate`. Get a 9–40 minute YouTube-ready MP4 in 2–5 minutes. No Chrome, no Node, no slideshow tools — just Python + ffmpeg + your SDXL anime art.

```
in/<spec>.json  ──►  ./generate  ──►  novels/<id>/output/final.mp4
                                       (~14 MB for a 9-min episode at 1280×720)
```

---

## Table of contents

1. [Purpose](#1-purpose)
2. [Setup from scratch (git clone → first render)](#2-setup-from-scratch)
3. [Requirements](#3-requirements)
4. [Assets you need to provide](#4-assets-you-need-to-provide)
5. [How to run + where the MP4 lands](#5-how-to-run--where-the-mp4-lands)
6. [CLI reference](#6-cli-reference)
7. [How it works (the pipeline)](#7-how-it-works)
8. [Dependencies](#8-dependencies)
9. [Writing new episodes](#9-writing-new-episodes)
10. [Troubleshooting](#10-troubleshooting)
11. [License](#11-license)

---

## 1. Purpose

This project is a **narration-first, atmosphere-heavy audiobook pipeline** for long-form Thai romance/comedy/light-novel content destined for YouTube. It's optimized for:

- **MacBook Pro Apple Silicon** (M1 or newer; designed against M2 Pro 32 GB)
- **30–40 minute episodes** at 720p or 1080p
- **5–15 generated images per episode** — visuals are *cinematic anchors*, not scene snapshots
- **2–5 minute renders end-to-end** for a 9-minute episode, ~10–15 minutes for a full 30-minute one

It is **not**:
- A fast slideshow tool — narration quality and audio mix matter
- An animation pipeline — images hold the screen for 2–5 minutes each
- Cloud-based — everything runs locally, all assets stay on your machine

---

## 2. Setup from scratch

This is the full path from a fresh `git clone` to a working render on a Mac.

### 2a. System tools (one-time, ~3 minutes)

```bash
# 1. Install Homebrew if you don't have it (https://brew.sh)

# 2. Install Python 3.11+ and ffmpeg
brew install python@3.13 ffmpeg
```

That's it for system packages. **No Node, no Docker, no global Python packages required.**

### 2b. Clone and bootstrap (one-time, ~5 minutes the first time)

```bash
git clone https://github.com/pichpatch/thai-novel.git
cd thai-novel

# This first run:
#  - creates ./.venv (Python virtual environment, isolated to this folder)
#  - installs Python dependencies (~30s)
#  - then exits early because there's no .json in ./in/ yet
./novel doctor
```

The first `./generate` (or first time SDXL is needed) will additionally:
- **Download SDXL Turbo weights** (~6.5 GB, cached at `./models/diffusers-hf/`)

To enable real image generation, install the optional ML stack:

```bash
.venv/bin/pip install torch diffusers transformers accelerate sentencepiece
```

If you skip this, the pipeline still runs — but it'll produce warm-gradient *placeholder* images with the prompt text overlaid, not real SDXL art. (You can install later and re-run; cached audio/library files are reused.)

### 2c. Verify everything

```bash
./novel doctor
```

You should see all checks pass:

```
┏━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━┳───────────────┓
┃ Check              ┃ Status ┃ Detail        ┃
┡━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━╇───────────────┩
│ Python ≥ 3.11      │ ✓      │ found 3.13.x  │
│ ffmpeg             │ ✓      │ found         │
│ VideoToolbox H.264 │ ✓      │ available     │
│ Thai font          │ ✓      │ ...Ayuthaya   │
│ ./in/              │ ✓      │ ok            │
│ ./novels/          │ ✓      │ ok            │
│ ./library/         │ ✓      │ ok            │
│ ./src/thai_novel/  │ ✓      │ ok            │
└────────────────────┴────────┴───────────────┘
All checks passed.
```

If a check fails, the row tells you exactly what to install.

### 2d. First render

```bash
./generate
```

That's it. ~2–5 minutes later you have:

```
novels/devil-cafe-ep01/output/final.mp4
novels/devil-cafe-ep01/output/subtitles.srt
novels/devil-cafe-ep01/output/chapter_markers.txt
```

---

## 3. Requirements

### System

| | Minimum | Recommended |
| --- | --- | --- |
| OS | macOS on Apple Silicon | macOS on M2 Pro 32 GB |
| Python | 3.11 | 3.13 |
| FFmpeg | any recent build | Homebrew's (includes VideoToolbox) |
| Disk free | ~10 GB | 25 GB |
| RAM | 16 GB | 32 GB |

### Fonts

You need **at least one Thai-capable font** installed. macOS ships several by default — the pipeline auto-detects and uses the first available:

| Order | Path | Status |
| --- | --- | --- |
| 1 | `library/fonts/*.ttf` (your own font) | optional |
| 2 | `/System/Library/Fonts/Supplemental/Sukhothai.ttf` | macOS default |
| 3 | `/System/Library/Fonts/Thonburi.ttc` | macOS default |
| 4 | `/System/Library/Fonts/Supplemental/Ayuthaya.ttf` | macOS default |

**Recommended override**: drop [Sarabun](https://fonts.google.com/specimen/Sarabun) (download from Google Fonts) into `library/fonts/Sarabun-Regular.ttf`. Modern, designed for screen reading.

---

## 4. Assets you need to provide

The pipeline references assets via the `library://` URI scheme. You drop files into `library/` and reference them by name in `in/<your-episode>.json`. The bundled `in/example.json` references **10 assets** — here's exactly what goes where:

### 4a. Music (5 files)

Drop **looping royalty-free instrumental** tracks (60s+ each):

```
library/audio/music/
├── intro_theme.mp3          ← under the welcome card (~5s of audio needed)
├── cozy_piano_01.mp3        ← default music bed (used for chapters by default)
├── playful_uke_01.mp3       ← for funny/playful narration blocks
├── strings_warm_02.mp3      ← for romantic narration blocks
└── piano_rain_01.mp3        ← for melancholy narration blocks
```

`.mp3`, `.wav`, `.ogg`, `.flac` all work. Suggested sources:
- [Pixabay Music](https://pixabay.com/music/) — royalty-free, no attribution required
- [Free Music Archive](https://freemusicarchive.org/) — CC-licensed
- [Incompetech](https://incompetech.com/music/) — Kevin MacLeod's library (attribution required)

### 4b. Ambience (3 files)

Drop **loopable environmental sound** (60s+ each, low-volume background):

```
library/audio/ambience/
├── rain_soft.mp3            ← default ambience (rain on pavement)
├── cafe_quiet.mp3           ← for cozy/funny moods (cafe murmur)
└── rain_window.mp3          ← for melancholy moods (rain on glass)
```

Sources: [SoundEffectsHub](https://soundeffectshub.com), [Pixabay SFX](https://pixabay.com/sound-effects/), or record your own.

### 4c. Logo (1 file)

```
library/visuals/overlays/channel_logo.png
```

**Aspect ratio**: 16:9 is ideal (matches the video). Pure square or other ratios get center-cropped.
**Resolution**: at least 1280×720 (will be downscaled for 720p, used native for 1080p).
**Format**: PNG (transparent or solid background — both work).


### 4d. Backgrounds (auto-generated, optional)

You don't need to provide background images. The example episode references:

```
library://backgrounds/cafe_rainy_night_exterior
```

…which is generated by SDXL Turbo on first run from the prompt in `in/example.json`, then *promoted* to `library/visuals/backgrounds/cafe_rainy_night_exterior.png`. Subsequent runs reuse it instantly.

You can also drop your own hand-drawn or stock backgrounds into `library/visuals/backgrounds/` and reference them via `"ref": "library://backgrounds/<name>"` in the JSON.

### 4e. Quick setup script

Drop your files and you're done:

```bash
# After clone, copy your existing music/logo if you have them:
cp /path/to/your/cozy_music.mp3   library/audio/music/cozy_piano_01.mp3
cp /path/to/your/intro_music.mp3  library/audio/music/intro_theme.mp3
cp /path/to/your/rain.mp3         library/audio/ambience/rain_soft.mp3
cp /path/to/your/logo.png         library/visuals/overlays/channel_logo.png

# Now render:
./generate
```

If any asset is missing, the pipeline skips it gracefully (no music, no ambience, fallback logo card with channel name). You won't get an error — you'll just get a thinner result.

---

## 5. How to run + where the MP4 lands

### One command for everything

```bash
./generate
```

That's the only command 99% of the time. It:
1. Picks the single `.json` in `./in/` (or batches them all if you have several)
2. Synthesizes narration via edge-tts
3. Resolves / generates visual anchors via SDXL Turbo (with library cache)
4. Composes the video via ffmpeg
5. Mixes music + ambience + loudness normalization
6. Writes the final MP4

### Output location

```
novels/<episode-id>/output/
├── final.mp4               ← the video you upload to YouTube
├── subtitles.srt           ← optional Thai captions
└── chapter_markers.txt     ← paste into the YouTube description
```

The `<episode-id>` comes from the `project.id` field in your JSON. For the bundled example: `novels/devil-cafe-ep01/output/final.mp4`.

### Iteration loop

```bash
# Edit a paragraph of narration:
$EDITOR in/example.json

# Re-render — only the changed sentence re-synthesizes; everything else is cached:
./generate
# ~90 seconds later, the updated MP4 is at novels/<id>/output/final.mp4
```

The content-addressable cache means **edits are fast**. Changing one sentence re-synthesizes one sentence (~2s), rebuilds one segment (~3s), and re-muxes the final video (~30s).

---

## 6. CLI reference

### Primary command (the one you use)

```bash
./generate [<id>]                     # full pipeline, one shot
./generate --skip-narrate             # text unchanged → skip narration regen
./generate --skip-images              # images unchanged → skip image regen
./generate --skip-narrate --skip-images   # only re-compose+mux
```

### Sub-commands (`./novel <verb>` — same venv, finer control)

```bash
./novel doctor                        # check Python, ffmpeg, fonts, etc.
./novel validate [<id>]               # schema check + pacing warnings (no render)
./novel new <id>                      # scaffold in/<id>.json from the example
./novel narrate [<id>]                # only synthesize narration WAVs
./novel images [<id>] [--force]       # only resolve/generate visual anchors
./novel render [<id>]                 # same as ./generate
./novel version
```

### Cleanup

```bash
./clean                               # wipe caches + outputs; PRESERVES library + models + your in/
./clean --models                      # also wipe SDXL weights (~6.5 GB redownload — rarely needed)
./clean --yes                         # skip confirmation prompt
```

`./clean` **never** deletes:
- `library/` — your music, logo, backgrounds (curated content)
- `models/` — SDXL weights (expensive to redownload)
- `in/` — your JSON specs
- `.venv/`, `node_modules/` — installs

### Auto-skipped files in `./in/`

Files matching these patterns are ignored by auto-pick:
- Start with `_` (e.g. `_old-draft.json`) — your archive
- End with `.example.json` (e.g. `template.example.json`) — template reference

To work on one explicitly: `./generate <name>` (without the `.json` extension).

---

## 7. How it works

### Pipeline (5 stages)

```
       JSON spec
          │
          ├──────────────────────────────────────────────┐
          │                                              │
          ▼                                              ▼
   [Stage 1] Narrate                                [Stage 2] Images
   pythainlp segments Thai text                     If anchor has `ref://`:
   3 parallel edge-tts calls                          look up library file
   Stitch sentences with mood                       If anchor has `prompt`:
   pauses + loudnorm                                  hash(prompt+seed+style) cache lookup
                                                       miss → SDXL Turbo (~5s on M2 Pro MPS)
                                                       optionally promote → library
          │                                              │
          ▼                                              ▼
   cache/<id>/blocks/*.wav            cache/<id>/anchors/*.png  (upscaled to project size)
          │                                              │
          └──────────────────┬───────────────────────────┘
                             ▼
                  [Stage 3] Compile timeline
                  Python: combine narration durations + anchors + mood cues
                  → cache/<id>/timeline.json
                             │
                             ▼
                  [Stage 4] Compose video
                  Pre-render cards (PIL): logo splash, episode title, chapter cards, end card
                  Build one ffmpeg segment per piece (4 parallel):
                    -loop 1 -i image.png -i audio.wav -tune stillimage -crf 28
                  Stream-copy concat → raw.mp4
                             │
                             ▼
                  [Stage 5] Final mux
                  ffmpeg adds:
                    - music bed (sidechain-ducked under narration)
                    - ambience layer
                    - loudness normalization to -14 LUFS (YouTube standard)
                  → novels/<id>/output/final.mp4
```

### Caching (why the second render is fast)

Every artifact is **content-addressable** — its filename is `sha256(inputs)`. Identical inputs → identical hash → instant cache hit.

| Cache | Location | Invalidated when… |
| --- | --- | --- |
| Narration sentences | `cache/narration/<hash>.wav` | Sentence text, voice, rate, or pitch changes |
| Generated images | `cache/images/<hash>.png` | Prompt, seed, style, size, or engine changes |
| Library promotions | `library/visuals/backgrounds/<name>.png` | Manually deleted; smart hit-check via `_index.json.image_key` |
| Compose segments | `cache/<id>/segments/<name>_<hash>.mp4` | Image, audio, duration, size, or fps changes |

Editing one paragraph re-synthesizes one sentence (~2s), rebuilds one segment (~3s), re-concats (~3s), re-muxes (~30s). **~40 seconds total** instead of starting over.

### Performance targets (M2 Pro 32 GB)

| Episode length | Cold render | Warm render (one paragraph edit) |
| --- | --- | --- |
| 9 minutes (bundled example) | ~2–3 min | ~40s |
| 30 minutes (target series episode) | ~10–15 min | ~60–90s |

### Output specs

| | 720p (default) | 1080p (set `resolution: "1920x1080"`) |
| --- | --- | --- |
| Frame size | 1280×720 | 1920×1080 |
| Frame rate | 24 fps (default) | 24 fps (or 30) |
| Video codec | H.264 (libx264, `tune=stillimage`, CRF 28) | same |
| Audio codec | AAC 96 kbps stereo, 44.1 kHz | same |
| File size | ~7 MB/minute | ~20 MB/minute |
| Loudness | -14 LUFS (YouTube target) | same |

---

## 8. Dependencies

### Required (always installed by `./novel doctor`)

| Package | Purpose |
| --- | --- |
| `typer` | CLI argument parsing |
| `rich` | Terminal UI (tables, progress bars) |
| `pydantic >= 2.10` | JSON schema validation |
| `aiohttp` | Async HTTP (edge-tts) |
| `edge-tts` | Microsoft text-to-speech (Thai voices, free) |
| `pythainlp >= 5.0` | Thai sentence segmentation |
| `soundfile`, `numpy` | WAV I/O and audio math |
| `pyloudnorm` | Loudness normalization (EBU R128) |
| `Pillow >= 11.0` | Card rendering, image upscale |

### Optional (install per use case)

| Package | What you gain | How to install |
| --- | --- | --- |
| `torch`, `diffusers`, `transformers`, `accelerate`, `sentencepiece` | Real SDXL Turbo image generation (~6.5 GB model download on first call) | `.venv/bin/pip install torch diffusers transformers accelerate sentencepiece` |
| `mlx-whisper` | Word-level subtitle timing on the Apple Neural Engine (vs even-distribution fallback) | `.venv/bin/pip install mlx-whisper` |
| `realesrgan-ncnn-vulkan` (binary) | Sharper upscale than Lanczos (`upscaler: "realesrgan"` in JSON) | `brew install <package — check Homebrew for current name>` |

### External (must be on PATH)

- **`ffmpeg`** — `brew install ffmpeg` (Homebrew's build includes the VideoToolbox encoder for hardware-accelerated H.264)
- **`python3.11` or newer** — `brew install python@3.13`

### What is NOT used (anymore)

- ~~Node.js~~ — removed in the pure-ffmpeg rewrite
- ~~Remotion / React / Webpack / headless Chrome~~ — removed
- ~~`node_modules/`~~ — gone, frees ~700 MB

---

## 9. Writing new episodes

### Use the template

```bash
cp in/template.example.json in/02_devil-cafe-ep02.json
$EDITOR in/02_devil-cafe-ep02.json
./generate
```

The template (`in/template.example.json`) has **inline `_doc` comments on every field**, tagged by tier:

- `FIXED` — set once for the channel. Don't change between episodes (voice, image style, music palette, intro logo).
- `PER_SERIES` — set once per series. Same across all episodes (characters, theme).
- `PER_EPISODE` — changes every episode. THIS is where the story lives (`project.id`, `chapters`, `narration_blocks`, `end_card`).

### Schema essentials

See `in/README.md` for the full field reference. Quick version:

```jsonc
{
  "project":    { "id": "...", "title": "...", "episode": N, "resolution": "1280x720", "fps": 24 },
  "tts":        { "voice": "th-TH-NiwatNeural", "rate": "-10%", "mood_pauses": {...} },
  "characters": { "male_lead": {...}, "female_lead": {...} },
  "audio":      { "music_bed": {...}, "ambience": {...} },
  "intro":      { "channel_name": "TH AI Novel", "logo_ref": "library://overlays/channel_logo" },
  "chapters": [
    {
      "id": "ch_01",
      "title": "...",
      "visual_anchor": {
        "prompt": "English description for SDXL",
        "save_to_library_as": "scene_slug",
        "motion": "static"
      },
      "narration_blocks": [
        { "id": "ch01_b1", "mood": "cozy", "narration": "Thai text, 1500-3000 chars" }
      ]
    }
  ],
  "end_card": { "next_episode_title": "...", "message": "..." }
}
```

### Batch mode

Drop multiple `.json` files into `./in/`. They render sequentially:

```
in/
  01_episode-1.json    ← rendered first
  02_episode-2.json    ← rendered second
  _draft.json          ← skipped (underscore prefix)
  template.example.json ← skipped (.example.json suffix)
```

A single `.json` can also be an array of episodes:

```jsonc
[
  { "project": { "id": "ep01", ... }, "chapters": [...] },
  { "project": { "id": "ep02", ... }, "chapters": [...] }
]
```

Both forms get flattened into one render queue. A summary table is printed at the end.

---

## 10. Troubleshooting

| Symptom | Diagnosis | Fix |
| --- | --- | --- |
| `./novel doctor` says "Thai font: not found" | macOS Supplemental fonts aren't installed | System Settings → Fonts → install Supplemental, OR drop a Thai font into `library/fonts/` |
| `./generate` produces placeholder gradient images instead of real anime | `torch` + `diffusers` not installed | `.venv/bin/pip install torch diffusers transformers accelerate sentencepiece` then re-run |
| Render is silent (no music) | Music files missing from `library/audio/music/` | See [§4a](#4a-music-5-files) — drop the referenced .mp3s |
| Subtitle .srt isn't synced word-by-word | `mlx-whisper` not installed (using even-distribute fallback) | `.venv/bin/pip install mlx-whisper` |
| Edge-tts errors with "rate limit" | Too many parallel sentences | The pipeline caps at 3 concurrent already; wait a minute and re-run |
| Render fails at "ffmpeg mux failed" | Asset path issue | Check that all `library://...` refs in your JSON resolve to existing files |
| Want a different voice | Edit `tts.voice` in JSON | See [Microsoft's Thai voice list](https://learn.microsoft.com/en-us/azure/ai-services/speech-service/language-support?tabs=tts#text-to-speech) — `th-TH-NiwatNeural` is the male voice |
| `./clean` accidentally too aggressive | It's not — `./clean` never deletes `library/`, `models/`, or `in/` | Verified by design |
| Random Chrome processes left behind | Stale from old Remotion days, shouldn't happen now | `pkill -9 -f 'chrome-headless-shell'` (one-time) |

---

## 11. License

**Apache License 2.0.** See [`LICENSE`](LICENSE) for the full text.

Practically:
- ✅ **Free for personal use**
- ✅ **Free for commercial use** (publish your YouTube channel, sell merchandise, etc.)
- ✅ **Free to modify and fork**
- ✅ **No royalties owed to the project**
- ❗ You should preserve the copyright notice in any redistribution of the code

**Note on generated content**: the videos this pipeline produces are *your* content. SDXL Turbo output and edge-tts audio are governed by their own licenses (both permit commercial use as of this writing — check current terms). Music, ambience, and logos you drop into `library/` are governed by the licenses of those individual files. The pipeline itself imposes no restrictions on the output.

---

## Credits

- **edge-tts** — Microsoft Cognitive Services (free; networked)
- **SDXL Turbo** — Stability AI ([model card](https://huggingface.co/stabilityai/sdxl-turbo))
- **pythainlp** — open-source Thai NLP library
- **ffmpeg** — the audio/video Swiss army knife
- **Pillow** — image rendering

Built and tested on **MacBook Pro M2 Pro / 32 GB**. Everything runs offline once model weights are cached.
