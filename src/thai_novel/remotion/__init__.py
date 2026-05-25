"""Phase D-3: invoke Remotion renderer from Python."""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
from pathlib import Path

log = logging.getLogger("thai_novel.remotion")


def _hardlink_tree(src: Path, dst: Path) -> int:
    """
    Mirror src directory tree as dst using hardlinks for files (zero disk cost
    when src/dst are on the same filesystem). Falls back to copy for cross-
    device boundaries.

    Returns the number of files materialized.
    """
    if not src.exists():
        return 0
    count = 0
    for root, _dirs, files in os.walk(src):
        rel = Path(root).relative_to(src)
        out_root = dst / rel
        out_root.mkdir(parents=True, exist_ok=True)
        for fname in files:
            sf = Path(root) / fname
            df = out_root / fname
            if df.exists():
                continue
            try:
                os.link(sf, df)
            except OSError:
                shutil.copy2(sf, df)
            count += 1
    return count


def _materialize_public(project_root: Path, episode_id: str) -> Path:
    """
    Mirror cache/<episode_id>/ + library/ into remotion/public/ as REAL files
    (hardlinks). Remotion's bundler doesn't follow symlinks when copying the
    public directory into the bundle, so symlinks here lead to broken serves
    and 404s at render time.
    """
    public = project_root / "remotion" / "public"
    public.mkdir(parents=True, exist_ok=True)

    # Clean out previous mirrors (symlinks or stale dirs)
    for name in ("cache", "library"):
        target = public / name
        if target.is_symlink():
            target.unlink()
        elif target.exists():
            shutil.rmtree(target)

    cache_count = _hardlink_tree(
        project_root / "cache" / episode_id,
        public / "cache" / episode_id,
    )
    lib_count = _hardlink_tree(
        project_root / "library",
        public / "library",
    )
    log.info(f"public/ materialized: {cache_count} cache files, {lib_count} library files")
    return public


# Back-compat alias for the preview command (which still calls _link_static).
def _link_static(project_root: Path) -> Path:
    """Best-effort static linking for preview mode (no episode known)."""
    public = project_root / "remotion" / "public"
    public.mkdir(parents=True, exist_ok=True)
    # For preview, materialize the whole cache + library tree.
    for name in ("cache", "library"):
        target = public / name
        if target.is_symlink():
            target.unlink()
        elif target.exists():
            shutil.rmtree(target)
    _hardlink_tree(project_root / "cache", public / "cache")
    _hardlink_tree(project_root / "library", public / "library")
    return public


async def _run_node(script: Path, args: list[str], cwd: Path) -> tuple[int, bytes, bytes]:
    """Spawn `node <script> <args...>` with separate argv (no shell)."""
    create = asyncio.create_subprocess_exec  # bound name
    proc = await create(
        "node", str(script), *args,
        cwd=str(cwd),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env={**os.environ},
    )
    out, err = await proc.communicate()
    return proc.returncode or 0, out, err


async def render_video(
    timeline_path: Path,
    out_path: Path,
    project_root: Path,
    concurrency: int = 3,
) -> Path:
    """
    Drive a Remotion render via scripts/render.mjs (programmatic API).

    Bypasses `npx remotion render`: the CLI --props handling doesn't reliably
    trigger calculateMetadata across Remotion 4.x point releases, so we use
    the @remotion/renderer programmatic API directly and force the right
    durationInFrames from the timeline.json.
    """
    # episode_id is the parent dir name of the timeline.json path
    # (we wrote it to cache/<episode_id>/timeline.json in the compiler)
    episode_id = timeline_path.parent.name

    _materialize_public(project_root, episode_id)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    render_script = project_root / "scripts" / "render.mjs"
    args = [str(timeline_path), str(out_path), str(concurrency)]

    log.info(f"rendering -> {out_path.relative_to(project_root)}")
    rc, stdout, stderr = await _run_node(render_script, args, cwd=project_root)
    if rc != 0:
        raise RuntimeError(
            f"remotion render failed (rc={rc}):\n"
            f"STDOUT (tail):\n{stdout.decode(errors='replace')[-2000:]}\n"
            f"STDERR (tail):\n{stderr.decode(errors='replace')[-2000:]}"
        )
    tail = stdout.decode(errors="replace").strip().split("\n")[-3:]
    for line in tail:
        if line.strip():
            log.info(line)
    return out_path


__all__ = ["render_video", "_link_static"]
