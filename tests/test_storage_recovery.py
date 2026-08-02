from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from typer.testing import CliRunner

from musecli import queue
from musecli.cli import app
from musecli.config import AppConfig
from musecli.journal import (
    JournalEntry,
    JournalReadError,
    append_entry,
    day_path,
    read_day,
    read_entries_for_day,
)
from musecli.queue import QueueLockedError, QueueUnavailableError, list_inbox_items


def _write_current_schema(path: Path) -> None:
    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            CREATE TABLE items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                text TEXT NOT NULL,
                status TEXT NOT NULL,
                pinned INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.commit()


def _journal_path(config: AppConfig) -> tuple[datetime, Path]:
    moment = datetime.now().astimezone().replace(microsecond=0)
    return moment, day_path(moment, config)


def test_corrupt_queue_is_preserved_without_replacement(tmp_path: Path) -> None:
    runner = CliRunner()
    original = b"PRIVATE corrupt sqlite data"
    (tmp_path / "muse.db").write_bytes(original)

    result = runner.invoke(app, ["--data-dir", str(tmp_path), "add", "new item"])

    assert result.exit_code == 1, result.output
    assert result.output == (
        "error: queue database is corrupt; original data was preserved; "
        "back up or move muse.db and its sidecars before retrying\n"
    )
    assert "PRIVATE" not in result.output
    assert (tmp_path / "muse.db").read_bytes() == original
    assert not list(tmp_path.glob("*.backup*"))


def test_queue_sidecars_are_preserved_when_validation_fails(tmp_path: Path) -> None:
    original = {
        "muse.db": b"PRIVATE corrupt sqlite data",
        "muse.db-wal": b"PRIVATE wal evidence",
        "muse.db-shm": b"PRIVATE shm evidence",
        "muse.db-journal": b"PRIVATE journal evidence",
    }
    for name, content in original.items():
        (tmp_path / name).write_bytes(content)

    result = CliRunner().invoke(app, ["--data-dir", str(tmp_path), "inbox"])

    assert result.exit_code == 1, result.output
    assert "original queue data was preserved" in result.output
    assert "PRIVATE" not in result.output
    for name, content in original.items():
        assert (tmp_path / name).read_bytes() == content


def test_ordinary_queue_access_failure_does_not_modify_original(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = AppConfig.defaults(base_dir=tmp_path)
    database = tmp_path / "muse.db"
    _write_current_schema(database)
    original = database.read_bytes()

    def fail(_path: Path) -> sqlite3.Connection:
        raise OSError("PRIVATE operating-system detail")

    monkeypatch.setattr(queue, "_connect_readonly", fail)

    with pytest.raises(QueueUnavailableError, match="queue storage is unavailable"):
        list_inbox_items(config)
    assert database.read_bytes() == original
    assert not list(tmp_path.glob("*.backup*"))


def test_locked_queue_is_classified_without_destructive_recovery(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = AppConfig.defaults(base_dir=tmp_path)
    database = tmp_path / "muse.db"
    _write_current_schema(database)
    original = database.read_bytes()

    def fail(_path: Path) -> sqlite3.Connection:
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(queue, "_connect_readonly", fail)

    with pytest.raises(QueueLockedError, match="queue database is locked"):
        list_inbox_items(config)
    assert database.read_bytes() == original


def test_custom_data_directory_queue_failure_is_safe_and_actionable(
    tmp_path: Path,
) -> None:
    database = tmp_path / "muse.db"
    database.write_bytes(b"PRIVATE corrupt sqlite data")

    result = CliRunner().invoke(app, ["--data-dir", str(tmp_path), "inbox"])

    assert result.exit_code == 1, result.output
    assert "original data was preserved" in result.output
    assert "PRIVATE" not in result.output
    assert "Traceback" not in result.output
    assert database.read_bytes() == b"PRIVATE corrupt sqlite data"


def test_invalid_queue_values_are_preserved_instead_of_normalised(tmp_path: Path) -> None:
    database = tmp_path / "muse.db"
    _write_current_schema(database)
    with sqlite3.connect(database) as conn:
        conn.execute(
            """
            INSERT INTO items (text, status, pinned, created_at, updated_at)
            VALUES ('preserve me', 'unknown', 1, '2026-08-02T10:00:00Z', '2026-08-02T10:00:00Z')
            """
        )
        conn.commit()
    original = database.read_bytes()

    result = CliRunner().invoke(app, ["--data-dir", str(tmp_path), "inbox"])

    assert result.exit_code == 1, result.output
    assert "queue database is incompatible" in result.output
    assert database.read_bytes() == original
    with sqlite3.connect(database) as conn:
        assert conn.execute("SELECT status, pinned FROM items").fetchone() == ("unknown", 1)


def test_journal_read_surfaces_issues_and_preserves_valid_records(tmp_path: Path) -> None:
    config = AppConfig.defaults(base_dir=tmp_path)
    moment, path = _journal_path(config)
    path.parent.mkdir(parents=True)
    valid_first = JournalEntry(moment, 3, "first valid").to_dict()
    valid_last = JournalEntry(moment + timedelta(hours=1), 4, "latest valid").to_dict()
    source = (
        json.dumps(valid_first)
        + "\n"
        + '{"PRIVATE malformed content"\n'
        + json.dumps(valid_last)
        + "\n"
        + json.dumps({"timestamp": "bad", "mood": 9, "note": "PRIVATE invalid"})
        + "\n"
    )
    path.write_text(source, encoding="utf-8")

    result = read_day(moment.date(), config)

    assert [entry.note for entry in result.entries] == ["first valid", "latest valid"]
    assert [(issue.line_number, issue.kind) for issue in result.issues] == [
        (2, "malformed JSON"),
        (4, "invalid record"),
    ]
    assert path.read_text(encoding="utf-8") == source

    with pytest.raises(JournalReadError) as raised:
        read_entries_for_day(moment.date(), config)
    assert raised.value.result == result


def test_today_shows_valid_journal_data_with_safe_degraded_warning(tmp_path: Path) -> None:
    config = AppConfig.defaults(base_dir=tmp_path)
    moment, path = _journal_path(config)
    append_entry(JournalEntry(moment, 4, "safe visible note"), config)
    with path.open("a", encoding="utf-8") as handle:
        handle.write('{"PRIVATE malformed content"\n')
    original = path.read_bytes()

    result = CliRunner().invoke(app, ["--data-dir", str(tmp_path), "today"])

    assert result.exit_code == 0, result.output
    assert "today\n\n  mood: 4\n  note: safe visible note\n" in result.output
    assert "contains 1 malformed record (malformed JSON: lines 2)" in result.output
    assert "valid entries shown; original file preserved" in result.output
    assert "PRIVATE" not in result.output
    assert "Traceback" not in result.output
    assert path.read_bytes() == original


def test_binary_journal_line_is_isolated_without_exposing_or_rewriting_it(tmp_path: Path) -> None:
    config = AppConfig.defaults(base_dir=tmp_path)
    moment, path = _journal_path(config)
    path.parent.mkdir(parents=True)
    valid = json.dumps(JournalEntry(moment, 3, "valid after binary").to_dict()).encode()
    source = b"\xff\xfePRIVATE binary\n" + valid + b"\n"
    path.write_bytes(source)

    result = CliRunner().invoke(app, ["--data-dir", str(tmp_path), "today"])

    assert result.exit_code == 0, result.output
    assert "note: valid after binary" in result.output
    assert "invalid encoding: lines 1" in result.output
    assert "PRIVATE" not in result.output
    assert path.read_bytes() == source


def test_check_in_appends_without_rewriting_existing_malformed_journal(tmp_path: Path) -> None:
    config = AppConfig.defaults(base_dir=tmp_path)
    _moment, path = _journal_path(config)
    path.parent.mkdir(parents=True)
    prefix = b'{"PRIVATE malformed content"\n'
    path.write_bytes(prefix)

    result = CliRunner().invoke(
        app,
        ["--data-dir", str(tmp_path), "check-in", "--mood", "5", "--note", "new valid"],
    )

    assert result.exit_code == 0, result.output
    assert result.output == "saved\n"
    assert path.read_bytes().startswith(prefix)
    assert len(path.read_text(encoding="utf-8").splitlines()) == 2
