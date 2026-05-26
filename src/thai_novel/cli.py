"""
thai-novel CLI.

Invoked as `./novel <verb> [<id>]` (via the bash wrapper at the project root)
or as `python -m thai_novel <verb>` / `thai-novel <verb>`.
"""

from __future__ import annotations

import asyncio
import json
import logging
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
from .spec import Episode, load_episodes

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
        candidates = sorted(
            p for p in IN_DIR.glob("*.json")
            if not p.name.startswith("_") and not p.stem.endswith(".example")
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
    if warnings:
        console.print("\n[yellow]Pacing warnings:[/yellow]")
        for w in warnings:
            console.print(w)

    console.print("\n[green]All specs valid.[/green]")


@app.command()
def new(
    id_: Annotated[str, typer.Argument(help="Episode id (slug-safe).")],
    from_: Annotated[str, typer.Option("--from", help="Template name to copy.")] = "example",
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
) -> None:
    """
    Build every episode end-to-end: narrate → images → timeline → compose → mux.

    BATCH MODE: with no argument, processes EVERY .json in ./in/ sequentially
    (one episode at a time, since each render already saturates 3 workers).
    Each JSON can itself contain a single Episode or an array of Episodes —
    both forms are flattened into one queue.

    Failure handling: a failed episode is reported but the batch continues
    unless --stop-on-error is set. A summary table is printed at the end.
    """
    _setup_logging(verbose)
    pairs = _load_all_episodes(id_or_path)

    from .narration import narrate_episode
    from .images import resolve_episode
    from .timeline import compile_timeline
    from .compose import compose_video
    from .encode import finalize

    # ── Queue summary ────────────────────────────────────────────────────────
    if len(pairs) > 1:
        console.print(
            Panel.fit(
                f"[bold]batch render[/bold]: {len(pairs)} episodes queued\n"
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
