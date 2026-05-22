# thai-novel

Local pipeline that turns a pre-segmented Thai novel script into a narrated MP4 ready to upload to YouTube.

Built and tested on **MacBook Pro M2 Pro / 32 GB**. Everything runs offline once the model weights are cached.

---

## What it does

You give it a JSON file with scenes (Thai narration + an English image prompt per scene). It:

1. Generates Thai narration audio per scene with **PyThaiTTS** (VachanaTTS voice).
2. Generates one image per scene with **[Z-Image-Turbo](https://huggingface.co/Tongyi-MAI/Z-Image-Turbo)** loaded directly into the process (no separate server, no port juggling — the model loads once, all scenes reuse it, the process exits cleanly when the MP4 is written).
3. Mixes a looping royalty-free relaxing instrumental from `music/` under the narration (voice clearly on top, music ducked to ~15%).
4. Prepends a 5 s welcome intro card ("ยินดีต้อนรับสู่ช่อง <channel>") — auto-generated, or you can drop your own `intro/intro.mp4` to override.
5. Concatenates everything into `out/<title>.mp4` at **1280×720** (720p).

You provide the narration and image prompts. This app does not split the novel for you — use Claude (template below) to convert your raw chapter text into the JSON format.

---

## Commands

```bash
./run                              # one-time: install Python deps in .venv/
./sync                             # pre-fetch / refresh all model caches
./make <inputs...>                 # render one or many JSON files
```

### `./make` — single or batch

```bash
./make in/ep01.json                          # one file
./make in/ep01.json in/ep02.json             # multiple files (positional)
./make in/*.json                             # shell glob — every JSON in in/
./make in                                    # directory — same as in/*.json
./make in/ep01.json --no-bgm                 # flags can come anywhere
./make in --stop-on-error                    # abort batch on first failure
./make in -v                                 # verbose / debug logs
```

Batch behaviour:
- Renders inputs in alphabetical order (the order the shell glob produces).
- One bad file does **not** kill the batch — it logs the error and moves on. Pass `--stop-on-error` if you want fail-fast.
- Each output lands at `out/<title>.mp4` (slug derived from the JSON's `title` field), so make sure your titles differ if you don't want one to overwrite another.
- At the end you get a summary like:
  ```
  ═════ Batch summary ═════
    succeeded: 8
      ✓ out/ep01.mp4
      ...
    failed: 2
      ✗ in/ep05.json — missing 'narration'
      ✗ in/ep07.json — TTS produced no output
  ```
- Exit code is 0 if everything succeeded, 1 if anything failed.

The first `./make` call (or your first `./sync`) downloads ~12 GB of Z-Image-Turbo weights plus the Vachana Thai voices to `~/.cache/huggingface/`. Every subsequent run reuses the cache.

### `./sync` flags

```bash
./sync                  # full refresh — Z-Image-Turbo + all 4 Thai voices
./sync --voices-only    # skip the 12 GB image model; just refresh voices (fast)
./sync --refresh-pip    # also run pip install -U -r requirements.txt
```

`./sync` is safe to re-run any time — it only pulls files that changed upstream.

---

## Input format

A single JSON file. Required fields are marked **required**, the rest have defaults.

```jsonc
{
  "title":           "ราชวงศ์แห่งเงา - ตอนที่ 1",  // required — used as MP4 filename and intro subtitle
  "channel":         "ThAI Novel",                  // required — drawn on the intro card (visual)
  "channel_spoken":  "ที เอช เอ ไอ โนเวล",         // optional — how TTS pronounces the channel name.
                                                    //            Falls back to `channel` when omitted.
                                                    //            Use this when the brand is stylised
                                                    //            (e.g. "ThAI" = TH + AI letter-by-letter).
  "language":        "th",                          // optional, default "th"
  "voice":           "th_f_1",                      // optional PyThaiTTS speaker: th_f_1 / th_m_1 / th_f_2 / th_m_2
  "engine":          "vachana",                     // optional PyThaiTTS engine: vachana / khanomtan / lunarlist_onnx
  "speed":            0.95,                         // optional, default 1.0 — playback speed (0.85=slower, 1.1=faster)
  "sentence_pause_ms": 250,                         // optional, default 0 — silence inserted between sentence chunks
  "scenes": [                                       // required — at least one scene
    {
      "narration":    "ราชวงศ์แห่งเงา ...",         // required — the Thai text to read aloud
      "image_prompt": "Cinematic dark fantasy Thai novel cover, ..."  // required — English prompt for Z-Image-Turbo
    }
    // ... as many scenes as you want; each scene shows ONE image while its narration plays.
  ]
}
```

### About `channel_spoken`

The visual card always uses `channel` verbatim — so "ThAI Novel" appears exactly as written on screen. The TTS engine, however, sees `channel_spoken` when one is set. Thai TTS engines mispronounce mixed-case Latin words ("ThAI" → "thigh") so for a brand like ours you want to spell out the letters phonetically in Thai script:

| Goal | `channel` | `channel_spoken` |
|---|---|---|
| Said as letters (T·H·A·I Novel) | `ThAI Novel` | `ที เอช เอ ไอ โนเวล` |
| Said as one word (Thai Novel) | `ThAI Novel` | `ไทย โนเวล` |
| Said in English | `ThAI Novel` | (depends on engine; Vachana is Thai-only) |

Spaces in the spoken form act as natural pauses for the TTS.

### Tuning TTS quality (`engine`, `voice`, `speed`, `sentence_pause_ms`)

PyThaiTTS sounds rushed and flat by default — these four knobs fix most of it.

| Symptom | Try |
|---|---|
| Too fast / no breathing | `"speed": 0.9` and `"sentence_pause_ms": 300` |
| Robotic / flat prosody | `"engine": "khanomtan", "voice": "Linda"` (multilingual model, more natural intonation) |
| Female sounds too brisk | `"voice": "th_f_2"` (calmer pacing, often best for long narration) |
| Want a male narrator | `"voice": "th_m_1"` (deeper) or `"voice": "th_m_2"` |
| Choppy across sentences | `"sentence_pause_ms": 250` glues each sentence with 250 ms of silence |

How each knob works:

- **`engine`** — picks the underlying model. `vachana` (default) is the fastest and offers four speakers. `khanomtan` is heavier but has noticeably more natural prosody for long narration. `lunarlist_onnx` is single-voice and the fastest of all.
- **`voice`** — speaker id. Valid set depends on engine. Vachana: `th_f_1 / th_m_1 / th_f_2 / th_m_2`. KhanomTan: `Linda` (default; many other multilingual speakers available — see the [KhanomTan repo](https://github.com/wannaphong/KhanomTan-TTS-v1.0)).
- **`speed`** — multiplier applied after synthesis via ffmpeg `atempo`. Pitch is preserved. Range 0.5–2.0 is the sweet spot; values outside chain multiple filters automatically. `1.0` skips this step entirely.
- **`sentence_pause_ms`** — when > 0, we split your narration on Thai sentence terminators (`.`, `!`, `?`, `…`, newlines), synthesise each sentence separately, and concat them with this much silence between. `0` (default) keeps the old single-shot behaviour. 200–400 ms feels most natural for novel narration.

⚠️ **Cache note**: scene WAVs are cached at `out/_work/<title>/scene_NNN.wav`. If you change `speed`, `voice`, `engine`, or `sentence_pause_ms` and re-run, the cached WAVs are reused — they won't reflect the new settings. Clear them first: `rm -rf out/_work/<title>`.

A working sample lives at `input.example.json` (3 short scenes; useful for a quick smoke test).

### Why English image prompts for a Thai novel?

Z-Image-Turbo is trained on English captions and produces noticeably better images from English prompts. Your narration stays Thai — only the *prompt to the image model* should be English. Claude can do this translation for you in one shot (see template below).

---

## Claude template — turn your novel text into the JSON

Copy/paste the block below into a Claude conversation, then paste your raw chapter text after it. Claude will return a JSON file you can save and feed straight into `./make`.

````
You are helping me convert a Thai novel chapter into the input format for my
local text-to-video pipeline. Read my chapter text below and output ONE JSON
object matching this schema:

{
  "title":             "<Thai title — chapter or episode title>",
  "channel":           "ThAI Novel",
  "channel_spoken":    "ที เอช เอ ไอ โนเวล",
  "language":          "th",
  "engine":            "vachana",
  "voice":             "th_f_1",
  "speed":             0.95,
  "sentence_pause_ms": 250,
  "scenes": [
    {
      "narration":    "<Thai text to be read aloud for this scene>",
      "image_prompt": "<English image prompt for a 1024x576 cinematic still>"
    }
  ]
}

Rules:
1. Split the chapter into SCENES. A scene boundary is one of:
   - a markdown heading (# / ## / ###)
   - an emoji section marker (👥 🗺️ 📜 ⛓️ etc.)
   - a clear shift in setting, point of view, or time
   Aim for 6–25 scenes per episode. A scene should hold one mental image.
2. The "narration" field is the Thai prose to be spoken for that scene.
   - Keep ALL of the user's Thai text — do NOT summarise. Move it into the
     right scene unchanged. Strip markdown syntax (#, *, lists) but keep the
     readable text. Expand abbreviations only if they would confuse a TTS.
3. The "image_prompt" is ONE English sentence (12–25 words) describing what
   the viewer should see during that scene. Always include a style hint
   (e.g. "cinematic", "atmospheric watercolor", "oil painting", "moody
   chiaroscuro"). Do NOT include character names the model won't know —
   describe the person ("an old Chinese-Thai merchant in 1940s Yaowarat",
   not "Ah Seng"). Aspect ratio is 16:9.
4. Set "title" from the chapter title in the source, or invent a short one
   if absent. Use "<MY_CHANNEL_NAME>" for "channel" — I will edit it.
5. Set "voice" to "th_f_1" unless I ask otherwise.
6. Leave `channel_spoken` exactly as shown — that controls the pronunciation
   of "ThAI Novel" in the welcome intro.
7. Output ONLY the JSON, no commentary, no markdown fences.

Chapter text follows:
---
<PASTE YOUR THAI CHAPTER HERE>
---
````

Save Claude's reply into `in/` with a zero-padded, ordered filename, e.g. `in/01_chapter-name.json`. The pipeline renders inputs in alphabetical order, so zero-padding keeps batches in the right sequence.

```bash
./make in/01_chapter-name.json     # one chapter
./make in                          # render every chapter in in/ (batch)
```

---

## Performance budget (M2 Pro / 32 GB)

| Step | Time |
|---|---|
| TTS per scene (~30 s narration) | a few seconds |
| Image per scene (1024×576) | ~2–3 min |
| 30-scene episode total | ~90 min |
| First-ever image of the project | +~10 min (one-time weight download) |

Image generation is the bottleneck. Start a render and walk away — the process holds the model in RAM the whole time and exits the moment the MP4 is written.

---

## Layout

```
thai-novel/
├── run                  # one-time setup: builds .venv, installs deps
├── sync                 # pre-fetch / refresh HuggingFace model caches
├── make                 # render: ./make <inputs...> → out/<title>.mp4
├── pipeline.py          # orchestrator: TTS → images → per-scene clips → intro → bgm → mux
├── tts.py               # PyThaiTTS wrapper (Vachana / KhanomTan / Lunarlist)
├── image_gen.py         # Z-Image-Turbo loader + generate() (in-process, no server)
├── video.py             # ffmpeg compose helpers
├── intro.py             # auto-generated welcome card (with optional logo)
├── sync.py              # implementation behind ./sync
├── requirements.txt
├── input.example.json
├── in/                  # (conventional) drop your chapter JSON files here
├── music/               # drop CC0 instrumental .mp3/.m4a/.wav here
├── intro/               # logo.png + optional intro.mp4 override (see "Intro card" below)
└── out/                 # generated MP4s land here
```

`in/` is just a convention — the pipeline accepts inputs from anywhere — but keeping them all in one folder makes `./make in` a clean batch trigger.

---

## Intro card — adding your channel logo

The auto-generated 5 s intro card normally shows just the channel name and episode title over a dark gradient. To add your logo:

**Drop a logo file into the `intro/` folder, named one of:**

```
intro/logo.png        ← recommended (transparent PNG works perfectly)
intro/logo.jpg
intro/logo.jpeg
intro/logo.webp
```

The pipeline picks the first one it finds. On every render it:

1. Reads your logo
2. Resizes it (aspect preserved) — max 35% of the card height, max 60% of the card width
3. Pastes it centered above your channel name, channel name and title below

Layout when a logo is present:

```
┌──────────────────────────────┐
│                              │
│           [ LOGO ]           │
│                              │
│        Channel Name          │
│         Episode Title        │
│                              │
└──────────────────────────────┘
```

**If you want a fully custom intro** (animations, your own voiceover, music sting, etc.), produce it in any video editor and save it as `intro/intro.mp4`. When that file exists, the pipeline skips the auto-generated card entirely and just concatenates your file at the start. You can use `logo.png` and `intro.mp4` either independently or together — `intro.mp4` always wins when both are present.

No logo? Card falls back to the centered text-only layout. You can drop a logo in anytime — it'll be picked up on the next render.

---

## Troubleshooting

**Black images on first generation.**
On Apple Silicon, fp16 produces NaN for this transformer. We default to bf16, which is fine. If you still see black output, set `Z_IMAGE_DTYPE=float32` in a `.env` file (slower but maximally stable).

**TTS errors about an unknown voice.**
For `vachana` (the default engine), valid speakers are: `th_f_1`, `th_m_1`, `th_f_2`, `th_m_2`. For `khanomtan`, the default is `Linda`. Switch engines via the `engine` field in your input JSON.

**TTS error: `TTS.__init__() got an unexpected keyword argument 'model'`.**
You're on PyThaiTTS 0.4.x where the constructor kwarg is `pretrained`, not `model`. Pull the latest `tts.py` from this repo (already fixed) and you'll be set.

**No music plays.**
`music/` is probably empty. Either drop tracks in (see `music/README.md` for free sources) or pass `--no-bgm`.

**Out of memory.**
Close other apps. Z-Image-Turbo needs ~12 GB while generating; with 32 GB RAM you should have headroom but Chrome with 50 tabs will eat it.

**Batch run failed partway through.**
Default behaviour is to skip failures and keep going so you don't lose hours. The summary at the end of the run tells you which JSONs failed. Fix and re-run just those: `./make in/05_*.json in/07_*.json`. Successful files won't be re-rendered as long as their cached `out/_work/<title>/` directories exist.

**I want to redo just the intro (e.g. after dropping in a new `intro/logo.png`).**
`rm -rf intro/_generated_* out/_work && ./make in` — the scene WAVs/PNGs are cached per-title, so only the intro and final concat are rebuilt. Much faster than a cold render.
