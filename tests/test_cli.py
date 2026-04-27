from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from typer.testing import CliRunner

from musecli.cli import app


def _journal_path(base: Path) -> Path:
    today = datetime.now().astimezone().date()
    return (
        base
        / "journal"
        / f"{today.year:04d}"
        / f"{today.month:02d}"
        / f"{today.isoformat()}.jsonl"
    )


def test_check_in_and_today_flow(tmp_path: Path) -> None:
    runner = CliRunner()

    result = runner.invoke(
        app,
        [
            "--data-dir",
            str(tmp_path),
            "check-in",
            "--mood",
            "4",
            "--note",
            "steady",
        ],
    )
    assert result.exit_code == 0, result.output
    assert result.output == "saved\n"

    entry_path = _journal_path(tmp_path)
    assert entry_path.exists()
    lines = entry_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    payload = json.loads(lines[0])
    assert payload["mood"] == 4
    assert payload["note"] == "steady"

    today = runner.invoke(app, ["--data-dir", str(tmp_path), "today"])
    assert today.exit_code == 0, today.output
    assert today.output == "today\n\n  mood: 4\n  note: steady\n"


def test_today_shows_empty_state_when_no_check_in(tmp_path: Path) -> None:
    runner = CliRunner()

    today = runner.invoke(app, ["--data-dir", str(tmp_path), "today"])

    assert today.exit_code == 0, today.output
    assert today.output == "today\n\n  no check-in\n"


def test_check_in_flag_input_still_works(tmp_path: Path) -> None:
    runner = CliRunner()

    result = runner.invoke(
        app,
        [
            "--data-dir",
            str(tmp_path),
            "check-in",
            "--mood",
            "4",
            "--note",
            "steady",
        ],
    )

    assert result.exit_code == 0, result.output
    assert result.output == "saved\n"


def test_check_in_requires_flags_only(tmp_path: Path) -> None:
    runner = CliRunner()

    missing_both = runner.invoke(
        app,
        ["--data-dir", str(tmp_path), "check-in"],
    )
    assert missing_both.exit_code == 1
    assert missing_both.output == "error: provide --mood\n"

    positional = runner.invoke(
        app,
        ["--data-dir", str(tmp_path), "check-in", "4", "steady"],
    )
    assert positional.exit_code == 2
    assert positional.output == "error: unexpected argument\n"


def test_check_in_requires_explicit_inputs(tmp_path: Path) -> None:
    runner = CliRunner()

    missing_note = runner.invoke(
        app,
        ["--data-dir", str(tmp_path), "check-in", "--mood", "4"],
    )
    assert missing_note.exit_code == 1
    assert missing_note.output == "error: provide --note\n"

    missing_mood = runner.invoke(
        app,
        ["--data-dir", str(tmp_path), "check-in", "--note", "steady"],
    )
    assert missing_mood.exit_code == 1
    assert missing_mood.output == "error: provide --mood\n"

    blank_note = runner.invoke(
        app,
        ["--data-dir", str(tmp_path), "check-in", "--mood", "4", "--note", "   "],
    )
    assert blank_note.exit_code == 1
    assert blank_note.output == "error: provide --note\n"

    missing_value = runner.invoke(
        app,
        ["--data-dir", str(tmp_path), "check-in", "--mood"],
    )
    assert missing_value.exit_code == 2
    assert missing_value.output == "error: provide --mood\n"

    missing_note_value = runner.invoke(
        app,
        ["--data-dir", str(tmp_path), "check-in", "--mood", "4", "--note"],
    )
    assert missing_note_value.exit_code == 2
    assert missing_note_value.output == "error: provide --note\n"

    invalid_mood = runner.invoke(
        app,
        ["--data-dir", str(tmp_path), "check-in", "--mood", "6", "--note", "steady"],
    )
    assert invalid_mood.exit_code == 1
    assert invalid_mood.output == "error: mood must be 1–5\n"

    invalid_mood_text = runner.invoke(
        app,
        ["--data-dir", str(tmp_path), "check-in", "--mood", "bad", "--note", "steady"],
    )
    assert invalid_mood_text.exit_code == 1
    assert invalid_mood_text.output == "error: mood must be 1–5\n"


def test_today_rejects_unknown_option(tmp_path: Path) -> None:
    runner = CliRunner()

    result = runner.invoke(app, ["--data-dir", str(tmp_path), "today", "--date", "2026-04-18"])

    assert result.exit_code == 2
    assert result.output == "error: unexpected option --date\n"
