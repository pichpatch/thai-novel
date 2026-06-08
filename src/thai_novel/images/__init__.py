"""Phase C: image pipeline (library lookup + SDXL Turbo + upscale)."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path

from ..hashing import image_key
from ..spec import Episode, VisualAnchor
from .generate import generate_image, _resolve_character_references
from .library import get_metadata, promote, resolve as resolve_lib
from .upscale import upscale_to_1080p

log = logging.getLogger("thai_novel.images")


@dataclass
class ResolvedAnchor:
    """Phase C result: a 1920x1080 PNG path for one anchor in the episode."""

    anchor_id: str
    src_kind: str  # "library" | "generated" | "promoted"
    image_path_1080p: Path
    gen_cache_path: Path | None = None


def _anchor_signature(anchor: VisualAnchor) -> str:
    return anchor.ref or anchor.prompt or "<empty>"


def collect_anchors(episode: Episode) -> list[tuple[str, VisualAnchor]]:
    """Walk the episode; return chapter anchors and per-block overrides."""
    out: list[tuple[str, VisualAnchor]] = []
    for ch in episode.chapters:
        out.append((ch.id, ch.visual_anchor))
        for b in ch.narration_blocks:
            if b.anchor_override:
                out.append((f"{ch.id}/{b.id}", b.anchor_override))
    return out


def resolve_anchor(
    anchor_id: str,
    anchor: VisualAnchor,
    episode: Episode,
    project_root: Path,
    force: bool = False,
) -> ResolvedAnchor:
    library_root = project_root / "library"
    cache_dir = project_root / "cache" / "images"
    models_dir = project_root / "models"
    upscaled_dir = project_root / "cache" / episode.project.id / "anchors"

    if anchor.ref:
        src = resolve_lib(anchor.ref, library_root)
        if src is None:
            raise LookupError(
                f"library ref not found: {anchor.ref}. "
                f"Did you forget to promote a generated image? "
                f"Use `save_to_library_as` in the JSON."
            )
        out = upscaled_dir / f"{anchor_id.replace('/', '__')}.png"
        upscale_to_1080p(src, out, method=episode.image_generation.upscaler)
        return ResolvedAnchor(
            anchor_id=anchor_id, src_kind="library",
            image_path_1080p=out, gen_cache_path=src,
        )

    assert anchor.prompt is not None

    # Compute the content-hash key for what this anchor *would* produce now,
    # given the current spec (prompt + style + seed + size + engine). This is
    # the source of truth for "did the inputs change since last promotion?"
    full_prompt = (episode.visual_style.base_prompt + " " + anchor.prompt).strip()
    current_key = image_key(
        prompt=full_prompt,
        negative_prompt=episode.visual_style.negative_prompt,
        style_base=episode.visual_style.base_prompt,
        seed=episode.image_generation.seed or 0,
        steps=episode.image_generation.steps,
        guidance=episode.image_generation.guidance,
        width=episode.image_generation.gen_width,
        height=episode.image_generation.gen_height,
        engine=episode.image_generation.engine,
        # Match the resolution generate_image does: explicit override OR tone-default.
        base_model=(
            episode.image_generation.base_model
            or ("cagliostrolab/animagine-xl-3.1"
                if getattr(episode.visual_style, "tone", "realistic") == "anime"
                else None)
        ),
    )

    # ── Smart library short-circuit ─────────────────────────────────────────
    # Reuse a promoted library file ONLY when the spec hasn't changed since
    # the file was generated. If the prompt/seed/size/engine changed, the
    # library copy is stale → regenerate.
    if anchor.save_to_library_as and not force:
        lib_ref = f"library://backgrounds/{anchor.save_to_library_as}"
        existing = resolve_lib(lib_ref, library_root)
        if existing is not None:
            meta = get_metadata(lib_ref, library_root) or {}
            stored_key = meta.get("image_key")
            if stored_key == current_key:
                log.info(
                    f"library hit: {anchor.save_to_library_as} (inputs unchanged)"
                )
                out = upscaled_dir / f"{anchor_id.replace('/', '__')}.png"
                upscale_to_1080p(existing, out, method=episode.image_generation.upscaler)
                return ResolvedAnchor(
                    anchor_id=anchor_id, src_kind="library",
                    image_path_1080p=out, gen_cache_path=existing,
                )
            else:
                reason = "no metadata" if not stored_key else "prompt/seed/style changed"
                log.info(
                    f"library miss: {anchor.save_to_library_as} ({reason}) — regenerating"
                )

    # Resolve character reference images for this anchor (if any). Each id
    # gets translated to a PIL image via the library; missing refs are silently
    # skipped (warned in logs). Cache key includes the ids so swapping refs
    # cleanly invalidates.
    char_ids = list(getattr(anchor, "characters", []) or [])
    char_refs = []
    if char_ids:
        # Episode.characters is a dict of CharacterSpec — convert to plain dicts
        # for the helper (which accepts dict shape).
        ep_chars = {k: (v.model_dump() if hasattr(v, "model_dump") else v)
                    for k, v in (episode.characters or {}).items()}
        char_refs = _resolve_character_references(char_ids, ep_chars, library_root)

    gen_path, _key = generate_image(
        prompt=anchor.prompt,
        style=episode.visual_style,
        image_cfg=episode.image_generation,
        cache_dir=cache_dir,
        models_dir=models_dir,
        character_refs=char_refs,
        character_ids_for_cache=char_ids,
    )

    src_kind = "generated"
    if anchor.save_to_library_as:
        promoted = promote(
            source_image=gen_path,
            name=anchor.save_to_library_as,
            library_root=library_root,
            kind="backgrounds",
            metadata={
                "prompt": anchor.prompt,
                "style_base": episode.visual_style.base_prompt,
                "seed": episode.image_generation.seed,
                "from_episode": episode.project.id,
                "image_key": current_key,  # used by the smart short-circuit on next run
            },
        )
        src_kind = "promoted"
        gen_path = promoted

    out = upscaled_dir / f"{anchor_id.replace('/', '__')}.png"
    upscale_to_1080p(gen_path, out, method=episode.image_generation.upscaler)
    return ResolvedAnchor(
        anchor_id=anchor_id, src_kind=src_kind,
        image_path_1080p=out, gen_cache_path=gen_path,
    )


def resolve_episode(
    episode: Episode,
    project_root: Path,
    force: bool = False,
    on_progress=None,
) -> list[ResolvedAnchor]:
    """Resolve every visual anchor (chapter + per-block + optional intro bg)."""
    anchors = collect_anchors(episode)

    if episode.intro.show and episode.intro.background_anchor is not None:
        anchors.insert(0, ("intro_background", episode.intro.background_anchor))

    seen: dict[str, ResolvedAnchor] = {}
    results: list[ResolvedAnchor] = []
    for i, (aid, anchor) in enumerate(anchors):
        sig = _anchor_signature(anchor)
        if sig in seen and not force:
            base = seen[sig]
            results.append(ResolvedAnchor(
                anchor_id=aid, src_kind=base.src_kind,
                image_path_1080p=base.image_path_1080p,
                gen_cache_path=base.gen_cache_path,
            ))
        else:
            log.info(f"resolving {aid} ({i+1}/{len(anchors)})")
            r = resolve_anchor(aid, anchor, episode, project_root, force=force)
            seen[sig] = r
            results.append(r)
        if on_progress:
            on_progress(i + 1, len(anchors))

    manifest_path = project_root / "cache" / episode.project.id / "anchors.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(
            [
                {
                    "anchor_id": r.anchor_id,
                    "src_kind": r.src_kind,
                    "image_path_1080p": str(r.image_path_1080p),
                }
                for r in results
            ],
            ensure_ascii=False, indent=2,
        ),
        encoding="utf-8",
    )

    return results


__all__ = ["resolve_episode", "resolve_anchor", "ResolvedAnchor"]
