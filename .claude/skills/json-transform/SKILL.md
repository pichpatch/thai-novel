---
name: json-transform
description: Use when the user wants a thai-novel episode JSON spec — either CREATED from a story idea/premise, or TRANSFORMED from existing Markdown/text files. Triggers on "/json-transform", "create a story about X", "write episode N", "draft an episode of <series>", "turn this story into JSON", "transform my .md files to JSON", "convert my story folder to spec", "import this novel into thai-novel", or any time the user pastes Thai prose and wants the pipeline to render it.
---

# json-transform

You produce a valid episode JSON for the `./generate` pipeline in this project. Your output gets dropped into `./in/<name>.json` and the user renders it to MP4.

## Two modes — detect which one the user wants

### Mode A — CREATE from scratch
Triggered by: "create a story about ...", "write episode N about ...", "draft a new episode", "make me a story where ..."

The user gives you a PREMISE or topic. You invent the story AND the JSON.

### Mode B — TRANSFORM existing files
Triggered by: "transform my .md files to JSON", "convert this folder to a spec", "I have a story at <path>", "import this novel", or any time the user points you at one or more `.md` / `.txt` / `.json` source files.

The user gives you EXISTING prose. You reshape it into the JSON schema without inventing new story content.

**If the request is ambiguous, ask once:**
> "Two paths: (A) I create a brand-new story from a premise you give me, or (B) I transform existing prose files into the JSON spec. Which do you want?"

---

## ALWAYS read these files first (BOTH modes)

Before writing anything:

1. **`in/template.example.json`** — schema with inline `_doc` comments tagged FIXED / PER_SERIES / PER_EPISODE. This is the canonical structure.
2. **`in/README.md`** — field-by-field reference + the `library://` convention.
3. **Any existing `in/*.json` siblings** — for series continuity (characters, voice, style).

Skip these and you will invent FIXED values that contradict the channel's standards.

---

## What to copy vs what to invent (BOTH modes)

| Tier | Source |
| --- | --- |
| **FIXED** (voice, image gen, visual style, music palette, intro logo, subtitle config) | Copy from `in/template.example.json` or from a sibling `in/*.json`. NEVER invent these. |
| **PER_SERIES** (characters, theme) | Copy from prior episode in same series. If none exists, ASK once. |
| **PER_EPISODE** (`project.id`, `title`, `episode`, `chapters[]`, `end_card`) | This is where your work goes — invented in Mode A, mapped from sources in Mode B. |

---

## Mode A — Create from scratch

### Workflow

1. **Clarify the premise** — one round of questions if needed:
   - Series this belongs to? (so you can reuse characters)
   - Approximate length? (default: ~30 min, 5–6 chapters, ~2000 Thai chars per block)
   - Tone? (romcom slow-burn is the default series voice)
   - Episode number?

2. **Outline the chapters BEFORE writing prose:**
   - 4–6 chapters, each with a one-line summary + dominant mood + visual setting.
   - Show the outline to the user. Get a yes/tweak before writing the full narration.

3. **Write narration blocks**:
   - 1500–3000 Thai chars per block, target ~2000.
   - One mood per block — start a new block if mood shifts.
   - Specific physical details, deadpan tone, inner thoughts, no fourth-wall breaks.
   - Reuse characters' names + appearance descriptors exactly from `characters[]`.

4. **Place visual anchors**:
   - One per chapter, plus ≤4 per-scene `anchor_override` for emotional peaks.
   - English prompts. Slug-safe, series-prefixed `save_to_library_as`.
   - Before inventing a new prompt, check `library/visuals/backgrounds/` via Bash (`ls library/visuals/backgrounds/`) — if a matching scene exists, REUSE it via `ref://`.

5. **End card**: next episode title + short Thai farewell.

6. **Write the JSON file** to `in/<descriptive-slug>.json`.

7. **Validate**: run `./novel validate <name>` (no `.json` extension). Must print "All specs valid."

8. **Report**: chapter list, anchor count (new vs reused), estimated runtime, any pacing warnings, and the command to render: `./generate <name>`.

**Do NOT auto-render.** Let the user trigger `./generate` themselves.

---

## Mode B — Transform existing files

### Workflow

1. **Locate the source files**. The user may have given:
   - A folder path → use `ls` to enumerate `.md` / `.txt` / `.json` inside it
   - A specific file → read it
   - Multiple files → read each

   Run `Glob` or `ls <folder>` first. Confirm what you found with the user before processing.

2. **Identify the structure**. Common formats you'll encounter:

   | File layout | Means |
   | --- | --- |
   | One `.md` per chapter, `# Title` then prose | One file = one chapter of one episode. Multiple files = one episode with multiple chapters. |
   | One `.md` with `## Chapter 1`, `## Chapter 2` headings | One file = one episode. Each h2 = one chapter. |
   | Plain prose with no headings, separators like `---` or blank-line gaps | Treat each large block as a chapter. Ask the user if uncertain. |
   | Legacy thai-novel `.json` with old schema | Validate via `./novel validate <name>` — the auto-normalizer fixes most issues silently. If the schema differs more deeply (e.g. `image_per_scene` instead of `visual_anchor`), map fields explicitly. |

   **If the structure is ambiguous, ask:**
   > "I found N files at `<path>`. Should I treat (a) each file as one episode, (b) all files together as one episode with N chapters, or (c) some other grouping? And do you want one MP4 per episode or one big concatenation?"

3. **Map prose to narration blocks**:
   - Each chapter's prose gets split into 1500–3000 char blocks.
   - Look for natural break points (paragraph endings, scene shifts, mood changes) — don't slice mid-sentence.
   - Infer mood per block from emotional cues:
     - Tension/conflict → `tense`
     - Loss/sadness/rain → `melancholy`
     - Romantic moments → `romantic`
     - Comic awkwardness → `funny`
     - Light banter → `playful`
     - Default narrative → `cozy`
   - **If you're unsure about mood for >30% of blocks, ASK** — better to confirm than to misclassify.

4. **Generate visual anchors from the prose**:
   - For each chapter, read the prose and identify the dominant SCENE/SETTING.
   - Convert to a 1-sentence English prompt focusing on SUBJECT/SETTING/LIGHTING. Do **NOT** put style keywords like `anime`, `painterly`, `photoreal`, or `cinematic photograph` here — those are auto-injected from `visual_style.tone`. Example:
     `Thai beach resort at golden hour, five young men arriving with luggage, warm sun, shallow depth of field`
   - Use the project's `visual_style.base_prompt` as the house style (don't repeat it — it's prepended automatically).
   - `save_to_library_as`: slug-safe, series-prefixed (e.g. `<series-id>_ep<N>_<chapter-slug>`).
   - Check `library/visuals/backgrounds/` first — REUSE existing assets when the scene matches.

5. **Fill in PER_SERIES from the source** if any chapter mentions characters by name:
   - Extract appearance descriptors from the prose (hair color, age range, distinctive features).
   - **Always give each character an `id`** (slug-safe, lowercase, e.g. `thana`, `phim`, `pom`). The `id` lets per-chapter `visual_anchor.characters` reference them.
   - If the user has a "character bible" `.md` file alongside, READ THAT FIRST and use it verbatim.
   - Optionally set `reference_image: "library://characters/<id>"` so IP-Adapter can lock the face across episodes (only effective if the user has actually dropped a PNG at `library/visuals/characters/<id>.png`; otherwise the field is harmless — the pipeline silently skips it).

6. **Tag characters into each chapter's `visual_anchor.characters`** when they appear in the scene:
   - List up to 4 character ids per chapter, e.g. `"characters": ["thana", "phim"]`.
   - These ids let the pipeline pass their reference images to IP-Adapter at render time → same face every episode.
   - If a character is mentioned in the narration but is **not visible in the visual anchor** (e.g. mentioned in a memory), do NOT add their id.

6. **Write the JSON file** — same as Mode A step 6.

7. **Validate + Report** — same as Mode A steps 7–8. In your report, ALSO include:
   - How many source files you processed
   - Which prose chunks became which narration blocks (give the user line ranges so they can verify)
   - Any prose you SKIPPED (and why — e.g. metadata, footnotes, English-only sections)

**For Mode B, don't invent new narrative content.** If the prose has gaps you'd want to fill, surface them as questions, don't write filler.

---

## Pipeline mental model (BOTH modes)

These rules govern your output regardless of how you arrived at it:

- **One chapter = one visual anchor by default.** All narration blocks in a chapter show the chapter's image. Mood does NOT change the image.
- **Mood drives music + pacing**, not visuals. Music is picked from `audio.music_bed.by_mood`, narration speed/pauses from `tts.mood_pauses`.
- **Per-scene images exist** via `narration_block.anchor_override` — use SPARINGLY for romantic peaks, cut-aways to objects, time-of-day shifts. ≤4 per episode.
- **Image budget**: 5–15 unique anchors per ~30-min episode. Library reuse is success.
- **Library convention**: `save_to_library_as` slugs are series-namespaced (e.g. `shadow-dynasty_ep45_ch01`, not `cafe`). Future episodes can `ref: "library://backgrounds/<name>"`.

---

## Critical content rules

### Mood vocabulary (STRICT Pydantic Literals)

| Mood | Use for | Pacing feel |
| --- | --- | --- |
| `cozy` | Default narrative atmosphere | Slow, warm |
| `funny` | Awkward, comedic beats | Slightly faster |
| `romantic` | Emotional peaks, longing | Slowest, longest pauses |
| `playful` | Teasing, mischief | Medium |
| `tense` | Conflict, urgency | Fast, short |
| `melancholy` | Quiet sadness, rain | Very slow |

Auto-normalizer accepts these aliases (prefer canonical names anyway): `melancholic→melancholy`, `sad→melancholy`, `happy→playful`, `calm→cozy`, `neutral→cozy`, `angry→tense`, `scared→tense`.

### Motion presets (STRICT)

`slow_zoom_in`, `slow_zoom_out`, `pan_left`, `pan_right`, `parallax_depth`, `subtle_handheld`, `ken_burns_combo`, `static`.

**Default to `static`** — the current pure-ffmpeg composer ignores motion. Setting it has zero effect today but keeps the spec future-proof. Auto-normalizer accepts: `slow_pan_left→pan_left`, `slow_pan_right→pan_right`, `fade_in/fade_out/none→static`.

### Color grades (STRICT)

`warm_cozy`, `cool_night`, `golden_hour`, `melancholy_blue`, `playful_pop`, `neutral`. Set once at `visual_style.color_grade`. Override per-anchor only when a scene needs a distinctly different palette.

### Tone — the aesthetic switch (NEW)

`visual_style.tone` is the single field that decides realistic vs anime. **Default: `"realistic"`**. Valid values: `"realistic" | "anime"`.

| Tone | Auto-prepended to positive prompt | Auto base_model |
|---|---|---|
| `realistic` (default) | `cinematic photograph, photorealistic, hyperrealistic, ` | None (= SDXL base 1.0) |
| `anime` | `anime style, illustration, ` | `cagliostrolab/animagine-xl-3.1` |

**Do NOT** put style words like `anime style`, `painterly`, `photorealistic`, or `cinematic photograph` in `visual_style.base_prompt` or per-anchor prompts — tone handles that automatically. Mixing them produces conflicted output.

`base_prompt` should contain **subject/atmosphere/lighting only**: e.g. `"dramatic atmosphere, natural lighting, shallow depth of field, 35mm film, sharp focus"`.

### Image generation defaults (channel-wide FIXED)

Copy these from `in/template.example.json`. Don't change unless instructed:

```jsonc
"image_generation": {
  "engine":     "hyper-sdxl-4step",   // FIXED — fast SDXL distilled LoRA
  "steps":      4,                     // FIXED — engine forces 4 anyway
  "guidance":   0,                     // FIXED — engine forces 0 anyway
  "seed":       <int>,                 // PER_EPISODE — pin for reproducibility
  "gen_width":  1280,                  // FIXED — 720p output
  "gen_height": 720,                   // FIXED — 16:9
  "upscaler":   "realesrgan"           // FIXED — sharper upscale to 1080p
}
```

To override aesthetic, set `image_generation.base_model` to any SDXL repo id (e.g. Pony, AAM XL). User override always wins over the tone default. Pony bases auto-inject score tags.

### Visual anchor prompts

- **Always English** — SDXL handles English much better than Thai.
- **Prompt template that works**:
  ```
  [scene type] at [time of day] in [setting], [lighting description],
  [atmosphere descriptors], [character description if any]
  ```
- **No style keywords here.** Tone field provides them.
- The `visual_style.base_prompt` is prepended automatically — don't repeat house-style adjectives.

### Narration blocks

- **1500–3000 Thai chars per block** is the sweet spot. CLI warns at <800 or >4000.
- A block is a *unit of pacing*, not a sentence. One mood at a time.
- Pure Thai prose. No English words inside narration.
- No dialogue tags — render dialogue as reported speech (`"เขาบอกว่า ..."` not `"เขา: ..."`).
- 4–6 chapters per 30-min episode is the sweet spot. Each chapter usually has 1–3 narration blocks.

---

## Quality bar — self-check before declaring done (BOTH modes)

- [ ] File path is `in/<name>.json` and does NOT end with `.example.json`
- [ ] `project.id` is slug-safe, lowercase, series-prefixed
- [ ] Every chapter has `id`, `title`, `visual_anchor`, ≥1 `narration_blocks`
- [ ] Every narration_block has `id`, `mood` (from strict list), `narration`
- [ ] All narration is Thai prose — no English inside narration field
- [ ] All visual prompts are English
- [ ] Total unique anchors ≤ 15 (count chapter anchors + per-block overrides, dedup by ref/prompt)
- [ ] `./novel validate <name>` prints "All specs valid."
- [ ] Pacing warnings reviewed — you tried to fix short/long blocks before shipping
- [ ] **Mode B only**: every paragraph of source prose ended up in some narration_block OR was explicitly flagged as skipped (with reason)

---

## Style notes for Thai romantic-comedy narration

The series voice (look at `in/example.json` for reference if it exists):

- **Specific physical details over abstract feelings.** "เปลือกตาข้างหนึ่งกระตุกเล็กน้อย" beats "เธอประหม่า".
- **Deadpan comedy.** Describe chaos in a calm tone — the contrast is the humor.
- **Inner thoughts are gold.** What characters notice but don't say is the whole romance.
- **Long sentences with embedded asides read aloud better** than short choppy ones in Thai.
- **Resist resolving things.** A scene that ends with both characters NOT admitting what they feel is more romantic than one that does.
- **The narrator is always third-person describing.** No fourth-wall breaks.

For other genres (thriller, drama, fantasy), adapt the voice but keep the structural rules.

---

## Common mistakes to avoid

| Mistake | Fix |
| --- | --- |
| Narration block has English words inside (`"เขาบอกว่า hello"`) | Translate or transliterate to Thai |
| `mood: "happy"` / `"sad"` / etc. | Use canonical names (`playful`, `melancholy`) — normalizer accepts aliases but be canonical |
| `motion: "fade_in"` / `"slow_pan_left"` | Use `static` (composer ignores motion currently) |
| Different `save_to_library_as` slugs for the same scene across episodes | Use the SAME slug — pipeline reuses the library file |
| Forgetting `narration_block.id` | Always set it (`<chapter_id>_b<n>`). Normalizer fills it but be explicit |
| Inventing a `series` or `theme` value that contradicts a prior episode | Read prior episodes first |
| Setting `subtitles.enabled: true` without being asked | Leave false (channel default) |
| Generating 20+ unique images in a single episode | Stop. Find scenes to reuse via `ref://`. Cut chapter count if needed |
| Writing a 6000-char block "because the story needed it" | Split into 2–3 blocks with mood shifts |
| Setting `tts.voice` to something other than the channel default without being asked | Don't change it |
| **Mode B**: rewriting / "improving" the source prose | Don't. Transform structure only. Surface improvement suggestions as questions, not silent edits |
| **Mode B**: skipping prose paragraphs silently | Report what you skipped and why |
| **Mode A**: writing the full episode before showing the user the outline | Outline first → get approval → then write prose |

---

## When the user asks to extend an existing episode

Read the target file first. Preserve everything FIXED + PER_SERIES. Only add to `chapters[]` and (optionally) update `end_card.next_episode_title`. Match the existing chapter id scheme (`ch_01` or `chapter_001` — whichever the file uses).

---

## Reference: minimal valid Episode

```jsonc
{
  "project": {
    "id": "my-series-ep01",
    "title": "ตอนที่ 1: <ชื่อตอน>"
  },
  "chapters": [
    {
      "id": "ch_01",
      "title": "<หัวข้อตอน>",
      "visual_anchor": {
        "characters": ["lead_male", "lead_female"],

        "prompt": "English scene description with cinematic adjectives",
        "save_to_library_as": "my-series_ep01_ch01",
        "motion": "static"
      },
      "narration_blocks": [
        {
          "id": "ch01_b1",
          "mood": "cozy",
          "narration": "<Thai prose, 1500–3000 chars>"
        }
      ]
    }
  ]
}
```

For real episodes, ALSO include `tts`, `image_generation`, `visual_style`, `characters`, `audio`, `subtitles`, `intro`, `end_card` — copy these from `in/template.example.json` and only adjust `intro.channel_name` / `characters.*` per series.

---

## Final reminder

Your job is to produce a JSON file that:
1. Validates the first time (`./novel validate <name>` passes)
2. Reads aloud naturally in Thai (no robotic transitions)
3. Renders to a cinematic, atmosphere-heavy audiobook MP4 (not a slideshow)
4. Earns the user's trust to ship to YouTube

The schema is strict but forgiving. The writing should be the opposite: loose and human, but precise about what mood is on screen and what scene we're in.
