"""
thai-novel CLI.

Invoked as `./novel <verb> [<id>]` (via the bash wrapper at the project root)
or as `python -m thai_novel <verb>` / `thai-novel <verb>`.
"""

from __future__ import annotations

import asyncio
import copy
import json
import logging
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Annotated

import typer
from pydantic import ValidationError
from rich.console import Console
from rich.logging import RichHandler
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeElapsedColumn
from rich.table import Table

from . import __version__
from .spec import Episode, load_episodes, load_story_bible

# ─────────────────────────────────────────────────────────────────────────────

app = typer.Typer(
    name="thai-novel",
    help="Cinematic Thai audiobook pipeline. JSON in ./in/, MP4 out in ./novels/<id>/output/.",
    no_args_is_help=True,
    add_completion=False,
    rich_markup_mode="rich",
)
console = Console()
err_console = Console(stderr=True)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
IN_DIR = PROJECT_ROOT / "in"
NOVELS_DIR = PROJECT_ROOT / "novels"
CACHE_DIR = PROJECT_ROOT / "cache"
LIBRARY_DIR = PROJECT_ROOT / "library"


def _setup_logging(verbose: bool = False) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(message)s",
        datefmt="[%X]",
        handlers=[RichHandler(console=console, rich_tracebacks=False, show_path=False)],
    )


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


def _resolve_inputs(id_or_path: str | None) -> list[Path]:
    """
    Resolve to a LIST of input JSON paths.

    - No argument: return every non-underscore-prefixed *.json in ./in/ (sorted).
                   This is batch mode — multiple JSONs render one after another.
    - Path-like (contains /): return [that path].
    - Bare name: return [./in/<name>.json].

    Inactive specs are prefixed with `_` (e.g. `_old-draft.json`) to be ignored.
    """
    if id_or_path is None:
        # Auto-skip:
        #   - underscore-prefixed (archived/disabled specs)
        #   - *.example.json (template files — by convention)
        #   - ep0.json (story bible / AI handoff, not renderable)
        candidates = sorted(
            p for p in IN_DIR.glob("*.json")
            if (
                not p.name.startswith("_")
                and not p.stem.endswith(".example")
                and p.name != "ep0.json"
            )
        )
        if not candidates:
            err_console.print(
                "[red]ERROR:[/red] no .json files in ./in/.\n"
                "Run [bold]./novel new <name>[/bold] to scaffold one, "
                "or copy [bold]in/example.json[/bold]."
            )
            raise typer.Exit(1)
        return candidates

    if "/" in id_or_path or id_or_path.endswith(".json"):
        p = (PROJECT_ROOT / id_or_path).resolve()
        if not p.exists():
            err_console.print(f"[red]ERROR:[/red] {p} not found.")
            raise typer.Exit(1)
        return [p]

    candidate = IN_DIR / f"{id_or_path}.json"
    if candidate.exists():
        return [candidate]
    err_console.print(f"[red]ERROR:[/red] no such input: in/{id_or_path}.json")
    raise typer.Exit(1)


def _load_all_episodes(id_or_path: str | None) -> list[tuple[Path, Episode]]:
    """
    Resolve all inputs and flatten them to (path, episode) tuples.

    Each .json file may contain a single Episode object or a list of Episodes;
    both cases are flattened so the caller can iterate uniformly.
    """
    paths = _resolve_inputs(id_or_path)
    flat: list[tuple[Path, Episode]] = []
    for path in paths:
        try:
            for ep in load_episodes(path):
                flat.append((path, ep))
        except ValidationError as e:
            err_console.print(
                Panel.fit(
                    str(e),
                    title=f"[red]Schema validation failed: {path.name}[/red]",
                    border_style="red",
                )
            )
            raise typer.Exit(1)
        except ValueError as e:
            err_console.print(f"[red]ERROR:[/red] {e}")
            raise typer.Exit(1)
    if not flat:
        err_console.print("[red]ERROR:[/red] no episodes found across the given JSONs.")
        raise typer.Exit(1)
    return flat


def _summary_table(episodes: list[Episode]) -> Table:
    t = Table(title=f"Loaded {len(episodes)} episode(s)", show_lines=False)
    t.add_column("ID", style="cyan")
    t.add_column("Title")
    t.add_column("Ch", justify="right")
    t.add_column("Blocks", justify="right")
    t.add_column("Anchors", justify="right")
    t.add_column("Chars", justify="right")
    t.add_column("Hint", justify="right")
    for ep in episodes:
        block_count = sum(len(c.narration_blocks) for c in ep.chapters)
        t.add_row(
            ep.project.id, ep.project.title,
            str(len(ep.chapters)), str(block_count), str(ep.anchor_count),
            f"{ep.total_narration_chars:,}", f"{ep.estimated_duration_sec:.0f}s",
        )
    return t


def _episode_number(ep: Episode, fallback: int) -> int:
    return ep.project.episode if ep.project.episode is not None else fallback


def _episode_label(ep: Episode, fallback: int) -> str:
    n = _episode_number(ep, fallback)
    return f"ตอนที่ {n} {ep.project.title}"


def _series_slug(ep: Episode) -> str:
    """Use project.id as the ASCII-safe source for publication group ids."""
    return re.sub(r"[-_]?ep\d+$", "", ep.project.id) or ep.project.id


def _make_group_episode(items: list[tuple[Path, Episode]], group_index: int) -> Episode:
    """
    Combine up to 10 source episodes into one publication video.

    New workflow rule: one source episode becomes one visual chapter in the
    grouped video, so a 10-episode video contains 10 generated/library images.
    If a legacy source episode has multiple chapters, their narration blocks
    are flattened under the first chapter's visual anchor.
    """
    first = items[0][1]
    last = items[-1][1]
    first_no = _episode_number(first, group_index * 10 + 1)
    last_no = _episode_number(last, first_no + len(items) - 1)
    base_slug = _series_slug(first)
    group_id = f"{base_slug}-ep{first_no:02d}-ep{last_no:02d}"

    ep_dict = first.model_dump(mode="json")
    ep_dict["project"] = {
        **ep_dict["project"],
        "id": group_id,
        "title": f"ตอนที่ {first_no}-{last_no}",
        "episode": first_no,
        "short_description": "\n\n".join(
            f"{_episode_label(ep, i + 1)}\n{(ep.project.short_description or '').strip()}"
            for i, (_, ep) in enumerate(items)
        ).strip(),
        "target_duration_min": sum(
            ep.project.target_duration_min or 0 for _, ep in items
        ) or None,
    }

    # One intro and one end card for the whole publication group.
    ep_dict["intro"] = copy.deepcopy(first.intro.model_dump(mode="json"))
    ep_dict["intro"]["title_narration"] = (
        f"{first.project.series} ตอนที่ {first_no} ถึง {last_no}"
        if first.project.series else f"ตอนที่ {first_no} ถึง {last_no}"
    )

    chapters = []
    for source_idx, (_, source_ep) in enumerate(items, start=1):
        source_no = _episode_number(source_ep, source_idx)
        first_chapter = source_ep.chapters[0]
        narration_blocks = []
        block_idx = 1
        for source_chapter in source_ep.chapters:
            for block in source_chapter.narration_blocks:
                block_data = block.model_dump(mode="json")
                block_data["id"] = f"ep{source_no:02d}_b{block_idx}"
                # Publication groups enforce one image per source episode.
                block_data["anchor_override"] = None
                narration_blocks.append(block_data)
                block_idx += 1
        chapters.append({
            "id": f"ep_{source_no:02d}",
            "title": _episode_label(source_ep, source_idx),
            "show_title_card": False,
            "title_card_duration_sec": 4,
            "visual_anchor": first_chapter.visual_anchor.model_dump(
                mode="json", exclude_none=True
            ),
            "narration_blocks": narration_blocks,
        })

    ep_dict["chapters"] = chapters
    base_end_card = last.end_card or first.end_card
    ep_dict["end_card"] = (
        copy.deepcopy(base_end_card.model_dump(mode="json"))
        if base_end_card else {"show": True, "duration_sec": 8}
    )
    next_no = last_no + 1
    ep_dict["end_card"]["next_episode_title"] = f"ตอนที่ {next_no}"
    ep_dict["end_card"]["message"] = "ขอบคุณที่รับฟังกันนะครับ"

    return Episode.model_validate(ep_dict)


def _group_for_publication(
    pairs: list[tuple[Path, Episode]],
    group_size: int,
) -> list[tuple[Path, Episode]]:
    if group_size <= 1 or len(pairs) <= 1:
        return pairs
    grouped: list[tuple[Path, Episode]] = []
    for i in range(0, len(pairs), group_size):
        chunk = pairs[i:i + group_size]
        group_ep = _make_group_episode(chunk, group_index=i // group_size)
        grouped.append((chunk[0][0], group_ep))
    return grouped


# ─────────────────────────────────────────────────────────────────────────────
# Commands
# ─────────────────────────────────────────────────────────────────────────────


@app.command()
def version() -> None:
    """Print the thai-novel version."""
    console.print(f"thai-novel [bold cyan]{__version__}[/bold cyan]")


@app.command()
def doctor() -> None:
    """Check that all external tools and folders are ready."""
    console.print(Panel.fit("thai-novel doctor", style="bold cyan"))

    checks: list[tuple[str, bool, str]] = []

    py = sys.version_info
    checks.append((
        "Python ≥ 3.11",
        (py.major, py.minor) >= (3, 11),
        f"found {py.major}.{py.minor}.{py.micro}",
    ))

    ff = shutil.which("ffmpeg")
    if ff:
        out = subprocess.run(
            [ff, "-hide_banner", "-encoders"], capture_output=True, text=True
        ).stdout
        has_vt = "h264_videotoolbox" in out
        checks.append(("ffmpeg", True, "found"))
        checks.append((
            "VideoToolbox H.264", has_vt,
            "available" if has_vt else "missing (rebuild ffmpeg with --enable-videotoolbox)",
        ))
    else:
        checks.append(("ffmpeg", False, "not found — install with `brew install ffmpeg`"))

    # Thai-capable font (for card rendering via PIL)
    try:
        from .compose.cards import find_font
        font = find_font(LIBRARY_DIR)
        checks.append(("Thai font", True, font.replace(str(Path.home()), "~")))
    except Exception as e:
        checks.append(("Thai font", False, str(e)))

    for d in ("in", "novels", "library", "src/thai_novel"):
        p = PROJECT_ROOT / d
        checks.append((f"./{d}/", p.is_dir(), "ok" if p.is_dir() else "missing"))

    t = Table(show_header=True, header_style="bold")
    t.add_column("Check"); t.add_column("Status"); t.add_column("Detail")
    for name, ok, detail in checks:
        t.add_row(name, "[green]✓[/green]" if ok else "[red]✗[/red]", detail)
    console.print(t)

    failed = [name for name, ok, _ in checks if not ok]
    if failed:
        err_console.print(f"\n[red]{len(failed)} check(s) failed:[/red] {', '.join(failed)}")
        raise typer.Exit(1)
    console.print("\n[green]All checks passed.[/green]")


@app.command()
def validate(
    id_or_path: Annotated[str | None, typer.Argument(help="Episode id or path. Default: auto-pick.")] = None,
) -> None:
    """Validate the JSON spec(s) without rendering. Batches all in/*.json by default."""
    if id_or_path is not None:
        paths = _resolve_inputs(id_or_path)
        if len(paths) == 1:
            try:
                bible = load_story_bible(paths[0])
            except ValueError:
                pass
            else:
                console.print(f"Reading [cyan]{paths[0].relative_to(PROJECT_ROOT)}[/cyan]")
                console.print(
                    f"[green]Story bible valid.[/green] "
                    f"{bible.series} — {len(bible.episode_plan)} planned episode(s)"
                )
                return

    pairs = _load_all_episodes(id_or_path)
    paths_seen: list[Path] = []
    for p, _ in pairs:
        if p not in paths_seen:
            paths_seen.append(p)
    for p in paths_seen:
        console.print(f"Reading [cyan]{p.relative_to(PROJECT_ROOT)}[/cyan]")
    episodes = [ep for _, ep in pairs]
    console.print(_summary_table(episodes))

    warnings: list[str] = []
    for ep in episodes:
        for c in ep.chapters:
            for b in c.narration_blocks:
                if len(b.narration) < 800:
                    warnings.append(
                        f"  [yellow]{ep.project.id}/{c.id}/{b.id}[/yellow]: "
                        f"narration is short ({len(b.narration)} chars). Target 1500–3000."
                    )
                if len(b.narration) > 4000:
                    warnings.append(
                        f"  [yellow]{ep.project.id}/{c.id}/{b.id}[/yellow]: "
                        f"narration is long ({len(b.narration)} chars). Consider splitting."
                    )
        if ep.anchor_count > 20:
            warnings.append(
                f"  [yellow]{ep.project.id}[/yellow]: {ep.anchor_count} unique anchors. "
                f"Target ≤15."
            )
        if ep.anchor_count > 1:
            warnings.append(
                f"  [yellow]{ep.project.id}[/yellow]: {ep.anchor_count} unique anchors. "
                "New workflow target is exactly 1 image per episode."
            )
    if warnings:
        console.print("\n[yellow]Pacing warnings:[/yellow]")
        for w in warnings:
            console.print(w)

    console.print("\n[green]All specs valid.[/green]")


@app.command()
def new(
    id_: Annotated[str, typer.Argument(help="Episode id (slug-safe).")],
    from_: Annotated[str, typer.Option("--from", help="Template name to copy.")] = "template.example",
) -> None:
    """Scaffold a new episode JSON in ./in/ from a template."""
    template = IN_DIR / f"{from_}.json"
    target = IN_DIR / f"{id_}.json"
    if not template.exists():
        err_console.print(f"[red]ERROR:[/red] template not found: {template.relative_to(PROJECT_ROOT)}")
        raise typer.Exit(1)
    if target.exists():
        err_console.print(f"[red]ERROR:[/red] {target.relative_to(PROJECT_ROOT)} already exists.")
        raise typer.Exit(1)
    target.write_text(template.read_text(encoding="utf-8"), encoding="utf-8")
    console.print(
        f"[green]Created[/green] {target.relative_to(PROJECT_ROOT)}\n"
        f"Edit the JSON, then run: [bold]./novel validate {id_}[/bold]"
    )


# ─── Phase B: narrate ────────────────────────────────────────────────────────


@app.command()
def narrate(
    id_or_path: Annotated[str | None, typer.Argument()] = None,
    verbose: Annotated[bool, typer.Option("--verbose", "-v")] = False,
) -> None:
    """Synthesize narration WAVs from the JSON spec(s). Batches all in/*.json by default."""
    _setup_logging(verbose)
    episodes = [ep for _, ep in _load_all_episodes(id_or_path)]
    for ep in episodes:
        console.print(Panel.fit(f"narrate [cyan]{ep.project.id}[/cyan] — {ep.project.title}"))
        from .narration import narrate_episode

        async def _run():
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                TextColumn("{task.completed}/{task.total}"),
                TimeElapsedColumn(),
                console=console,
            ) as p:
                task = p.add_task("Synthesizing sentences", total=None)
                def cb(done, total):
                    p.update(task, completed=done, total=total)
                results = await narrate_episode(ep, PROJECT_ROOT, on_progress=cb)
                p.update(task, description="Done")
            return results

        results = asyncio.run(_run())
        total = sum(b.duration_sec for b in results)
        console.print(
            f"[green]✓[/green] {len(results)} blocks, total audio {total:.1f}s "
            f"-> [dim]cache/{ep.project.id}/[/dim]"
        )


# ─── Phase C: images ─────────────────────────────────────────────────────────


@app.command()
def images(
    id_or_path: Annotated[str | None, typer.Argument()] = None,
    force: Annotated[bool, typer.Option(help="Re-generate even if cached.")] = False,
    verbose: Annotated[bool, typer.Option("--verbose", "-v")] = False,
) -> None:
    """Resolve / generate visual anchors. Batches all in/*.json by default."""
    _setup_logging(verbose)
    episodes = [ep for _, ep in _load_all_episodes(id_or_path)]
    for ep in episodes:
        console.print(Panel.fit(f"images [cyan]{ep.project.id}[/cyan]"))
        from .images import resolve_episode

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("{task.completed}/{task.total}"),
            TimeElapsedColumn(),
            console=console,
        ) as p:
            task = p.add_task("Resolving anchors", total=None)
            def cb(done, total):
                p.update(task, completed=done, total=total)
            results = resolve_episode(ep, PROJECT_ROOT, force=force, on_progress=cb)

        kinds = {r.src_kind: 0 for r in results}
        for r in results:
            kinds[r.src_kind] += 1
        bits = ", ".join(f"{n} {k}" for k, n in kinds.items())
        console.print(f"[green]✓[/green] {len(results)} anchors ({bits})")


# ─── Render (full pipeline) ──────────────────────────────────────────────────


@app.command()
def render(
    id_or_path: Annotated[str | None, typer.Argument()] = None,
    skip_narrate: Annotated[bool, typer.Option(help="Skip narration step (cache must exist).")] = False,
    skip_images: Annotated[bool, typer.Option(help="Skip image resolution (cache must exist).")] = False,
    verbose: Annotated[bool, typer.Option("--verbose", "-v")] = False,
    stop_on_error: Annotated[bool, typer.Option(help="Stop the batch on the first failure.")] = False,
    group_size: Annotated[int, typer.Option(help="Maximum source episodes per output video. Use 1 for one MP4 per episode.")] = 10,
) -> None:
    """
    Build every episode end-to-end: narrate → images → timeline → compose → mux.

    BATCH MODE: with multiple source episodes, render publication groups of up
    to --group-size episodes per MP4. Default is 10, so ep01..ep10 become one
    video with 10 episode images and 10 YouTube-description entries.

    Failure handling: a failed episode is reported but the batch continues
    unless --stop-on-error is set. A summary table is printed at the end.
    """
    if group_size < 1 or group_size > 10:
        err_console.print("[red]ERROR:[/red] --group-size must be between 1 and 10.")
        raise typer.Exit(1)

    _setup_logging(verbose)
    source_pairs = _load_all_episodes(id_or_path)
    pairs = _group_for_publication(source_pairs, group_size)

    from .narration import narrate_episode
    from .images import resolve_episode
    from .timeline import compile_timeline
    from .compose import compose_video
    from .encode import finalize

    # ── Queue summary ────────────────────────────────────────────────────────
    if len(source_pairs) > 1:
        console.print(
            Panel.fit(
                f"[bold]batch render[/bold]: {len(source_pairs)} source episodes → "
                f"{len(pairs)} publication video(s), max {group_size} episodes each\n"
                + "\n".join(
                    f"  {i+1}. [cyan]{ep.project.id}[/cyan] — {ep.project.title}"
                    for i, (_, ep) in enumerate(pairs)
                ),
                style="cyan",
            )
        )

    # ── Render each ──────────────────────────────────────────────────────────
    results: list[dict] = []
    for i, (src_path, ep) in enumerate(pairs):
        header = (
            f"[bold cyan]render {i+1}/{len(pairs)}[/bold cyan]  "
            f"{ep.project.id} — {ep.project.title}\n"
            f"[dim]source: {src_path.relative_to(PROJECT_ROOT)}[/dim]"
        )
        console.print()
        console.print(Panel.fit(header, style="cyan"))

        out_dir = PROJECT_ROOT / "novels" / ep.project.id / "output"
        work_dir = PROJECT_ROOT / "novels" / ep.project.id / "_work"
        work_dir.mkdir(parents=True, exist_ok=True)

        try:
            if not skip_narrate:
                console.print("\n[bold]Stage 1/5: narrate[/bold]")
                blocks = asyncio.run(narrate_episode(ep, PROJECT_ROOT))
            else:
                console.print("\n[dim]Stage 1/5: narrate — using cache[/dim]")
                blocks = asyncio.run(narrate_episode(ep, PROJECT_ROOT))

            if not skip_images:
                console.print("\n[bold]Stage 2/5: images[/bold]")
                anchors = resolve_episode(ep, PROJECT_ROOT)
            else:
                console.print("\n[dim]Stage 2/5: images — using cache[/dim]")
                anchors = resolve_episode(ep, PROJECT_ROOT)

            console.print("\n[bold]Stage 3/5: compile timeline[/bold]")
            timeline_path = compile_timeline(ep, blocks, anchors, PROJECT_ROOT)
            timeline = json.loads(timeline_path.read_text(encoding="utf-8"))
            console.print(f"  total duration: [cyan]{timeline['total_duration_sec']:.1f}s[/cyan]")

            console.print("\n[bold]Stage 4/5: compose video (pure ffmpeg, ~30–90s)[/bold]")
            raw_mp4 = work_dir / "raw.mp4"
            asyncio.run(compose_video(timeline_path, raw_mp4, PROJECT_ROOT))

            console.print("\n[bold]Stage 5/5: final mux[/bold]")
            artifacts = asyncio.run(finalize(raw_mp4, timeline, PROJECT_ROOT, out_dir))

            size_mb = artifacts["mp4"].stat().st_size / 1024 / 1024
            console.print(
                f"\n[green]✓ done[/green] -> [cyan]{artifacts['mp4'].relative_to(PROJECT_ROOT)}[/cyan] "
                f"({size_mb:.1f} MB, {timeline['total_duration_sec']:.1f}s)"
            )
            results.append({
                "id": ep.project.id,
                "ok": True,
                "mp4": artifacts["mp4"],
                "duration_sec": timeline["total_duration_sec"],
                "size_mb": size_mb,
                "error": None,
            })

        except Exception as e:
            err_console.print(f"\n[red]✗ FAILED[/red] {ep.project.id}: {e}")
            results.append({
                "id": ep.project.id, "ok": False, "mp4": None,
                "duration_sec": 0, "size_mb": 0, "error": str(e),
            })
            if stop_on_error:
                err_console.print("[red]--stop-on-error set; aborting batch.[/red]")
                break

    # ── Final summary (only when batching) ───────────────────────────────────
    if len(pairs) > 1 or any(not r["ok"] for r in results):
        t = Table(title=f"Batch summary: {sum(r['ok'] for r in results)}/{len(results)} succeeded")
        t.add_column("Episode", style="cyan")
        t.add_column("Status")
        t.add_column("Duration", justify="right")
        t.add_column("Size", justify="right")
        t.add_column("Output / Error")
        for r in results:
            if r["ok"]:
                t.add_row(
                    r["id"], "[green]✓[/green]",
                    f"{r['duration_sec']:.0f}s", f"{r['size_mb']:.1f} MB",
                    str(r["mp4"].relative_to(PROJECT_ROOT)),
                )
            else:
                t.add_row(r["id"], "[red]✗[/red]", "—", "—", r["error"][:80])
        console.print()
        console.print(t)

    failures = [r for r in results if not r["ok"]]
    if failures:
        raise typer.Exit(1)


# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app()
