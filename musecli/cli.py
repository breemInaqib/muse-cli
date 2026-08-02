"""Typer entry point for museCLI."""

from __future__ import annotations

import sqlite3
import sys
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path
from typing import Optional, TextIO

import click
import typer
from typer.core import TyperGroup

from .config import AppConfig, config_path, load_config, save_config
from .journal import JournalEntry, JournalReadResult, append_entry, read_day
from .queue import (
    QueueCorruptError,
    QueueIncompatibleError,
    QueueLockedError,
    QueueStorageError,
    add_item,
    discard_item,
    inbox_count,
    init_db,
    keep_item,
    list_inbox_items,
    list_pinned_items,
)
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
Run `muse` in a terminal for the simple local session.
Use `muse --tui` for the full workspace.
Redirected no-argument use keeps the focus snapshot.
""".strip()


class MuseGroup(TyperGroup):
    """Normalize Click/Typer parse errors into CLI-controlled messages."""

    def collect_usage_pieces(self, ctx: click.Context) -> list[str]:
        """Keep optional root-command usage stable across supported Typer releases."""
        return [
            "[COMMAND] [ARGS]..." if piece == "COMMAND [ARGS]..." else piece
            for piece in super().collect_usage_pieces(ctx)
        ]

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
            raise SystemExit(exc.exit_code) from None
        except click.Abort:
            if not standalone_mode:
                raise
            click.echo("error: aborted", err=True)
            raise SystemExit(1) from None
        except click.exceptions.Exit as exc:
            if not standalone_mode:
                raise
            raise SystemExit(exc.exit_code) from None


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
    data_dir: Optional[Path] = typer.Option(
        None,
        help="Override the data directory for this invocation.",
    ),
    tui: bool = typer.Option(
        False,
        "--tui",
        help="Open the full-screen visible workspace.",
    ),
) -> None:
    """Load config once and route commands or an interactive presentation."""
    if ctx.resilient_parsing:
        return
    if tui and ctx.invoked_subcommand is not None:
        _fail("error: --tui cannot be used with a command")
    base_dir = data_dir.expanduser() if data_dir else None
    config, warning = load_config(base_dir=base_dir)
    _set_context(ctx, config=config)
    if warning:
        typer.echo("error: config file was malformed; defaults were loaded", err=True)
    if ctx.invoked_subcommand is not None:
        return
    interactive_terminal = _is_interactive_terminal()
    if tui and not interactive_terminal:
        _fail("error: --tui requires an interactive terminal")
    try:
        init_db(config)
    except QueueStorageError as exc:
        _fail_queue(exc, action="initialize storage")
    except (OSError, sqlite3.Error):
        _fail("error: could not initialize storage")
    if not config_path(config).exists():
        try:
            save_config(config)
        except OSError:
            _fail("error: could not save config")
    if tui:
        _run_interactive(config, initial_workspace=True)
        raise AssertionError("unreachable")
    if interactive_terminal:
        try:
            home_lines = _home_lines(config)
        except QueueStorageError as exc:
            _fail_queue(exc, action="load home")
        except (RuntimeError, OSError, sqlite3.Error):
            _fail("error: could not load home")
        _run_interactive(config, initial_workspace=False, home_lines=home_lines)
        raise AssertionError("unreachable")
    try:
        _echo_lines(_home_lines(config))
    except QueueStorageError as exc:
        _fail_queue(exc, action="load home")
    except (RuntimeError, OSError, sqlite3.Error):
        _fail("error: could not load home")
    raise typer.Exit()


def _is_interactive_terminal() -> bool:
    return sys.stdin.isatty() and sys.stdout.isatty()


def _run_interactive(
    config: AppConfig,
    *,
    initial_workspace: bool,
    home_lines: Iterable[str] = (),
) -> None:
    from .interactive import run_application
    from .session import Presentation, SessionController

    presentation = Presentation.WORKSPACE if initial_workspace else Presentation.SIMPLE
    exit_code = run_application(
        SessionController(config),
        initial_presentation=presentation,
        home_lines=home_lines,
    )
    raise typer.Exit(code=exit_code)


@app.command()
def add(
    ctx: typer.Context,
    text: Optional[str] = typer.Argument(None),
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
    except QueueStorageError as exc:
        _fail_queue(exc, action="write item")
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
    except QueueStorageError as exc:
        _fail_queue(exc, action="read queue")
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
            except QueueStorageError as exc:
                _fail_queue(exc, action="update item")
            except (KeyError, RuntimeError, OSError, sqlite3.Error):
                _fail("error: could not update item")
            continue
        if choice == "d":
            try:
                discard_item(config, item_id=item.id)
            except QueueStorageError as exc:
                _fail_queue(exc, action="update item")
            except (KeyError, RuntimeError, OSError, sqlite3.Error):
                _fail("error: could not update item")
            continue
        try:
            keep_item(config, item_id=item.id, pinned=True)
        except QueueStorageError as exc:
            _fail_queue(exc, action="update item")
        except (KeyError, RuntimeError, OSError, sqlite3.Error):
            _fail("error: could not update item")


@app.command()
def focus(ctx: typer.Context) -> None:
    """Manage and complete focus items."""
    config = _get_config(ctx)
    stream = None if sys.stdin.isatty() else typer.get_text_stream("stdin")
    try:
        items = list_pinned_items(config)
    except QueueStorageError as exc:
        _fail_queue(exc, action="read queue")
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
        except QueueStorageError as exc:
            _fail_queue(exc, action="update item")
        except (KeyError, RuntimeError, OSError, sqlite3.Error):
            _fail("error: could not update item")


@app.command("check-in")
def check_in(
    ctx: typer.Context,
    mood: Optional[str] = typer.Option(None, "--mood", help="Mood rating 1-5."),
    note: Optional[str] = typer.Option(None, "--note", help="Short reflection note."),
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
        entries = _read_today(_get_config(ctx))
    except OSError:
        _fail("error: could not read today")
    _echo_lines(_today_lines(entries))


def _home_lines(config: AppConfig) -> list[str]:
    entries = _read_today(config)
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


def _latest_entry(entries: list[JournalEntry]) -> Optional[JournalEntry]:
    return entries[-1] if entries else None


def _read_today(config: AppConfig) -> list[JournalEntry]:
    result = read_day(datetime.now().astimezone().date(), config)
    if result.issues:
        typer.echo(_journal_warning(result), err=True)
    return list(result.entries)


def _journal_warning(result: JournalReadResult) -> str:
    location = "journal/" + "/".join(result.path.parts[-3:])
    groups: list[str] = []
    for kind in ("malformed JSON", "invalid record", "invalid encoding"):
        lines = [str(issue.line_number) for issue in result.issues if issue.kind == kind]
        if lines:
            groups.append(f"{kind}: lines {', '.join(lines)}")
    detail = "; ".join(groups)
    count = len(result.issues)
    label = "record" if count == 1 else "records"
    return (
        f"warning: {location} contains {count} malformed {label} ({detail}); "
        "valid entries shown; original file preserved"
    )


def _fail_queue(exc: QueueStorageError, *, action: str) -> None:
    if isinstance(exc, QueueIncompatibleError):
        _fail(
            "error: queue database is incompatible; original data was preserved; "
            "move muse.db and its sidecars before retrying"
        )
    if isinstance(exc, QueueCorruptError):
        _fail(
            "error: queue database is corrupt; original data was preserved; "
            "back up or move muse.db and its sidecars before retrying"
        )
    if isinstance(exc, QueueLockedError):
        _fail(
            "error: queue database is locked; original data was preserved; "
            "close other muse processes and retry"
        )
    _fail(f"error: could not {action}; original queue data was preserved")


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


def _read_choice(valid: tuple[str, ...], prompt: str, *, stream: Optional[TextIO] = None) -> str:
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
    mood: Optional[str],
    note: Optional[str],
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
        raise AssertionError("unreachable") from None
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
    if message.startswith("Got unexpected extra argument") or message.startswith(
        "Got unexpected extra arguments"
    ):
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
