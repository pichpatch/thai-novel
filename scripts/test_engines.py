"""
Render the same episode with every supported (engine, base_model) combo so
you can A/B compare image-generation pipelines side by side.

Usage:
    python scripts/test_engines.py <episode_id>
    # e.g.
    python scripts/test_engines.py five-survivors-ep01-th

For each combo it:
  1. Clones the source JSON to a temp `in/<id>__test__<engine_slug>.json`.
  2. Forces engine + base_model and strips `save_to_library_as` (so library
     stays clean and the smart short-circuit can never falsely match).
  3. Calls `./novel render` on the temp JSON via subprocess.
  4. Copies the resulting MP4 to `novels/_engine_tests/<engine_slug>.mp4`.

Idempotent: if `<engine_slug>.mp4` already exists, that combo is skipped.
Resumable: a crashed run can be re-invoked safely.

The narration cache is shared across all combos (same Thai text, same voice)
so download cost is paid once. Only the image-generation pass differs.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

# All combos we want to compare. Each tuple = (slug, engine, base_model_or_None)
# The slug becomes the output MP4 filename.
COMBOS = [
    ("sdxl-turbo",                    "sdxl-turbo",           None),
    ("sdxl-lightning-4step",          "sdxl-lightning-4step", None),
    ("sdxl-lightning-8step",          "sdxl-lightning-8step", None),       # ↑ quality
    ("hyper-sdxl-4step__animagine",   "hyper-sdxl-4step",     "cagliostrolab/animagine-xl-3.1"),
    ("hyper-sdxl-4step__pony",        "hyper-sdxl-4step",     "John6666/pony-diffusion-v6-xl-sdxl-spo"),
    ("hyper-sdxl-4step__realistic",   "hyper-sdxl-4step",     None),       # NEW: realistic comparison
    ("hyper-sdxl-8step__realistic",   "hyper-sdxl-8step",     None),       # ⭐ ep01's new default
    ("z-image-turbo",                 "z-image-turbo",        None),
    ("flux-schnell-4step",            "flux-schnell-4step",   None),
]


PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR   = PROJECT_ROOT / "novels" / "_engine_tests"


def make_variant_json(source_id: str, slug: str, engine: str, base_model: str | None) -> tuple[Path, str]:
    """
    Clone source episode JSON to a per-combo temp file with engine forced.
    Returns (path_to_temp_json, new_episode_id).
    """
    src = PROJECT_ROOT / "in" / f"{source_id}.json"
    if not src.exists():
        raise SystemExit(f"source episode not found: {src}")

    d = json.loads(src.read_text(encoding="utf-8"))
    eps = d if isinstance(d, list) else [d]

    new_id = f"{source_id}__test__{slug}"
    for ep in eps:
        # Force engine + base_model
        ig = ep["image_generation"]
        ig["engine"] = engine
        if base_model is not None:
            ig["base_model"] = base_model
        else:
            ig.pop("base_model", None)

        # Strip save_to_library_as on every anchor so each variant generates
        # fresh images without polluting library/_index.json.
        for ch in ep["chapters"]:
            a = ch.get("visual_anchor", {})
            a.pop("save_to_library_as", None)

        # Give the rendered output a distinct id so it doesn't overwrite
        # the user's "real" novels/<id>/output/ folder.
        ep["project"]["id"] = new_id

    target = PROJECT_ROOT / "in" / f"{new_id}.json"
    target.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
    return target, new_id


def run_combo(source_id: str, slug: str, engine: str, base_model: str | None) -> dict:
    """Render one combo. Returns a status dict for the summary table."""
    out_mp4 = OUTPUT_DIR / f"{slug}.mp4"
    if out_mp4.exists():
        return {"slug": slug, "status": "SKIPPED (already exists)", "path": out_mp4, "elapsed_s": 0}

    print(f"\n{'=' * 70}")
    print(f"⚡ rendering combo: {slug}")
    print(f"   engine={engine}  base_model={base_model or '(none)'}")
    print(f"{'=' * 70}")

    temp_json, new_id = make_variant_json(source_id, slug, engine, base_model)
    t0 = time.time()

    try:
        # Use the same ./novel render path the user uses normally.
        # Output lands at novels/<new_id>/output/<new_id>.mp4
        result = subprocess.run(
            ["./novel", "render", new_id],
            cwd=str(PROJECT_ROOT),
            capture_output=False,  # stream so user sees progress
        )
        if result.returncode != 0:
            return {"slug": slug, "status": f"FAILED (exit {result.returncode})", "path": None,
                    "elapsed_s": time.time() - t0}

        # Locate the produced MP4 and copy/rename it to OUTPUT_DIR
        rendered = PROJECT_ROOT / "novels" / new_id / "output" / f"{new_id}.mp4"
        if not rendered.exists():
            # Some output paths use different filenames; do a broad search
            cands = list((PROJECT_ROOT / "novels" / new_id / "output").glob("*.mp4"))
            if not cands:
                return {"slug": slug, "status": "FAILED (no mp4 produced)", "path": None,
                        "elapsed_s": time.time() - t0}
            rendered = cands[0]

        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        shutil.copy2(rendered, out_mp4)
        size_mb = out_mp4.stat().st_size / 1024 / 1024
        return {"slug": slug, "status": "OK", "path": out_mp4, "elapsed_s": time.time() - t0,
                "size_mb": size_mb}
    except KeyboardInterrupt:
        return {"slug": slug, "status": "INTERRUPTED", "path": None, "elapsed_s": time.time() - t0}
    except Exception as e:
        return {"slug": slug, "status": f"ERROR: {type(e).__name__}: {e}",
                "path": None, "elapsed_s": time.time() - t0}


def main():
    ap = argparse.ArgumentParser(description="Render an episode with every engine combo.")
    ap.add_argument("episode_id", help="Source episode (e.g. five-survivors-ep01-th)")
    ap.add_argument("--only", action="append", default=None,
                    help="Run only these slug(s). May be repeated. e.g. --only flux-schnell-4step")
    ap.add_argument("--list", action="store_true", help="List combos and exit")
    args = ap.parse_args()

    if args.list:
        print("Combos:")
        for slug, eng, base in COMBOS:
            print(f"  {slug:40s}  engine={eng:25s} base={base or '(none)'}")
        return

    selected = [(s, e, b) for (s, e, b) in COMBOS
                if args.only is None or s in args.only]
    if not selected:
        raise SystemExit("no combos matched --only filter")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"\n▶ rendering '{args.episode_id}' through {len(selected)} engine combo(s)")
    print(f"  → output: {OUTPUT_DIR}/")
    print(f"  → idempotent: existing {{slug}}.mp4 files will be skipped")

    results = []
    for slug, engine, base in selected:
        results.append(run_combo(args.episode_id, slug, engine, base))

    # Summary
    print(f"\n{'=' * 70}\nSUMMARY\n{'=' * 70}")
    for r in results:
        mins = r["elapsed_s"] / 60
        size = f"{r.get('size_mb', 0):.1f} MB" if r.get("size_mb") else ""
        print(f"  {r['slug']:40s}  {r['status']:30s}  {mins:5.1f} min  {size}")
    print(f"\n→ MP4s in: {OUTPUT_DIR}/")
    print(f"→ Play side by side to compare aesthetics.")

    ok = sum(1 for r in results if r["status"] == "OK")
    failed = sum(1 for r in results if "FAIL" in r["status"] or "ERROR" in r["status"])
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
