"""Read-only CLI for discovering and inspecting muse-code workflow evidence."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer

from .agent.audit import AuditLogError, JsonlTraceStore
from .config import AppConfig, load_config
from .workflow_index import load_workflow_index, render_workflow_index
from .workflow_view import render_workflow

_HELP = """
Discover and inspect local coding-agent workflow evidence.

\b
Runs are read from the active museCLI data directory. These commands never
execute a tool or change a recorded workflow.
""".strip()

app = typer.Typer(
    name="muse-code",
    help=_HELP,
    add_completion=False,
    no_args_is_help=True,
    rich_markup_mode=None,
)


@app.callback()
def main() -> None:
    """Discover and inspect saved muse-code runs."""


@app.command("list")
def list_runs(
    data_dir: Optional[Path] = typer.Option(
        None,
        "--data-dir",
        help="Override the museCLI data directory.",
    ),
) -> None:
    """List saved runs with recomputed trace-control status."""
    config = _load_code_config(data_dir)
    store = JsonlTraceStore(config.data_dir / "agent" / "runs")
    try:
        entries = load_workflow_index(store)
    except OSError:
        _fail("error: could not list run evidence")
    typer.echo("\n".join(render_workflow_index(entries)))


@app.command("inspect")
def inspect_run(
    run_id: str = typer.Argument(..., help="Run identifier to inspect."),
    data_dir: Optional[Path] = typer.Option(
        None,
        "--data-dir",
        help="Override the museCLI data directory.",
    ),
) -> None:
    """Show intent, actions, checks, and evidence for one recorded run."""
    config = _load_code_config(data_dir)
    store = JsonlTraceStore(config.data_dir / "agent" / "runs")
    try:
        path = store.path_for(run_id)
    except ValueError:
        _fail("error: invalid run id")
    if not path.exists():
        _fail(f"error: run not found: {run_id}")
    try:
        events = store.read(run_id)
    except (AuditLogError, OSError):
        _fail("error: could not read run evidence")
    typer.echo("\n".join(render_workflow(run_id, events)))


def _load_code_config(data_dir: Optional[Path]) -> AppConfig:
    base_dir = data_dir.expanduser() if data_dir else None
    config, warning = load_config(base_dir=base_dir)
    if warning:
        typer.echo("error: config file was malformed; defaults were loaded", err=True)
    return config


def _fail(message: str) -> None:
    typer.echo(message, err=True)
    raise typer.Exit(code=1)
