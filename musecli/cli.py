"""Typer entry point for museCLI."""

from __future__ import annotations

from collections.abc import Iterable
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import TextIO

import click
import typer
from typer.core import TyperGroup

from .config import AppConfig, config_path, load_config, save_config
from .journal import JournalEntry, append_entry, read_entries_for_day
from .queue import add_item, discard_item, inbox_count, init_db, keep_item, list_inbox_items, list_pinned_items
from .utils import ClipboardUnavailableError, read_clipboard_text, truncate, utc_now

_TEXT_WIDTH = 60
_INDENT = "  "
_INBOX_PROMPT = "[k] keep   [d] discard   [p] pin   [q] quit"
_FOCUS_PROMPT = "[d] done   [q] quit"
_CLI_HELP = """
museCLI keeps local capture, focus, and reflection in one calm workflow.

\b
Flow:
  add -> inbox -> focus -> check-in -> today

\b
Run `muse` with no arguments for a focus snapshot.
""".strip()


class MuseGroup(TyperGroup):
    """Normalize Click/Typer parse errors into CLI-controlled messages."""

    def main(
        self,
        args: list[str] | None = None,
        prog_name: str | None = None,
        complete_var: str | None = None,
        standalone_mode: bool = True,
        windows_expand_args: bool = True,
        **extra: object,
    ) -> object:
        try:
            result = super().main(
                args=args,
                prog_name=prog_name,
                complete_var=complete_var,
                standalone_mode=False,
                windows_expand_args=windows_expand_args,
                **extra,
            )
            if standalone_mode and isinstance(result, int):
                raise SystemExit(result)
            return result
        except click.ClickException as exc:
            if not standalone_mode:
                raise
            click.echo(_click_error_message(exc), err=True)
            raise SystemExit(exc.exit_code)
        except click.Abort:
            if not standalone_mode:
                raise
            click.echo("error: aborted", err=True)
            raise SystemExit(1)
        except click.exceptions.Exit as exc:
            if not standalone_mode:
                raise
            raise SystemExit(exc.exit_code)


app = typer.Typer(
    name="muse",
    cls=MuseGroup,
    help=_CLI_HELP,
    add_completion=False,
    rich_markup_mode=None,
)


def _get_config(ctx: typer.Context) -> AppConfig:
    config = (ctx.obj or {}).get("config")
    if config is None:
        _fail("error: configuration missing")
    return config


def _set_context(ctx: typer.Context, *, config: AppConfig) -> None:
    if ctx.obj is None:
        ctx.obj = {}
    ctx.obj["config"] = config


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    data_dir: Path | None = typer.Option(None, help="Override the data directory for this invocation."),
) -> None:
    """Load config once per invocation and show the default home view."""
    if ctx.resilient_parsing:
        return
    base_dir = data_dir.expanduser() if data_dir else None
    config, warning = load_config(base_dir=base_dir)
    _set_context(ctx, config=config)
    if warning:
        typer.echo("error: config file was malformed; defaults were loaded", err=True)
    if ctx.invoked_subcommand is not None:
        return
    try:
        init_db(config)
    except (OSError, sqlite3.Error):
        _fail("error: could not initialize storage")
    if not config_path(config).exists():
        try:
            save_config(config)
        except OSError:
            _fail("error: could not save config")
    try:
        _echo_lines(_home_lines(config))
    except (RuntimeError, OSError, sqlite3.Error):
        _fail("error: could not load home")
    raise typer.Exit()


@app.command()
def add(
    ctx: typer.Context,
    text: str | None = typer.Argument(None),
    stdin: bool = typer.Option(False, "--stdin", help="Read from stdin"),
    clipboard: bool = typer.Option(False, "--clipboard", help="Read from clipboard"),
) -> None:
    """Capture an inbox item."""
    modes = sum((text is not None, stdin, clipboard))
    if modes == 0:
        _fail("error: provide text, --stdin, or --clipboard")
    if modes > 1:
        _fail("error: provide only one of text, --stdin, or --clipboard")

    if stdin:
        body = sys.stdin.read().strip()
    elif clipboard:
        try:
            body = read_clipboard_text().strip()
        except ClipboardUnavailableError:
            _fail("error: clipboard unavailable")
    else:
        body = (text or "").strip()

    if not body:
        _fail("error: entry content is empty")

    try:
        add_item(_get_config(ctx), text=body)
    except ValueError as exc:
        _fail(f"error: {exc}")
    except (RuntimeError, OSError, sqlite3.Error):
        _fail("error: could not write item")
    typer.echo("added")


@app.command()
def inbox(ctx: typer.Context) -> None:
    """Process inbox items."""
    config = _get_config(ctx)
    stream = None if sys.stdin.isatty() else typer.get_text_stream("stdin")
    try:
        items = list_inbox_items(config)
    except (RuntimeError, OSError, sqlite3.Error):
        _fail("error: could not read queue")
    if not items:
        _echo_lines(_render_view("inbox", _render_empty()))
        return

    for index, item in enumerate(items):
        _echo_lines(_render_interaction("inbox", item.text, _INBOX_PROMPT, first=index == 0))
        choice = _read_choice(("k", "d", "p", "q"), _INBOX_PROMPT, stream=stream)
        if choice == "q":
            return
        if choice == "k":
            try:
                keep_item(config, item_id=item.id, pinned=False)
            except (KeyError, RuntimeError, OSError, sqlite3.Error):
                _fail("error: could not update item")
            continue
        if choice == "d":
            try:
                discard_item(config, item_id=item.id)
            except (KeyError, RuntimeError, OSError, sqlite3.Error):
                _fail("error: could not update item")
            continue
        try:
            keep_item(config, item_id=item.id, pinned=True)
        except (KeyError, RuntimeError, OSError, sqlite3.Error):
            _fail("error: could not update item")


@app.command()
def focus(ctx: typer.Context) -> None:
    """Manage and complete focus items."""
    config = _get_config(ctx)
    stream = None if sys.stdin.isatty() else typer.get_text_stream("stdin")
    try:
        items = list_pinned_items(config)
    except (RuntimeError, OSError, sqlite3.Error):
        _fail("error: could not read queue")
    if not items:
        _echo_lines(_render_view("focus", _render_empty()))
        return

    for index, item in enumerate(items):
        _echo_lines(_render_interaction("focus", item.text, _FOCUS_PROMPT, first=index == 0))
        choice = _read_choice(("d", "q"), _FOCUS_PROMPT, stream=stream)
        if choice == "q":
            return
        try:
            discard_item(config, item_id=item.id)
        except (KeyError, RuntimeError, OSError, sqlite3.Error):
            _fail("error: could not update item")


@app.command("check-in")
def check_in(
    ctx: typer.Context,
    mood: str | None = typer.Option(None, "--mood", help="Mood rating 1-5."),
    note: str | None = typer.Option(None, "--note", help="Short reflection note."),
) -> None:
    """Capture a journal check-in."""
    resolved_mood, resolved_note = _resolve_check_in_input(mood=mood, note=note)
    entry = JournalEntry(
        timestamp=utc_now(),
        mood=resolved_mood,
        note=resolved_note,
    )
    try:
        append_entry(entry, _get_config(ctx))
    except ValueError as exc:
        _fail(f"error: {exc}")
    except (OSError, sqlite3.Error):
        _fail("error: could not write check-in")
    typer.echo("saved")


@app.command()
def today(ctx: typer.Context) -> None:
    """Show today's check-ins."""
    try:
        entries = read_entries_for_day(datetime.now().astimezone().date(), _get_config(ctx))
    except OSError:
        _fail("error: could not read today")
    _echo_lines(_today_lines(entries))


def _home_lines(config: AppConfig) -> list[str]:
    entries = read_entries_for_day(datetime.now().astimezone().date(), config)
    focus_items = list_pinned_items(config)[:3]
    lines = _render_view("museCLI", _render_detail(f"inbox: {inbox_count(config)}"))
    lines.append("")
    lines.append("focus")
    if focus_items:
        lines.extend(_render_list(item.text for item in focus_items))
    else:
        lines.extend(_render_empty())
    lines.append("")
    lines.append("today")
    entry = _latest_entry(entries)
    if entry is None:
        lines.extend(_render_detail("no check-in"))
    else:
        lines.extend(_render_details([("mood", str(entry.mood)), ("note", _item_text(entry.note))]))
    return lines


def _today_lines(entries: list[JournalEntry]) -> list[str]:
    lines = _render_view("today", [])
    entry = _latest_entry(entries)
    if entry is None:
        lines.extend(_render_detail("no check-in"))
        return lines
    lines.extend(_render_details([("mood", str(entry.mood)), ("note", _item_text(entry.note))]))
    return lines


def _latest_entry(entries: list[JournalEntry]) -> JournalEntry | None:
    return entries[-1] if entries else None


def _item_text(text: str) -> str:
    return truncate(" ".join(text.split()), _TEXT_WIDTH)


def _render_view(title: str, body: list[str]) -> list[str]:
    return [title, "", *body]


def _render_interaction(title: str, text: str, prompt: str, *, first: bool) -> list[str]:
    lines = _render_view(title, []) if first else [""]
    lines.extend([_indent(_item_text(text)), "", _prompt_line(prompt)])
    return lines


def _render_empty() -> list[str]:
    return [_indent("empty")]


def _render_detail(text: str) -> list[str]:
    return [_indent(text)]


def _render_details(entries: list[tuple[str, str]]) -> list[str]:
    return [_indent(f"{label}: {value}") for label, value in entries]


def _render_list(items: Iterable[str]) -> list[str]:
    return [_indent(f"- {_item_text(text)}") for text in items]


def _indent(text: str) -> str:
    return f"{_INDENT}{text}"


def _prompt_line(prompt: str) -> str:
    return _indent(prompt)


def _echo_lines(lines: list[str]) -> None:
    typer.echo("\n".join(lines))


def _read_choice(valid: tuple[str, ...], prompt: str, *, stream: TextIO | None = None) -> str:
    while True:
        if sys.stdin.isatty():
            try:
                choice = click.getchar()
            except (KeyboardInterrupt, EOFError):
                return "q"
        else:
            active_stream = stream or typer.get_text_stream("stdin")
            choice = active_stream.read(1)
            if choice == "":
                return "q"
        if choice in {"\r", "\n"}:
            continue
        normalized = choice.lower()
        if normalized in valid:
            return normalized
        typer.echo(_indent(f"error: choose {_choice_error_options(valid)}"), err=True)
        typer.echo(_prompt_line(prompt))


def _choice_error_options(valid: tuple[str, ...]) -> str:
    if len(valid) == 1:
        return valid[0]
    if len(valid) == 2:
        return f"{valid[0]} or {valid[1]}"
    return f"{', '.join(valid[:-1])}, or {valid[-1]}"


def _resolve_check_in_input(
    *,
    mood: str | None,
    note: str | None,
) -> tuple[int, str]:
    raw_mood = mood.strip() if mood is not None else None
    raw_note = note.strip() if note is not None else None

    if not raw_mood:
        _fail("error: provide --mood")
    if not raw_note:
        _fail("error: provide --note")
    return _parse_mood(raw_mood), raw_note


def _parse_mood(raw: str) -> int:
    try:
        value = int(raw)
    except ValueError:
        _fail("error: mood must be 1–5")
        raise AssertionError("unreachable")
    if not 1 <= value <= 5:
        _fail("error: mood must be 1–5")
    return value


def _click_error_message(exc: click.ClickException) -> str:
    if isinstance(exc, click.BadOptionUsage):
        option = _option_name(getattr(exc, "option_name", None), exc.format_message())
        if "requires an argument" in exc.format_message() and option:
            if option == "--mood":
                return "error: provide --mood"
            if option == "--note":
                return "error: provide --note"
            return f"error: provide {option}"
    if isinstance(exc, click.MissingParameter):
        param = getattr(exc, "param", None)
        if param is not None and getattr(param, "opts", None):
            option = param.opts[0]
            if option == "--mood":
                return "error: provide --mood"
            if option == "--note":
                return "error: provide --note"
            return f"error: provide {option}"
    if isinstance(exc, click.NoSuchOption):
        option = _option_name(getattr(exc, "option_name", None), exc.format_message())
        if option:
            return f"error: unexpected option {option}"
    message = exc.format_message()
    if message.startswith("Got unexpected extra argument") or message.startswith("Got unexpected extra arguments"):
        return "error: unexpected argument"
    if message.startswith("No such command"):
        command = message.split(":", 1)[1].strip()
        return f"error: unexpected command {command}"
    return "error: invalid input"


def _option_name(raw: object, message: str) -> str | None:
    if isinstance(raw, str) and raw.strip():
        value = raw.strip()
        return value if value.startswith("-") else f"--{value}"
    for token in message.replace(".", "").split():
        if token.startswith("-"):
            return token
    return None


def _fail(message: str, *, code: int = 1) -> None:
    typer.echo(message, err=True)
    raise typer.Exit(code=code)
