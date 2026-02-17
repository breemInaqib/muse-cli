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


def test_check_in_and_today_flow(tmp_path) -> None:
    runner = CliRunner()

    result = runner.invoke(
        app,
        [
            "--data-dir",
            str(tmp_path),
            "check-in",
            "--mood",
            "4",
            "--tags",
            "calm",
            "--note",
            "test note",
            "--long-note",
            "",
            "--skip-editor",
        ],
    )
    assert result.exit_code == 0, result.stdout

    entry_path = _journal_path(tmp_path)
    assert entry_path.exists()
    lines = entry_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    payload = json.loads(lines[0])
    assert payload["mood"] == 4

    today = runner.invoke(app, ["--data-dir", str(tmp_path), "today"])
    assert today.exit_code == 0
    assert "calm" in today.stdout
    assert "test note" in today.stdout


def test_stats_empty_week(tmp_path) -> None:
    runner = CliRunner()

    result = runner.invoke(app, ["--data-dir", str(tmp_path), "stats"])

    assert result.exit_code == 0
    assert "Entries: 0" in result.stdout
    assert "Sparkline: " in result.stdout


def test_export_writes_csv_headers(tmp_path) -> None:
    runner = CliRunner()

    check_in = runner.invoke(
        app,
        [
            "--data-dir",
            str(tmp_path),
            "check-in",
            "--mood",
            "3",
            "--tags",
            "focus",
            "--note",
            "export test",
            "--long-note",
            "",
            "--skip-editor",
        ],
    )
    assert check_in.exit_code == 0, check_in.stdout

    output_path = tmp_path / "out.csv"
    result = runner.invoke(
        app,
        [
            "--data-dir",
            str(tmp_path),
            "export",
            "--format",
            "csv",
            "--output",
            str(output_path),
            "--days",
            "1",
        ],
    )

    assert result.exit_code == 0, result.stdout
    assert output_path.exists()
    lines = output_path.read_text(encoding="utf-8").splitlines()
    assert lines[0] == "timestamp,mood,tags,note,long_note"


def test_settings_update_persists(tmp_path) -> None:
    runner = CliRunner()

    result = runner.invoke(
        app,
        [
            "--data-dir",
            str(tmp_path),
            "settings",
            "--key",
            "date_format",
            "--value",
            "%d/%m/%Y",
        ],
    )

    assert result.exit_code == 0, result.stdout

    config_path = tmp_path / "config.json"
    assert config_path.exists()
    data = json.loads(config_path.read_text(encoding="utf-8"))
    assert data["date_format"] == "%d/%m/%Y"



def test_today_respects_date_format(tmp_path) -> None:
    runner = CliRunner()
    pattern = "%d/%m/%Y"

    settings_result = runner.invoke(
        app,
        [
            "--data-dir",
            str(tmp_path),
            "settings",
            "--key",
            "date_format",
            "--value",
            pattern,
        ],
    )
    assert settings_result.exit_code == 0, settings_result.stdout

    outcome = runner.invoke(app, ["--data-dir", str(tmp_path), "today"])
    assert outcome.exit_code == 0
    expected_label = datetime.now().astimezone().date().strftime(pattern)
    assert expected_label in outcome.stdout



def test_export_empty_window_creates_header(tmp_path) -> None:
    runner = CliRunner()
    output_path = tmp_path / "empty.csv"

    result = runner.invoke(
        app,
        [
            "--data-dir",
            str(tmp_path),
            "export",
            "--format",
            "csv",
            "--output",
            str(output_path),
            "--days",
            "1",
        ],
    )

    assert result.exit_code == 0, result.stdout
    assert output_path.exists()
    lines = output_path.read_text(encoding="utf-8").splitlines()
    assert lines[0] == "timestamp,mood,tags,note,long_note"
    assert len(lines) == 1



def test_timeline_lists_entries(tmp_path) -> None:
    runner = CliRunner()
    check_in = runner.invoke(
        app,
        [
            "--data-dir",
            str(tmp_path),
            "check-in",
            "--mood",
            "3",
            "--tags",
            "focus",
            "--note",
            "timeline test",
            "--long-note",
            "",
            "--skip-editor",
        ],
    )
    assert check_in.exit_code == 0, check_in.stdout

    result = runner.invoke(app, ["--data-dir", str(tmp_path), "timeline", "--days", "7"])

    assert result.exit_code == 0, result.stdout
    assert "timeline ready." in result.stdout
    assert "focus" in result.stdout
    assert "timeline test" in result.stdout



def test_timeline_no_entries_message(tmp_path) -> None:
    runner = CliRunner()

    result = runner.invoke(app, ["--data-dir", str(tmp_path), "timeline"])

    assert result.exit_code == 0, result.stdout
    assert "no entries in the last 7 days" in result.stdout



def test_timeline_tag_filter(tmp_path) -> None:
    runner = CliRunner()

    runner.invoke(
        app,
        [
            "--data-dir",
            str(tmp_path),
            "check-in",
            "--mood",
            "4",
            "--tags",
            "focus,calm",
            "--note",
            "should appear",
            "--long-note",
            "",
            "--skip-editor",
        ],
    )
    runner.invoke(
        app,
        [
            "--data-dir",
            str(tmp_path),
            "check-in",
            "--mood",
            "2",
            "--tags",
            "rest",
            "--note",
            "filtered out",
            "--long-note",
            "",
            "--skip-editor",
        ],
    )

    result = runner.invoke(
        app,
        [
            "--data-dir",
            str(tmp_path),
            "timeline",
            "--tag",
            "focus",
        ],
    )

    assert result.exit_code == 0, result.stdout
    assert "should appear" in result.stdout
    assert "filtered out" not in result.stdout

    empty_result = runner.invoke(
        app,
        [
            "--data-dir",
            str(tmp_path),
            "timeline",
            "--tag",
            "missing",
        ],
    )

    assert empty_result.exit_code == 0, empty_result.stdout
    assert "no entries in the last 7 days" in empty_result.stdout
