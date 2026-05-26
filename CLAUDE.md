# Notes for Claude / Cowork: authoring thai-novel episodes

This file is read by any AI assistant working on this project. The rules below
keep the pipeline producing cinematic, narration-first episodes that match the
project's romantic-comedy slow-burn voice.

## What this project IS

- A **cinematic Thai audiobook pipeline**, not an animated anime pipeline.
- Output is 30–40 minute YouTube episodes at 1920×1080.
- Narration and atmosphere are the product. Visuals are **cinematic anchors**.
- Tone: cozy, romantic, funny, slow-paced, emotionally observant.

## What this project IS NOT

- Not action-heavy.
- Not visually busy. A single image can hold the screen for 2–5 minutes.
- Not plot-driven. Relationship progression matters more than plot beats.
- Not English-first. All narration is Thai. Image prompts are English (for SDXL).

---

## The hard rules (do not break these)

1. **Never edit generated files directly.** `index.html`, `narration.txt`,
   compiled timelines, cached WAVs — they're all regenerated. Edit `in/<id>.json`.

2. **One active JSON per pipeline run.** The CLI auto-picks the single non-`_`-prefixed
   `.json` in `./in/`. To keep older specs around, prefix them with `_`.

3. **Narration blocks are 1500–3000 Thai characters.** Shorter = choppy pacing.
   Longer = audience attention drops. The `./novel validate` command warns on
   both extremes.

4. **One visual anchor per chapter by default.** Per-block `anchor_override`
   exists for romantic peaks or comedic close-ups but should be rare. If a
   chapter has more than 2 anchors, the pacing has probably shifted into
   "scene list" territory — pull back.

5. **Prefer `ref: "library://..."` over `prompt`.** Library reuse is the
   success metric. By episode 5 you should be generating ≤3 new anchors per
   episode. If you find yourself writing the same `prompt` twice, promote it
   to the library with `save_to_library_as`.

6. **Total generated images per episode: 5–15.** Anything more and the
   render budget and the art-style consistency suffer.

7. **Image prompts are English; narration is Thai.** SDXL/CLIP-derived models
   handle English prompts much better. Don't mix.

---

## Mood is the central knob

Every `narration_block` has a `mood`. Mood drives:
- TTS pause length and rate (via `tts.mood_pauses`)
- Music selection (via `audio.music_bed.by_mood`)
- Ambience selection
- Subtitle reveal speed
- Color grading

Available moods (defined in `src/thai_novel/spec.py`):

| Mood | When to use | Pace feel |
| --- | --- | --- |
| `cozy` | Default for atmospheric narration | Slow, warm |
| `funny` | Awkward moments, comedic beats | Slightly faster, shorter pauses |
| `romantic` | Emotional peaks, longing | Slowest, longest pauses |
| `playful` | Light teasing, banter | Medium, light |
| `tense` | Conflict, urgency (rare in this genre) | Fast, short |
| `melancholy` | Quiet sadness, rain windows | Very slow, dwelling pauses |

Don't invent new moods — they're typed and validated.

---

## When the user asks for a new episode

1. **Read `in/README.md`** for the current schema (every field documented).
2. **Read `in/example.json`** for a complete worked example
   (ร้านกาแฟของคุณปีศาจ ep1, ~32 min, 5 chapters).
3. **Read `manuscripts/`** if they have raw chapter text already — that's
   the source material for the narration blocks.
4. **Pick the chapter list** — 4–6 chapters for a 30-min episode is the sweet
   spot. Each chapter = one visual anchor + 1–3 narration blocks.
5. **Write the spec JSON** to `in/<id>.json`. Replace the existing file or
   `_`-prefix it. Match narration length to `duration_hint_sec` at roughly
   2.5 Thai characters per second of read time at rate `-10%`.
6. **Tell the user to run** `./novel validate <id>` first, then `./novel render <id>`.
   Don't run it yourself unless they ask.

---

## Writing romantic-comedy narration well

The narration carries the show. A few principles that match the voice the
user wants:

- **Describe small physical details.** "เปลือกตาข้างหนึ่งกระตุกเล็กน้อย"
  beats "เธอประหม่า". Specificity is cozy.
- **Let comedy be deadpan.** The narrator should describe a chaotic moment
  in a calm tone — that contrast is the humor.
- **Inner thoughts are gold.** What the character notices but doesn't say
  is the whole romance. Use them generously.
- **Awkward pauses are storytelling.** Long sentences with embedded asides
  read aloud better than short choppy ones in Thai.
- **Resist resolving things.** A scene that ends with both characters
  *not* admitting what they feel is more romantic than one that resolves.

---

## The library system

When you write a `prompt` that you think will be reused, include
`save_to_library_as: "descriptive_slug"`. On first render, the image
gets promoted into `library/visuals/backgrounds/<slug>.png` and the
`_index.json` is updated with the prompt + seed + tags.

Subsequent episodes should `ref: "library://backgrounds/<slug>"` instead
of regenerating.

The library is the long-lived value of this project. Episodes 1–3 grow it;
episodes 4+ should mostly reuse it.

---

## CLI commands (all shipping today)

- `./generate [<id>]` — one-shot: full pipeline (narrate → images → compose → mux)
- `./novel doctor` — env check (Python, ffmpeg+VideoToolbox, Thai font)
- `./novel new <id>` — scaffold `in/<id>.json` from `in/example.json`
- `./novel validate [<id>]` — schema check + pacing warnings
- `./novel narrate [<id>]` — Phase B only (edge-tts → WAVs)
- `./novel images [<id>] [--force]` — Phase C only (SDXL Turbo + library + upscale)
- `./novel render [<id>]` — same as `./generate` but assumes venv is ready
- `./clean` — wipe caches + outputs; preserves library, models, content

No live preview server — render is fast enough (~1–2 min) that the loop is
"edit JSON → `./generate` → play MP4". For just narration, run `./novel narrate`
and listen to `cache/<id>/blocks/*.wav` directly.

---

## Apple Silicon constraints

- **M2 Pro 32 GB. Max 3 parallel per stage** (3 edge-tts, 3 Remotion chunks).
- **SDXL Turbo via MLX**, 1024×576 generation, Real-ESRGAN upscale to 1920×1080.
- **Whisper-MLX** for alignment (Neural Engine).
- **VideoToolbox H.264** for encoding (3× faster than libx264).
- Never run image generation and Remotion render simultaneously on 16 GB
  machines (we're 32 GB so this is fine, but the schema should still allow
  it to be opt-in for portability).
