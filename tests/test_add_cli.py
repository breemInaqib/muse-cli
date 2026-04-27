from __future__ import annotations

import io
import sqlite3
from types import SimpleNamespace

from typer.testing import CliRunner

from musecli.cli import _read_choice, app
from musecli.config import AppConfig
from musecli.queue import add_item, keep_item, list_inbox_items, list_pinned_items
from musecli.utils import ClipboardUnavailableError, truncate


def test_add_uses_text_argument_and_stores_item(tmp_path) -> None:
    runner = CliRunner()

    added = runner.invoke(app, ["--data-dir", str(tmp_path), "add", "hello"])

    assert added.exit_code == 0, added.output
    assert added.output == "added\n"

    inbox = runner.invoke(app, ["--data-dir", str(tmp_path), "inbox"], input="q")
    assert inbox.exit_code == 0, inbox.output
    assert inbox.output == (
        "inbox\n\n"
        "  hello\n\n"
        "  [k] keep   [d] discard   [p] pin   [q] quit\n"
    )


def test_inbox_shows_empty_state_when_nothing_to_process(tmp_path) -> None:
    runner = CliRunner()

    inbox = runner.invoke(app, ["--data-dir", str(tmp_path), "inbox"])

    assert inbox.exit_code == 0, inbox.output
    assert inbox.output == "inbox\n\n  empty\n"


def test_inbox_loops_through_items_until_quit(tmp_path) -> None:
    runner = CliRunner()
    config = AppConfig.defaults(base_dir=tmp_path)
    add_item(config, text="first")
    add_item(config, text="second")

    inbox = runner.invoke(app, ["--data-dir", str(tmp_path), "inbox"], input="kq")

    assert inbox.exit_code == 0, inbox.output
    assert inbox.output == (
        "inbox\n\n"
        "  second\n\n"
        "  [k] keep   [d] discard   [p] pin   [q] quit\n\n"
        "  first\n\n"
        "  [k] keep   [d] discard   [p] pin   [q] quit\n"
    )
    assert [item.text for item in list_inbox_items(config)] == ["first"]
    assert [item.text for item in list_pinned_items(config)] == []


def test_focus_shows_empty_state_when_nothing_is_pinned(tmp_path) -> None:
    runner = CliRunner()

    focus = runner.invoke(app, ["--data-dir", str(tmp_path), "focus"])

    assert focus.exit_code == 0, focus.output
    assert focus.output == "focus\n\n  empty\n"


def test_focus_quit_leaves_remaining_items_pinned(tmp_path) -> None:
    runner = CliRunner()
    config = AppConfig.defaults(base_dir=tmp_path)
    first = add_item(config, text="first")
    second = add_item(config, text="second")
    third = add_item(config, text="third")
    keep_item(config, item_id=first.id, pinned=True)
    keep_item(config, item_id=second.id, pinned=True)
    keep_item(config, item_id=third.id, pinned=True)

    focus = runner.invoke(app, ["--data-dir", str(tmp_path), "focus"], input="dq")

    assert focus.exit_code == 0, focus.output
    assert focus.output == (
        "focus\n\n"
        "  third\n\n"
        "  [d] done   [q] quit\n\n"
        "  second\n\n"
        "  [d] done   [q] quit\n"
    )
    assert [item.text for item in list_pinned_items(config)] == ["second", "first"]
    with sqlite3.connect(tmp_path / "muse.db") as conn:
        row = conn.execute(
            "SELECT status, pinned FROM items WHERE text = ?",
            ("third",),
        ).fetchone()
    assert row == ("discarded", 0)


def test_focus_rejects_invalid_choice(tmp_path) -> None:
    runner = CliRunner()
    config = AppConfig.defaults(base_dir=tmp_path)
    item = add_item(config, text="still focused")
    keep_item(config, item_id=item.id, pinned=True)

    focus = runner.invoke(app, ["--data-dir", str(tmp_path), "focus"], input="rq")

    assert focus.exit_code == 0, focus.output
    assert focus.output == (
        "focus\n\n"
        "  still focused\n\n"
        "  [d] done   [q] quit\n"
        "  error: choose d or q\n"
        "  [d] done   [q] quit\n"
    )
    assert [item.text for item in list_pinned_items(config)] == ["still focused"]


def test_focus_done_discards_pinned_item(tmp_path) -> None:
    runner = CliRunner()
    config = AppConfig.defaults(base_dir=tmp_path)
    item = add_item(config, text="finish this")
    keep_item(config, item_id=item.id, pinned=True)

    focus = runner.invoke(app, ["--data-dir", str(tmp_path), "focus"], input="d")

    assert focus.exit_code == 0, focus.output
    assert focus.output == (
        "focus\n\n"
        "  finish this\n\n"
        "  [d] done   [q] quit\n"
    )
    assert list_pinned_items(config) == []
    with sqlite3.connect(tmp_path / "muse.db") as conn:
        row = conn.execute(
            "SELECT status, pinned FROM items WHERE text = ?",
            ("finish this",),
        ).fetchone()
    assert row == ("discarded", 0)


def test_add_reads_stdin_only_when_flag_is_set(tmp_path) -> None:
    runner = CliRunner()

    added = runner.invoke(
        app,
        ["--data-dir", str(tmp_path), "add", "--stdin"],
        input="hello\n",
    )

    assert added.exit_code == 0, added.output
    assert added.output == "added\n"


def test_add_reads_clipboard_when_flag_is_set(tmp_path, monkeypatch) -> None:
    runner = CliRunner()
    monkeypatch.setattr("musecli.cli.read_clipboard_text", lambda: "hello")

    added = runner.invoke(app, ["--data-dir", str(tmp_path), "add", "--clipboard"])

    assert added.exit_code == 0, added.output
    assert added.output == "added\n"


def test_add_clipboard_failure_is_short_and_deterministic(tmp_path, monkeypatch) -> None:
    runner = CliRunner()

    def fail() -> str:
        raise ClipboardUnavailableError("No supported clipboard command found.")

    monkeypatch.setattr("musecli.cli.read_clipboard_text", fail)

    result = runner.invoke(app, ["--data-dir", str(tmp_path), "add", "--clipboard"])

    assert result.exit_code == 1, result.output
    assert result.output == "error: clipboard unavailable\n"


def test_add_requires_one_explicit_input_source(tmp_path) -> None:
    runner = CliRunner()

    missing = runner.invoke(app, ["--data-dir", str(tmp_path), "add"])
    assert missing.exit_code == 1, missing.output
    assert missing.output == "error: provide text, --stdin, or --clipboard\n"

    conflict = runner.invoke(
        app,
        ["--data-dir", str(tmp_path), "add", "a", "--stdin"],
        input="b\n",
    )
    assert conflict.exit_code == 1, conflict.output
    assert conflict.output == "error: provide only one of text, --stdin, or --clipboard\n"

    unknown = runner.invoke(app, ["--data-dir", str(tmp_path), "add", "--bogus"])
    assert unknown.exit_code == 2, unknown.output
    assert unknown.output == "error: unexpected option --bogus\n"


def test_long_text_is_truncated_consistently_in_views(tmp_path) -> None:
    runner = CliRunner()
    text = "x" * 70
    shown = ("x" * 57) + "..."

    added = runner.invoke(app, ["--data-dir", str(tmp_path), "add", text])
    assert added.exit_code == 0, added.output

    inbox = runner.invoke(app, ["--data-dir", str(tmp_path), "inbox"], input="p")
    assert inbox.exit_code == 0, inbox.output
    assert inbox.output == (
        "inbox\n\n"
        f"  {shown}\n\n"
        "  [k] keep   [d] discard   [p] pin   [q] quit\n"
    )

    focus = runner.invoke(app, ["--data-dir", str(tmp_path), "focus"], input="q")
    assert focus.exit_code == 0, focus.output
    assert focus.output == (
        "focus\n\n"
        f"  {shown}\n\n"
        "  [d] done   [q] quit\n"
    )


def test_truncation_prefers_word_boundaries() -> None:
    assert truncate("one two three four five", 14) == "one two..."
    assert truncate("alpha beta_gamma_delta", 18) == "alpha beta_gamm..."


def test_read_choice_treats_keyboard_interrupt_as_quit(monkeypatch) -> None:
    monkeypatch.setattr("musecli.cli.typer.get_text_stream", lambda _name: object())
    monkeypatch.setattr("musecli.cli.sys", SimpleNamespace(stdin=SimpleNamespace(isatty=lambda: True)))

    def raise_interrupt() -> str:
        raise KeyboardInterrupt

    monkeypatch.setattr("musecli.cli.click.getchar", raise_interrupt)

    assert _read_choice(("q",), "prompt") == "q"


def test_read_choice_reuses_non_tty_stream_across_calls(monkeypatch) -> None:
    stream = io.StringIO("pq")
    monkeypatch.setattr("musecli.cli.sys", SimpleNamespace(stdin=SimpleNamespace(isatty=lambda: False)))

    assert _read_choice(("p", "q"), "prompt", stream=stream) == "p"
    assert _read_choice(("p", "q"), "prompt", stream=stream) == "q"


def test_invalid_choice_reprints_prompt_at_same_indent(tmp_path) -> None:
    runner = CliRunner()
    config = AppConfig.defaults(base_dir=tmp_path)
    add_item(config, text="hello")

    inbox = runner.invoke(app, ["--data-dir", str(tmp_path), "inbox"], input="xq")

    assert inbox.exit_code == 0, inbox.output
    assert inbox.output == (
        "inbox\n\n"
        "  hello\n\n"
        "  [k] keep   [d] discard   [p] pin   [q] quit\n"
        "  error: choose k, d, p, or q\n"
        "  [k] keep   [d] discard   [p] pin   [q] quit\n"
    )


def test_add_resets_incompatible_database_schema(tmp_path) -> None:
    runner = CliRunner()
    db_path = tmp_path / "muse.db"

    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                text TEXT NOT NULL,
                lane TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute("CREATE TABLE pins (item_id INTEGER PRIMARY KEY)")
        conn.execute(
            """
            INSERT INTO items (text, lane, status, created_at, updated_at)
            VALUES ('old row', 'gather', 'inbox', '2026-04-22T10:00:00Z', '2026-04-22T10:00:00Z')
            """
        )
        conn.commit()

    added = runner.invoke(app, ["--data-dir", str(tmp_path), "add", "hello"])

    assert added.exit_code == 0, added.output
    assert added.output == "added\n"

    with sqlite3.connect(db_path) as conn:
        tables = [
            row[0]
            for row in conn.execute(
                """
                SELECT name
                FROM sqlite_master
                WHERE type = 'table' AND name NOT LIKE 'sqlite_%'
                ORDER BY name ASC
                """
            ).fetchall()
        ]
        assert tables == ["items"]
        columns = [
            (row[1], row[2].upper(), row[3], row[4], row[5])
            for row in conn.execute("PRAGMA table_info(items)").fetchall()
        ]
        assert columns == [
            ("id", "INTEGER", 0, None, 1),
            ("text", "TEXT", 1, None, 0),
            ("status", "TEXT", 1, None, 0),
            ("pinned", "INTEGER", 1, "0", 0),
            ("created_at", "TEXT", 1, None, 0),
            ("updated_at", "TEXT", 1, None, 0),
        ]
        rows = conn.execute("SELECT text, status, pinned FROM items").fetchall()
        assert rows == [("hello", "inbox", 0)]
