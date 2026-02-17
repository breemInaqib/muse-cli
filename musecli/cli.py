# museCLI ✦ calm command line reflection tool
# --------------------------------------------
# purpose:
#   this file (and the project beside it) builds a quiet space in the terminal
#   where you can check in, note a mood, and reflect without noise.
#   it is written to feel simple, almost human. every command has one small job.

# about this file:
#   cli.py is the voice. it holds the main typer app and defines each command.
#   the commands connect to helpers in nearby modules:
#       storage.py   — handles files, config, and data safety
#       model.py     — defines data shapes for entries and settings
#       formatting.py — keeps the look consistent (dates, tables, sparklines)
#       stats.py     — reads entries and builds summaries
#       editor.py    — opens your text editor for long reflections
#       insights.py  — reserved for future local summaries
#
#   together these files form a layered system:
#       cli → helpers → data → user
#   all layers stay small and clear so nothing feels heavy.

# vibe protocol:
#   - code should read like calm conversation
#   - comments explain intent, not syntax
#   - print statements sound human and finish clean
#   - no network calls, no tracking, everything offline
#   - default behaviour works even with zero setup

# design logic:
#   each command is a short story:
#       check_in  — record mood and quick note
#       today     — list today’s entries
#       stats     — show last seven days
#       export    — write data to csv/jsonl
#       reflect   — open editor for deeper thought
#       settings  — view or change preferences

# next to this file:
#   storage.py:  safely writes and reads jsonl entries; creates folders when needed.
#   model.py:    defines the Entry and Config dataclasses used everywhere else.
#   formatting.py: converts raw data into readable output, formats dates using config.
#   stats.py:    summarises entries by day and mood for sparkline display.
#   editor.py:   finds $EDITOR or defaults to nano; handles long note capture.
#   insights.py: placeholder for later—will summarise trends if called.

# how to work with it:
#   - read each command like a paragraph: short, direct, one emotion per line.
#   - when adding a new feature, start with the story (“what should the user feel?”).
#   - write the comment first, then the code that makes it true.

# guiding mood:
#   think of this as a breathing terminal—slow, clear, honest.
#   museCLI is not about productivity metrics; it’s about noticing yourself.
#
# proceed with that energy.

from __future__ import annotations

import csv
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import typer

from . import __version__
from .editor import launch_editor
from .formatting import (
    format_date,
    format_local_time,
    join_tags,
    render_table,
    sparkline,
    truncate,
    day_header,
)
from .model import AppConfig, JournalEntry
from .stats import summarise
from .storage import (
    append_entry,
    ensure_export_dir,
    iter_entries,
    iter_entries_between,
    load_config,
    read_entries_for_day,
    save_config,
)

app = typer.Typer(
    help="MuseCLI: quiet mood and reflection logging.",
    no_args_is_help=True,
)

_NOTE_WIDTH = 48


def get_config(ctx: typer.Context) -> AppConfig:
    """Return the loaded configuration from the Typer context."""
    obj = ctx.obj or {}
    config = obj.get("config")
    if config is None:
        typer.echo("configuration missing; run the command again", err=True)
        raise typer.Exit(code=1)
    return config


def set_config(ctx: typer.Context, config: AppConfig) -> None:
    """Persist the configuration in the Typer context."""
    if ctx.obj is None:
        ctx.obj = {}
    ctx.obj["config"] = config


@app.callback()
def initialise(
    ctx: typer.Context,
    data_dir: Optional[Path] = typer.Option(
        None,
        help="Override the data directory for this invocation.",
    ),
) -> None:
    """Load configuration once per invocation."""
    base = data_dir.expanduser() if data_dir else None
    config, warning = load_config(base_dir=base)
    set_config(ctx, config)
    if warning:
        typer.echo(
            "Config file was malformed. Defaults loaded. Run 'muse settings --reset'.",
            err=True,
        )


@app.command()
def version() -> None:
    """Show the current MuseCLI version."""
    typer.echo(__version__)


@app.command("check-in")
def check_in(
    ctx: typer.Context,
    mood: Optional[int] = typer.Option(
        None,
        "--mood",
        "-m",
        help="Mood rating 1-5.",
    ),
    tags: Optional[str] = typer.Option(
        None,
        "--tags",
        "-t",
        help="Comma separated tags.",
    ),
    note: Optional[str] = typer.Option(
        None,
        "--note",
        "-n",
        help="Short one line note.",
    ),
    long_note: Optional[str] = typer.Option(
        None,
        "--long-note",
        help="Detailed reflection text supplied noninteractively.",
    ),
    open_editor: Optional[bool] = typer.Option(
        None,
        "--open-editor/--skip-editor",
        help="Open the configured editor for a longer reflection.",
    ),
    editor_override: Optional[str] = typer.Option(
        None,
        "--editor",
        help="Override the editor command for this entry.",
    ),
) -> None:
    """Capture a new mood check-in."""
    config = get_config(ctx)
    rating = _resolve_mood(mood)
    tag_values = _resolve_tags(tags)
    note_text = _resolve_note(note)
    reflection_text = _resolve_long_note(
        long_note=long_note,
        open_editor=open_editor,
        editor_override=editor_override,
        config=config,
    )
    timestamp = datetime.now(timezone.utc)
    entry = JournalEntry(
        timestamp=timestamp,
        mood=rating,
        tags=tag_values,
        note=note_text,
        long_note=reflection_text,
    )
    _save_entry(entry, config, success_message="Check-in saved.")


@app.command()
def today(
    ctx: typer.Context,
    date_override: Optional[str] = typer.Option(
        None,
        "--date",
        help="Display entries for the given YYYY-MM-DD date.",
    ),
) -> None:
    """Show today's entries in a compact table."""
    config = get_config(ctx)
    target_date = _parse_date(date_override, option="--date") if date_override else datetime.now().astimezone().date()
    entries = read_entries_for_day(target_date, config)
    date_label = format_date(target_date, pattern=config.date_format)
    if not entries:
        typer.echo(f"No entries for {date_label} yet.")
        return
    typer.echo(f"Entries for {date_label} (local time)")
    rows = [
        (
            format_local_time(entry.timestamp),
            str(entry.mood),
            join_tags(entry.tags),
            truncate(entry.note, _NOTE_WIDTH),
        )
        for entry in entries
    ]
    typer.echo(render_table(["time", "mood", "tags", "note"], rows))
    typer.echo("Today listed.")


@app.command()
def timeline(
    ctx: typer.Context,
    days: int = typer.Option(
        7,
        min=1,
        help="days to list.",
    ),
    tag: Optional[str] = typer.Option(
        None,
        "--tag",
        help="filter by tag.",
    ),
) -> None:
    """browse recent entries."""
    config = get_config(ctx)
    end_date = datetime.now().astimezone().date()
    start_date = end_date - timedelta(days=days - 1)
    entries = list(iter_entries(start_date, end_date, config))
    if tag:
        tag_lower = tag.strip().lower()
        entries = [
            entry
            for entry in entries
            if any(token.lower() == tag_lower for token in entry.tags)
        ]
    if not entries:
        typer.echo(f"no entries in the last {days} days")
        return
    grouped: dict[date, list[JournalEntry]] = {}
    for entry in entries:
        local_day = entry.timestamp.astimezone().date()
        grouped.setdefault(local_day, []).append(entry)
    for day in sorted(grouped, reverse=True):
        label = day_header(day, pattern=config.date_format)
        typer.echo(label)
        rows = [
            (
                format_local_time(item.timestamp),
                str(item.mood),
                join_tags(item.tags),
                truncate(item.note, _NOTE_WIDTH),
            )
            for item in sorted(grouped[day], key=lambda value: value.timestamp)
        ]
        typer.echo(render_table(["time", "mood", "tags", "note"], rows))
        typer.echo("")
    typer.echo("timeline ready.")


@app.command()
def stats(
    ctx: typer.Context,
    days: int = typer.Option(
        7,
        min=1,
        help="Number of days to summarise ending with the end date.",
    ),
    end: Optional[str] = typer.Option(
        None,
        help="Window end date in YYYY-MM-DD. Defaults to today.",
    ),
) -> None:
    """Summarise recent entries with counts, averages, and tags."""
    config = get_config(ctx)
    end_date = _parse_date(end, option="--end") if end else datetime.now().astimezone().date()
    start_date = end_date - timedelta(days=days - 1)
    entries = list(iter_entries_between(start_date, end_date, config))
    summary = summarise(entries, start=start_date, end=end_date)
    start_label = format_date(summary.start, pattern=config.date_format)
    end_label = format_date(summary.end, pattern=config.date_format)
    typer.echo(f"Window: {start_label} → {end_label}")
    typer.echo(f"Entries: {summary.count}")
    typer.echo(f"Average mood: {summary.average_mood:.2f}")
    top_tags = ", ".join(summary.top_tags) if summary.top_tags else "-"
    typer.echo(f"Top tags: {top_tags}")
    spark = sparkline(summary.daily_averages)
    typer.echo(f"Sparkline: {spark}")
    typer.echo("Stats ready.")


@app.command()
def export(
    ctx: typer.Context,
    format_: str = typer.Option(
        "csv",
        "--format",
        "-f",
        help="Export format: csv or jsonl.",
        show_default=True,
    ),
    output: Optional[Path] = typer.Option(
        None,
        "--output",
        "-o",
        help="Path to save the export. Defaults to the configured export dir.",
    ),
    start: Optional[str] = typer.Option(
        None,
        help="Start date in YYYY-MM-DD. Overrides --days.",
    ),
    end: Optional[str] = typer.Option(
        None,
        help="End date in YYYY-MM-DD. Defaults to today.",
    ),
    days: int = typer.Option(
        7,
        min=1,
        help="Number of days to include when --start is not supplied.",
    ),
) -> None:
    """Export entries to CSV or JSONL within a date window."""
    config = get_config(ctx)
    fmt = format_.lower()
    if fmt not in {"csv", "jsonl"}:
        typer.echo("Format must be 'csv' or 'jsonl'.", err=True)
        raise typer.Exit(code=1)
    if start:
        start_date = _parse_date(start, option="--start")
        end_date = _parse_date(end, option="--end") if end else start_date
    else:
        end_date = _parse_date(end, option="--end") if end else datetime.now().astimezone().date()
        start_date = end_date - timedelta(days=days - 1)
    if start_date > end_date:
        typer.echo("Start date must be on or before end date.", err=True)
        raise typer.Exit(code=1)
    entries = list(iter_entries_between(start_date, end_date, config))
    if output:
        target_path = output.expanduser()
        if target_path.is_dir():
            default_name = _default_export_name(start_date, end_date, fmt)
            target_path = target_path / default_name
    else:
        export_dir = ensure_export_dir(config)
        default_name = _default_export_name(start_date, end_date, fmt)
        target_path = export_dir / default_name
    target_path.parent.mkdir(parents=True, exist_ok=True)
    if fmt == "csv":
        _write_csv_export(entries, target_path)
    else:
        _write_jsonl_export(entries, target_path)
    typer.echo(f"Export saved to {target_path}")


@app.command()
def reflect(
    ctx: typer.Context,
    mood: Optional[int] = typer.Option(
        None,
        "--mood",
        "-m",
        help="Mood rating 1-5.",
    ),
    tags: Optional[str] = typer.Option(
        None,
        "--tags",
        "-t",
        help="Comma separated tags.",
    ),
    note: Optional[str] = typer.Option(
        None,
        "--note",
        "-n",
        help="Optional short label for this reflection.",
    ),
    editor_override: Optional[str] = typer.Option(
        None,
        "--editor",
        help="Override the editor command just for this reflection.",
    ),
) -> None:
    """Capture a longer reflection using the configured editor."""
    config = get_config(ctx)
    rating = _resolve_mood(mood)
    tag_values = _resolve_tags(tags)
    note_text = _resolve_note(note)
    template = _reflection_template()
    try:
        content = launch_editor(config, initial=template, override=editor_override)
    except Exception as exc:  # noqa: BLE001
        typer.echo(f"Could not open editor: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    cleaned = content.strip()
    if not cleaned:
        typer.echo("Reflection cancelled.")
        return
    entry = JournalEntry(
        timestamp=datetime.now(timezone.utc),
        mood=rating,
        tags=tag_values,
        note=note_text,
        long_note=cleaned,
    )
    _save_entry(entry, config, success_message="Reflection saved.")


@app.command()
def settings(
    ctx: typer.Context,
    key: Optional[str] = typer.Option(
        None,
        "--key",
        "-k",
        help="Config key to update.",
    ),
    value: Optional[str] = typer.Option(
        None,
        "--value",
        "-v",
        help="New value for the specified key.",
    ),
    reset: bool = typer.Option(
        False,
        "--reset",
        help="Reset config values (except data_dir) to defaults.",
    ),
) -> None:
    """Show or update configuration values."""
    config = get_config(ctx)
    if reset:
        reset_config = AppConfig.defaults(base_dir=config.data_dir)
        save_config(reset_config)
        set_config(ctx, reset_config)
        typer.echo("Settings reset to defaults.")
        return
    if key:
        if value is None:
            typer.echo("Provide --value when using --key.", err=True)
            raise typer.Exit(code=1)
        updated = _update_setting(config, key, value)
        save_config(updated)
        set_config(ctx, updated)
        typer.echo(f"{key} updated.")
        return
    rows = [
        ("data_dir", str(config.data_dir)),
        ("date_format", config.date_format),
        ("editor", config.editor or "-"),
        ("export_dir", str(config.export_dir)),
        ("insights_enabled", "true" if config.insights_enabled else "false"),
        ("debug", "true" if config.debug else "false"),
    ]
    typer.echo(render_table(["key", "value"], rows))
    typer.echo("Settings listed.")


def _save_entry(entry: JournalEntry, config: AppConfig, *, success_message: str) -> None:
    """Append an entry and emit a single success line."""
    try:
        path, created = append_entry(entry, config)
    except OSError as exc:
        typer.echo(f"Could not write entry: {exc.strerror or exc}", err=True)
        raise typer.Exit(code=1) from exc
    if created:
        typer.echo(f"Journal folder created at {path.parent}")
    typer.echo(success_message)


def _resolve_mood(explicit: Optional[int]) -> int:
    """Validate or prompt for the mood rating."""
    if explicit is not None:
        if 1 <= explicit <= 5:
            return explicit
        typer.echo("Mood must be between 1 and 5.", err=True)
        raise typer.Exit(code=1)
    attempts = 0
    while attempts < 2:
        raw = typer.prompt("Mood (1-5)")
        try:
            value = int(raw)
        except ValueError:
            value = 0
        if 1 <= value <= 5:
            return value
        attempts += 1
        if attempts >= 2:
            typer.echo("Mood must be between 1 and 5. Aborting.", err=True)
            raise typer.Exit(code=1)
        typer.echo("Mood must be between 1 and 5. Try once more.")
    raise typer.Exit(code=1)


def _resolve_tags(explicit: Optional[str]) -> tuple[str, ...]:
    """Collect tags from flags or prompt."""
    raw = explicit
    if raw is None:
        raw = typer.prompt(
            "Tags (comma separated, optional)",
            default="",
            show_default=False,
        )
    return tuple(token.strip() for token in raw.split(",") if token.strip())


def _resolve_note(explicit: Optional[str]) -> str:
    """Collect the short note."""
    if explicit is not None:
        return explicit.strip()
    return typer.prompt(
        "One line note (optional)",
        default="",
        show_default=False,
    ).strip()


def _resolve_long_note(
    *,
    long_note: Optional[str],
    open_editor: Optional[bool],
    editor_override: Optional[str],
    config: AppConfig,
) -> Optional[str]:
    """Resolve the reflection text through flags or editor prompts."""
    if long_note is not None:
        return long_note.strip() or None
    should_open: bool
    if open_editor is None:
        should_open = typer.confirm(
            "Open editor for a longer reflection?",
            default=False,
        )
    else:
        should_open = open_editor
    if not should_open:
        return None
    try:
        content = launch_editor(config, initial="", override=editor_override)
    except Exception as exc:  # noqa: BLE001
        typer.echo(f"Could not open editor: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    return content.strip() or None


def _parse_date(value: Optional[str], *, option: str) -> date:
    """Parse a YYYY-MM-DD string into a date."""
    if value is None:
        raise ValueError("date value is required")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        typer.echo(f"Invalid {option} value. Use YYYY-MM-DD.", err=True)
        raise typer.Exit(code=1) from exc


def _default_export_name(start: date, end: date, fmt: str) -> str:
    """Build a default export filename."""
    return f"muse_{start.isoformat()}_{end.isoformat()}.{fmt}"


def _write_csv_export(entries: list[JournalEntry], path: Path) -> None:
    """Write entries to CSV with a fixed header order."""
    fieldnames = ["timestamp", "mood", "tags", "note", "long_note"]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for entry in entries:
            writer.writerow(
                {
                    "timestamp": entry.timestamp.astimezone(timezone.utc).isoformat(),
                    "mood": entry.mood,
                    "tags": ",".join(entry.tags),
                    "note": entry.note,
                    "long_note": entry.long_note or "",
                }
            )


def _write_jsonl_export(entries: list[JournalEntry], path: Path) -> None:
    """Write entries to a JSONL file."""
    with path.open("w", encoding="utf-8") as handle:
        for entry in entries:
            handle.write(json.dumps(entry.to_dict(), ensure_ascii=True) + "\n")


def _update_setting(config: AppConfig, key: str, value: str) -> AppConfig:
    """Update a configuration key and return a new config instance."""
    key_lower = key.replace("-", "_").lower()
    if key_lower not in {
        "data_dir",
        "date_format",
        "editor",
        "export_dir",
        "insights_enabled",
        "debug",
    }:
        typer.echo(
            "Unknown key. Valid keys: data_dir, date_format, editor, export_dir, insights_enabled, debug.",
            err=True,
        )
        raise typer.Exit(code=1)
    data = config.to_dict()
    if key_lower in {"data_dir", "export_dir"}:
        if not value.strip():
            typer.echo("Paths cannot be empty.", err=True)
            raise typer.Exit(code=1)
        path_value = Path(value).expanduser()
        data[key_lower] = str(path_value)
    elif key_lower in {"insights_enabled", "debug"}:
        normalised = value.strip().lower()
        if normalised not in {"true", "false"}:
            typer.echo("Boolean values must be 'true' or 'false'.", err=True)
            raise typer.Exit(code=1)
        data[key_lower] = normalised == "true"
    elif key_lower == "editor":
        trimmed = value.strip()
        data[key_lower] = trimmed or None
    else:
        data[key_lower] = value
    updated = AppConfig.from_dict(data, base_dir=Path(data["data_dir"]))
    if key_lower == "data_dir":
        updated.data_dir = Path(data["data_dir"]).expanduser()
    return updated


def _reflection_template() -> str:
    """Provide a calm template for reflections."""
    local_now = datetime.now().astimezone()
    return (
        f"reflection started {local_now.strftime('%Y-%m-%d %H:%M %Z')}\n"
        "\n"
        "what feels present?\n\n"
        "where did you notice ease?\n\n"
        "what would you like to remember?\n"
    )


if __name__ == "__main__":
    app()
