from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

from typer.testing import CliRunner

from musecli.cli import app
from musecli.config import AppConfig
from musecli.journal import JournalEntry, append_entry
from musecli.queue import add_item, keep_item


def test_top_level_help_keeps_only_locked_commands() -> None:
    runner = CliRunner()

    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0, result.output
    assert "Usage: muse [OPTIONS] COMMAND [ARGS]..." in result.output
    for command in [
        "add",
        "inbox",
        "focus",
        "check-in",
        "today",
    ]:
        assert command in result.output
    assert "Manage and complete focus items." in result.output
    listed_commands = re.findall(r"^\s{2}([a-z][a-z-]*)\s{2,}", result.output, re.MULTILINE)
    assert listed_commands == ["add", "inbox", "focus", "check-in", "today"]
    assert "╭" not in result.output
    assert "│" not in result.output
    assert "╰" not in result.output
    assert "Flow:" in result.output
    assert "  add -> inbox -> focus -> check-in -> today" in result.output
    assert "Run `muse` with no arguments for a focus snapshot." in result.output
    assert "shell" not in result.output.lower()


def test_subcommand_help_does_not_require_storage_and_shows_only_long_flags(monkeypatch) -> None:
    runner = CliRunner()

    def fail(_config) -> None:
        raise AssertionError("storage should not be initialized for help")

    monkeypatch.setattr("musecli.cli.init_db", fail)

    result = runner.invoke(app, ["check-in", "--help"])

    assert result.exit_code == 0, result.output
    assert "Usage: muse check-in [OPTIONS]" in result.output
    assert "--mood" in result.output
    assert "--note" in result.output
    assert "╭" not in result.output
    assert "│" not in result.output
    assert "╰" not in result.output
    assert "[MOOD_ARG]" not in result.output
    assert "[NOTE_ARG]" not in result.output
    assert " -m," not in result.output
    assert " -n," not in result.output


def test_no_args_prints_empty_home_view_and_exits(tmp_path: Path) -> None:
    runner = CliRunner()

    result = runner.invoke(app, ["--data-dir", str(tmp_path)])

    assert result.exit_code == 0, result.output
    assert result.output.splitlines() == [
        "museCLI",
        "",
        "  inbox: 0",
        "",
        "focus",
        "  empty",
        "",
        "today",
        "  no check-in",
    ]
    assert len(result.output.splitlines()) <= 12
    assert (tmp_path / "config.json").exists()


def test_no_args_home_view_summarises_focus_state(tmp_path: Path) -> None:
    runner = CliRunner()
    config = AppConfig.defaults(base_dir=tmp_path)
    first = add_item(config, text="first pinned task", now=datetime(2026, 4, 20, 8, 0, tzinfo=timezone.utc))
    second = add_item(config, text="second pinned task", now=datetime(2026, 4, 20, 8, 1, tzinfo=timezone.utc))
    third = add_item(config, text="third pinned task", now=datetime(2026, 4, 20, 8, 2, tzinfo=timezone.utc))
    fourth = add_item(config, text="fourth pinned task", now=datetime(2026, 4, 20, 8, 3, tzinfo=timezone.utc))
    keep_item(config, item_id=first.id, pinned=True, now=datetime(2026, 4, 20, 9, 0, tzinfo=timezone.utc))
    keep_item(config, item_id=second.id, pinned=True, now=datetime(2026, 4, 20, 9, 1, tzinfo=timezone.utc))
    keep_item(config, item_id=third.id, pinned=True, now=datetime(2026, 4, 20, 9, 2, tzinfo=timezone.utc))
    keep_item(config, item_id=fourth.id, pinned=True, now=datetime(2026, 4, 20, 9, 3, tzinfo=timezone.utc))
    append_entry(
        JournalEntry(
            timestamp=datetime.now().astimezone().replace(microsecond=0),
            mood=4,
            note="steady",
        ),
        config,
    )

    result = runner.invoke(app, ["--data-dir", str(tmp_path)])

    assert result.exit_code == 0, result.output
    assert result.output.splitlines() == [
        "museCLI",
        "",
        "  inbox: 0",
        "",
        "focus",
        "  - fourth pinned task",
        "  - third pinned task",
        "  - second pinned task",
        "",
        "today",
        "  mood: 4",
        "  note: steady",
    ]
    assert len(result.output.splitlines()) <= 12
