---
name: json-transform
description: Use when the user wants a thai-novel episode JSON spec — either CREATED from a story idea/premise, or TRANSFORMED from existing Markdown/text files. Triggers on "/json-transform", "create a story about X", "write episode N", "draft an episode of <series>", "turn this story into JSON", "transform my .md files to JSON", "convert my story folder to spec", "import this novel into thai-novel", or any time the user pastes Thai prose and wants the pipeline to render it.
---

# json-transform

You produce a story bible plus valid episode JSON for the `./generate` pipeline in this project.

- `in/ep0.json` is the non-rendered story bible: whole-story summary, poster prompt, shared image style, character bible, and per-episode prompts for other AI agents.
- `in/epNN.json` files are renderable source episodes.
- Each source episode has exactly one chapter and one image.
- `./generate` groups up to 10 source episodes into one publication MP4.
- The poster is shared for every YouTube post for the story; it is not the only in-video image.
- A grouped video shows the channel image for the welcome, then changes to each episode image when that episode starts.

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
3. **`in/ep0.json` if it exists** — story bible, prompt handoff, and continuity source.
4. **Any existing `in/epNN.json` siblings** — for series continuity (characters, voice, style).

Skip these and you will invent FIXED values that contradict the channel's standards.

---

## What to copy vs what to invent (BOTH modes)

| Tier | Source |
| --- | --- |
| **FIXED** (voice, image gen, visual style, music palette, intro logo, subtitle config) | Copy from `in/template.example.json` or from a sibling `in/*.json`. NEVER invent these. |
| **PER_SERIES** (characters, theme, poster prompt, shared image style) | Copy from `in/ep0.json` or prior episode. If none exists, ASK once. |
| **PER_EPISODE** (`project.id`, `title`, `episode`, `short_description`, one `chapter`, `narration_blocks`, `end_card`) | This is where your work goes — invented in Mode A, mapped from sources in Mode B. |

---

## Mode A — Create from scratch

### Workflow

1. **Clarify the premise** — one round of questions if needed:
   - Series this belongs to? (so you can reuse characters)
   - Approximate length? (default: ~30 min, 5–6 chapters, ~2000 Thai chars per block)
   - Tone? (romcom slow-burn is the default series voice)
   - Episode number?

2. **Create or update `in/ep0.json` BEFORE writing prose:**
   - Whole-story summary from beginning to ending.
   - Shared poster prompt for `novels/poster/background.png`; this poster is reused for every YouTube post for the story.
   - Shared episode-image style prompt.
   - Character bible.
   - Episode plan with `episode`, `title`, `short_description`, `image_prompt`, and `narration_prompt`.
   - Show the short story, poster prompt, and episode plan to the user before writing the full episode files when the user asks for preview/approval.

3. **Write narration blocks**:
   - 1500–3000 Thai chars per block, target ~2000.
   - One mood per block — start a new block if mood shifts.
   - Specific physical details, deadpan tone, inner thoughts, no fourth-wall breaks.
   - Reuse characters' names + appearance descriptors exactly from `characters[]`.

4. **Place exactly one visual anchor per episode**:
   - Preferred: generate the image with OpenAI/Codex and save it as `library/visuals/backgrounds/<series-slug>_epNN.png`.
   - In `epNN.json`, set `visual_anchor.ref` to `library://backgrounds/<series-slug>_epNN`.
   - Keep the English prompt in `in/ep0.json` under that episode's `image_prompt`.
   - Do not use `anchor_override` in the new workflow.
   - Local SDXL `prompt` + `save_to_library_as` remains a fallback only.

5. **Short description + end card**:
   - Write `project.short_description` as one smooth Thai paragraph for YouTube.
   - Keep it short: 2–4 sentences, no spoilers beyond the episode hook.
   - It is exported to `novels/<id>/output/description.txt`.
   - End card: next episode title + short Thai farewell.

6. **Write the JSON file** to `in/epNN.json`.
   - `NN` is the two-digit episode number from `project.episode`.
   - Examples: episode 1 → `in/ep01.json`, episode 12 → `in/ep12.json`.
   - Do **not** include the story title or descriptive slug in the filename.
   - Keep `project.id` slug-safe and meaningful; the filename and `project.id` do not need to match.

7. **Validate**: run `./novel validate <name>` (no `.json` extension). Must print "All specs valid."

8. **Report**: episode list, image refs generated/reused, estimated runtime, any pacing warnings, and the command to render. For batch publishing, use `./generate` to produce groups of up to 10 episodes, or `./generate --group-size 1` for one MP4 per episode.

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
   > "I found N files at `<path>`. Should I treat each file as one source episode? The new pipeline will render up to 10 source episodes per publication MP4 by default."

3. **Map prose to narration blocks**:
   - Each source episode's prose gets split into 1500–3000 char blocks inside one chapter.
   - Look for natural break points (paragraph endings, scene shifts, mood changes) — don't slice mid-sentence.
   - Infer mood per block from emotional cues:
     - Tension/conflict → `tense`
     - Loss/sadness/rain → `melancholy`
     - Romantic moments → `romantic`
     - Comic awkwardness → `funny`
     - Light banter → `playful`
     - Default narrative → `cozy`
   - **If you're unsure about mood for >30% of blocks, ASK** — better to confirm than to misclassify.

4. **Generate the single episode image prompt from the prose**:
   - For each source episode, identify the dominant emotional image for the entire episode.
   - Convert to a 1-sentence English prompt focusing on SUBJECT/SETTING/LIGHTING. Do **NOT** put style keywords like `anime`, `painterly`, `photoreal`, or `cinematic photograph` here — those are auto-injected from `visual_style.tone`. Example:
     `Thai beach resort at golden hour, five young men arriving with luggage, warm sun, shallow depth of field`
   - Use the project's `visual_style.base_prompt` as the house style (don't repeat it — it's prepended automatically).
   - Store the prompt in `in/ep0.json` under `episode_plan[].image_prompt`.
   - Preferred render anchor: `ref: "library://backgrounds/<series-slug>_epNN"` after OpenAI/Codex generates the image file.

5. **Fill in PER_SERIES from the source** if any chapter mentions characters by name:
   - Extract appearance descriptors from the prose (hair color, age range, distinctive features).
   - **Always give each character an `id`** (slug-safe, lowercase, e.g. `thana`, `phim`, `pom`). The `id` lets per-chapter `visual_anchor.characters` reference them.
   - If the user has a "character bible" `.md` file alongside, READ THAT FIRST and use it verbatim.
   - Optionally set `reference_image: "library://characters/<id>"` so IP-Adapter can lock the face across episodes (only effective if the user has actually dropped a PNG at `library/visuals/characters/<id>.png`; otherwise the field is harmless — the pipeline silently skips it).

6. **Tag characters into the episode `visual_anchor.characters`** when they appear in the image:
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

- **One source episode = one chapter = one visual anchor.** All narration blocks in that episode show the same image. Mood does NOT change the image.
- **Mood drives music + pacing**, not visuals. Music is picked from `audio.music_bed.by_mood`, narration speed/pauses from `tts.mood_pauses`.
- **Do not use per-scene images** in the new workflow. `anchor_override` is legacy escape hatch only.
- **Image budget**: exactly 1 episode image per source episode, plus 1 poster for the whole story.
- **Library convention**: episode images are series-namespaced, e.g. `shadow_dynasty_ep01`, and referenced as `library://backgrounds/shadow_dynasty_ep01`.
- **Publication grouping**: `./generate` groups up to 10 source episodes into one video and writes a description containing all included short descriptions.
- **Grouped video sequence**:
  1. Speak `ยินดีต้อนรับเข้าสู่ช่อง T H A I channel ขอให้สนุกกับการรับฟังครับ` while showing the channel image/logo.
  2. For each source episode, speak `เรื่อง {story_name} ตอนที่ N {ep_title}`.
  3. Show that episode's image and read that episode's narration.
  4. Repeat episode title + episode image + narration until the group reaches 10 episodes.

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
  "engine":     "hyper-sdxl-8step",   // FIXED — better quality SDXL distilled LoRA
  "steps":      8,                     // FIXED — engine forces 8 anyway
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

- [ ] `in/ep0.json` exists and contains the whole-story summary, poster prompt, shared image style, characters, and episode plan
- [ ] Poster prompt clearly says it is a shared YouTube/posting poster, not the only in-video image
- [ ] File path is `in/epNN.json` (two-digit episode number only) and does NOT end with `.example.json`
- [ ] `project.id` is slug-safe, lowercase, series-prefixed
- [ ] `project.short_description` is a smooth Thai YouTube description paragraph
- [ ] Every source episode has exactly one chapter with `id`, `title`, `visual_anchor`, and ≥1 `narration_blocks`
- [ ] Every narration_block has `id`, `mood` (from strict list), `narration`
- [ ] All narration is Thai prose — no English inside narration field
- [ ] All visual prompts in `ep0.json` are English
- [ ] Total unique anchors per `epNN.json` is exactly 1
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
| More than one unique image in a source episode | Merge into one chapter/photo. The publication video may contain up to 10 episode images because it groups up to 10 source episodes |
| Writing a 6000-char block "because the story needed it" | Split into 2–3 blocks with mood shifts |
| Setting `tts.voice` to something other than the channel default without being asked | Don't change it |
| **Mode B**: rewriting / "improving" the source prose | Don't. Transform structure only. Surface improvement suggestions as questions, not silent edits |
| **Mode B**: skipping prose paragraphs silently | Report what you skipped and why |
| **Mode A**: writing the full episode before showing the user the outline | Outline first → get approval → then write prose |

---

## When the user asks to extend an existing episode

Read `in/ep0.json` and the target file first. Preserve everything FIXED + PER_SERIES. Keep exactly one chapter; add narration blocks inside that chapter and update `project.short_description` / `end_card.next_episode_title` if needed.

---

## Reference: minimal valid Episode

```jsonc
{
  "project": {
    "id": "my-series-ep01",
    "title": "ตอนที่ 1: <ชื่อตอน>",
    "episode": 1,
    "short_description": "เรื่องย่อสั้นภาษาไทยสำหรับ YouTube description ของตอนนี้"
  },
  "chapters": [
    {
      "id": "ch_01",
      "title": "<ภาพหลักของตอน>",
      "visual_anchor": {
        "characters": ["lead_male", "lead_female"],

        "ref": "library://backgrounds/my_series_ep01",
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

## Reference: minimal valid `in/ep0.json`

```jsonc
{
  "kind": "story_bible",
  "series": "ชื่อเรื่อง",
  "title": "ชื่อเรื่อง",
  "whole_story_summary": "สรุปทั้งเรื่องตั้งแต่ต้นจนจบ",
  "poster_prompt": "English prompt for the whole-series poster",
  "episode_image_style_prompt": "English shared style prompt for every episode image",
  "characters": {
    "lead_male": {
      "id": "lead_male",
      "name": "ชื่อตัวละคร",
      "appearance": "English visual description"
    }
  },
  "episode_plan": [
    {
      "episode": 1,
      "title": "ชื่อตอน",
      "short_description": "เรื่องย่อสั้นของตอน",
      "image_prompt": "English OpenAI image prompt for this episode"
    }
  ]
}
```

---

## Final reminder

Your job is to produce a JSON file that:
1. Validates the first time (`./novel validate <name>` passes)
2. Reads aloud naturally in Thai (no robotic transitions)
3. Renders to a cinematic, atmosphere-heavy audiobook MP4 (not a slideshow)
4. Earns the user's trust to ship to YouTube

The schema is strict but forgiving. The writing should be the opposite: loose and human, but precise about what mood is on screen and what scene we're in.
