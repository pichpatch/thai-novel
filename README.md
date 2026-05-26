# thai-novel

> Cinematic AI-native Thai audiobook production pipeline.
> Drop a JSON spec in `./in/`, run `./novel render`, get a 30–40 minute YouTube episode in `./novels/<id>/output/`.

Built for **MacBook Pro M2 Pro / 32 GB**, narration-first, atmosphere-heavy. Romantic comedy slow-burn is the target genre. Visuals are *cinematic anchors*, not scene snapshots — a single image can hold the screen for 2–5 minutes with camera motion, subtitles, music, and sound design doing the work.

---

## The one-line idea

```
in/<spec>.json  ──►  ./novel render  ──►  novels/<id>/output/final.mp4
```

5–15 generated images per episode. ~8–12 minutes cold render. ~2–3 minutes warm (after editing a paragraph).

---

## Quick start

```bash
# 1. (Optional) look at / edit the example spec
$EDITOR in/example.json

# 2. Generate the video
./generate
```

That's it. `./generate` does everything:

1. On first run, creates `./.venv` and installs Python deps (~30s).
2. Synthesizes narration via edge-tts (cached per sentence).
3. Resolves / generates visual anchors (SDXL Turbo, cached per prompt+seed).
4. Composes the video via ffmpeg (cards → segments → concat, 4 parallel).
5. Muxes music + ambience + loudnorm via ffmpeg.
6. Exits cleanly. Your shell `PATH` is untouched.

You get `./novels/<id>/output/final.mp4` when it's done — typically **2–3 minutes** end-to-end for a 9-minute episode (warm cache), **4–5 minutes** cold.

### Batch mode — multiple JSONs at once

Drop several `.json` files into `./in/` and run `./generate` — it processes
all of them sequentially (one episode at a time, since each render already
saturates 3 Remotion workers). Episodes are rendered in **alphabetical
order of filename**, so prefix them if you care:

```
in/
  01_devil-cafe-ep01.json    # rendered 1st
  02_devil-cafe-ep02.json    # rendered 2nd
  03_devil-cafe-ep03.json    # rendered 3rd
  _draft.json                # underscore-prefixed → ignored
```

Each JSON file can itself be a single Episode OR an array of Episodes —
both forms are flattened into one queue and rendered in order. A summary
table is printed at the end:

```
Batch summary: 3/3 succeeded
┏━━━━━━━━━━━━━━━━━┳━━━━━━━━┳━━━━━━━━━━┳━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ Episode         ┃ Status ┃ Duration ┃ Size    ┃ Output                    ┃
┡━━━━━━━━━━━━━━━━━╇━━━━━━━━╇━━━━━━━━━━╇━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━┩
│ devil-cafe-ep01 │ ✓      │ 1820s    │ 245 MB  │ novels/.../final.mp4      │
│ devil-cafe-ep02 │ ✓      │ 1750s    │ 232 MB  │ novels/.../final.mp4      │
│ devil-cafe-ep03 │ ✓      │ 1840s    │ 251 MB  │ novels/.../final.mp4      │
└─────────────────┴────────┴──────────┴─────────┴───────────────────────────┘
```

A failed episode is reported but the batch continues unless you pass
`--stop-on-error`. The cache means later runs are fast — only the changed
sentences re-synthesize, only the changed anchors re-generate.

### About venv "activation"

You don't need to `source .venv/bin/activate` and you don't need to
`deactivate` afterwards. `./generate` invokes `.venv/bin/thai-novel`
by its full path, so the venv's Python is used without ever modifying
your shell. When the script exits, there's nothing to clean up.

---

## How it works

Pure-Python pipeline — no Node, no Chrome, no JavaScript runtime:

```
JSON ─┬─► narration stream   (edge-tts WAVs, parallel, content-cached)
      ├─► visual stream      (≤15 PNGs from library + SDXL Turbo @ 1024×576)
      ├─► cards stream       (PIL pre-renders logo splash, title cards, end card)
      └─► timeline stream    (plan: segments with image + audio + duration)
                             │
                             ▼
                   ffmpeg segment build (4 parallel)
                             │
                             ▼
                   stream-copy concat -> raw.mp4
                             │
                             ▼
                   ffmpeg mux (music + ambience + loudnorm) -> final.mp4
```

Everything is **content-addressable cached**. Identical inputs → identical hash → instant cache hit. Editing one paragraph re-synthesizes one sentence, rebuilds one segment, restitches.

---

## Project layout

```
thai-novel/
├── novel                          # the one command you run
├── in/
│   ├── example.json               # full ep1 of ร้านกาแฟของคุณปีศาจ (~32 min)
│   └── README.md                  # JSON schema reference
├── novels/<id>/output/            # per-episode rendered MP4s (gitignored)
├── library/                       # reusable assets (grows across episodes)
│   ├── visuals/{backgrounds,characters,overlays,luts}
│   ├── audio/{ambience,music,sfx}
│   └── fonts/
├── cache/                         # content-addressed; safe to delete (gitignored)
├── models/                        # SDXL Turbo + Whisper weights (auto-fetched)
├── remotion/src/                  # Remotion compositions (TypeScript)
├── src/thai_novel/                # Python pipeline (Typer CLI + async)
├── manuscripts/                   # raw chapter sources (your existing 45 chapters)
├── voices/                        # Piper .onnx models (kept as TTS fallback)
├── music/, intro/, cover/         # pre-existing user assets (kept for reference)
└── docs/
```

---

## CLI reference

```bash
# The one-shot you'll run 99% of the time:
./generate [<id>]               # full pipeline → ./novels/<id>/output/final.mp4

# Granular sub-commands (./novel = same venv, finer control):
./novel doctor                  # check Node ≥22, Python ≥3.11, ffmpeg+VideoToolbox
./novel new <id>                # scaffold in/<id>.json from in/example.json
./novel validate [<id>]         # schema check + pacing warnings (no rendering)
./novel narrate [<id>]          # synthesize narration WAVs only
./novel images [<id>] [--force] # resolve/generate visual anchors only
./novel preview [<id>]          # remotion studio on :3000 (live preview)
./novel render [<id>]           # same as ./generate but assumes venv ready

# Skip stages if their cache is up to date (warm iteration mode):
./generate --skip-narrate       # text unchanged; only re-renders video
./generate --skip-narrate --skip-images   # only re-renders timeline → video
```

The `<id>` argument is optional when exactly one `.json` is in `./in/`. To keep multiple specs around, prefix the inactive ones with `_` (e.g. `_old-draft.json`) — the CLI ignores those.

---

## Build phases

| Phase | What ships | Status |
| --- | --- | --- |
| **A** | Scaffold, schema, CLI (`doctor`, `validate`, `new`), example.json, archive of old pipeline | **done** |
| **B** | Narration: pythainlp segmentation, parallel edge-tts (3 concurrent), loudness normalization, Whisper-MLX alignment | next |
| **C** | Images: SDXL Turbo @ 1024×576 via MLX, Real-ESRGAN upscale to 1920×1080, library lookup + promotion | next |
| **D** | Remotion: motion presets (6), subtitle karaoke reveal, music/ambience layers with sidechain ducking, chapter cards | next |
| **E** | Final mux: ffmpeg concat per-chapter chunks, VideoToolbox H.264 encode, loudnorm pass to -14 LUFS, SRT export | next |

---

## Performance targets (M2 Pro 32 GB)

| Metric | Target | Why |
| --- | --- | --- |
| Cold render (35 min episode) | 8–12 min | Quality-first; libx264-quality output via VT |
| Warm render (one paragraph edited) | 2–3 min | One sentence re-synth, one chunk re-render |
| Per-stage parallel cap | 3 | Safe headroom on 32 GB; ~15 GB Remotion peak |
| Generated images per episode | 5–15 | Library reuse handles the rest |
| Image hold duration | 2–5 min per anchor | Camera motion + subs prevent slideshow feel |
| Narration block length | 1500–3000 Thai chars | Cozy pacing baseline |

---

## Requirements

- **macOS** on Apple Silicon (M1 or newer; M2 Pro 32 GB is the design target)
- **Python ≥ 3.11** (`brew install python@3.13` if missing)
- **FFmpeg** (`brew install ffmpeg`)
- A **Thai-capable font** — macOS ships several (Ayuthaya, Thonburi, Sukhothai); auto-detected
- **~10 GB free disk** for SDXL Turbo weights + cache

Run `./novel doctor` to verify everything. No Node, no Chrome, no npm.

---

## Iterating on an episode

Edit `in/<id>.json`, then re-run `./novel render <id>`. The cache means only what changed re-runs:

- Change one sentence → re-narrate that sentence (~2s), re-align that block (~1s), re-render that chapter chunk (~30s).
- Change a visual anchor's prompt → re-generate that image (~1.5s), re-render that chapter chunk.
- Change the music_bed → re-mux the final video (~25s). No re-render.

---

## Authoring rules for AI assistants

See [CLAUDE.md](CLAUDE.md). The short version:

1. Narration blocks are 1500–3000 Thai characters; mood drives pacing.
2. One visual anchor per chapter by default. Per-block `anchor_override` is the exception, not the rule.
3. Prefer `ref: "library://..."` over `prompt`. Library reuse is success.
4. Romance progression matters more than plot progression.

---

## Status

This is the rewrite of the original Python pipeline (PyThaiTTS + per-scene image gen). The old code is gone from the working tree but preserved in git history — `git log --all --full-history -- pipeline.py` will surface it if you ever need to refer back. The new pipeline is cinema-first, narration-led, M2-Pro-tuned.
