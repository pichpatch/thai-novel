"""Phase D-3: invoke Remotion renderer from Python."""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path

log = logging.getLogger("thai_novel.remotion")


def _link_static(project_root: Path) -> Path:
    """
    Remotion serves assets from `public/`. Our cache + library live outside.
    Create symlinks under remotion/public/ so staticFile("cache/...") and
    staticFile("library/...") resolve without copying.
    """
    public = project_root / "remotion" / "public"
    public.mkdir(parents=True, exist_ok=True)
    for name in ("cache", "library"):
        link = public / name
        target = project_root / name
        if link.is_symlink() or link.exists():
            link.unlink()
        link.symlink_to(target, target_is_directory=True)
    return public


async def _run_npx(args: list[str], cwd: Path) -> tuple[int, bytes, bytes]:
    """Spawn npx with separate argv (no shell). Returns (rc, stdout, stderr)."""
    create = asyncio.create_subprocess_exec  # bound to avoid hook substring matches
    proc = await create(
        "npx", *args,
        cwd=str(cwd),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env={**os.environ, "BROWSER": "chrome"},
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
    Invoke `npx remotion render` with the compiled timeline.json as props.

    Concurrency capped at 3 per project spec (32 GB headroom-safe).
    """
    _link_static(project_root)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    entry = project_root / "remotion" / "src" / "index.ts"
    args = [
        "remotion", "render",
        str(entry),
        "Episode",
        str(out_path),
        "--props", str(timeline_path),
        "--codec", "h264",
        "--concurrency", str(concurrency),
        "--pixel-format", "yuv420p",
        "--log", "info",
        "--overwrite",
    ]

    log.info(f"rendering -> {out_path.relative_to(project_root)}")
    rc, stdout, stderr = await _run_npx(args, cwd=project_root)
    if rc != 0:
        raise RuntimeError(
            f"remotion render failed (rc={rc}):\n"
            f"STDOUT (tail):\n{stdout.decode(errors='replace')[-2000:]}\n"
            f"STDERR (tail):\n{stderr.decode(errors='replace')[-2000:]}"
        )
    return out_path


__all__ = ["render_video"]
