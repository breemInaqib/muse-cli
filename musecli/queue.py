"""SQLite-backed queue storage for museCLI."""

from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .config import AppConfig
from .utils import ensure_private_dir, ensure_private_file, iso_utc, parse_timestamp, utc_now

_ALLOWED_STATUSES = {"inbox", "kept", "discarded"}
_EXPECTED_ITEMS_SCHEMA = [
    ("id", "INTEGER", 0, None, 1),
    ("text", "TEXT", 1, None, 0),
    ("status", "TEXT", 1, None, 0),
    ("pinned", "INTEGER", 1, "0", 0),
    ("created_at", "TEXT", 1, None, 0),
    ("updated_at", "TEXT", 1, None, 0),
]
_ITEM_SELECT = """
    SELECT
        id,
        created_at,
        updated_at,
        text,
        status,
        pinned
    FROM items
"""


@dataclass(frozen=True)
class InboxItem:
    """One queue item stored in SQLite."""

    id: int
    created_at: datetime
    updated_at: datetime
    text: str
    status: str
    pinned: bool


def db_path(config: AppConfig) -> Path:
    """Return the queue database path."""
    return config.data_dir / "muse.db"


def init_db(config: AppConfig) -> Path:
    """Create the queue database and schema if needed."""
    with _open_db(config):
        pass
    return db_path(config)


def add_item(
    config: AppConfig,
    *,
    text: str,
    now: datetime | None = None,
) -> InboxItem:
    """Insert one inbox item and return the stored row."""
    body = text.strip()
    if not body:
        raise ValueError("text cannot be empty")

    stamp = iso_utc(now or utc_now())
    with _open_db(config) as conn:
        cursor = conn.execute(
            """
            INSERT INTO items (text, status, pinned, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (body, "inbox", 0, stamp, stamp),
        )
        item = _get_item(conn, int(cursor.lastrowid))
        conn.commit()
    if item is None:
        raise RuntimeError("created item could not be read")
    return item


def list_inbox_items(config: AppConfig) -> list[InboxItem]:
    """Return inbox items newest first."""
    return _list_items(
        config,
        where="WHERE status = 'inbox'",
        order="ORDER BY created_at DESC, id DESC",
    )


def list_pinned_items(config: AppConfig) -> list[InboxItem]:
    """Return focus items newest first."""
    return _list_items(
        config,
        where="WHERE status = 'kept' AND pinned = 1",
        order="ORDER BY updated_at DESC, id DESC",
    )


def keep_item(
    config: AppConfig,
    *,
    item_id: int,
    pinned: bool = False,
    now: datetime | None = None,
) -> bool:
    """Mark one item as kept, optionally pinning it for focus."""
    with _open_db(config) as conn:
        _require_item(conn, item_id)
        cursor = conn.execute(
            """
            UPDATE items
            SET status = 'kept', pinned = ?, updated_at = ?
            WHERE id = ? AND (status <> 'kept' OR pinned <> ?)
            """,
            (1 if pinned else 0, iso_utc(now or utc_now()), item_id, 1 if pinned else 0),
        )
        conn.commit()
        return cursor.rowcount > 0


def discard_item(
    config: AppConfig,
    *,
    item_id: int,
    now: datetime | None = None,
) -> bool:
    """Mark one item as discarded and remove any pin."""
    with _open_db(config) as conn:
        _require_item(conn, item_id)
        cursor = conn.execute(
            """
            UPDATE items
            SET status = 'discarded', pinned = 0, updated_at = ?
            WHERE id = ? AND (status <> 'discarded' OR pinned <> 0)
            """,
            (iso_utc(now or utc_now()), item_id),
        )
        conn.commit()
        return cursor.rowcount > 0


def inbox_count(config: AppConfig) -> int:
    """Return the number of inbox items."""
    with _open_db(config) as conn:
        row = conn.execute("SELECT COUNT(*) AS total FROM items WHERE status = 'inbox'").fetchone()
    return int(row["total"]) if row else 0


def _list_items(
    config: AppConfig,
    *,
    where: str,
    order: str,
) -> list[InboxItem]:
    with _open_db(config) as conn:
        rows = conn.execute(f"{_ITEM_SELECT} {where} {order}").fetchall()
    return [
        InboxItem(
            id=int(row["id"]),
            created_at=parse_timestamp(row["created_at"]),
            updated_at=parse_timestamp(row["updated_at"]),
            text=str(row["text"]),
            status=_normalise_status(str(row["status"])),
            pinned=bool(row["pinned"]),
        )
        for row in rows
    ]


def _get_item(conn: sqlite3.Connection, item_id: int) -> InboxItem | None:
    row = conn.execute(f"{_ITEM_SELECT} WHERE id = ?", (item_id,)).fetchone()
    if row is None:
        return None
    return InboxItem(
        id=int(row["id"]),
        created_at=parse_timestamp(row["created_at"]),
        updated_at=parse_timestamp(row["updated_at"]),
        text=str(row["text"]),
        status=_normalise_status(str(row["status"])),
        pinned=bool(row["pinned"]),
    )


def _normalise_status(value: str) -> str:
    status = value.strip().lower()
    return status if status in _ALLOWED_STATUSES else "inbox"


def _open_db(config: AppConfig) -> sqlite3.Connection:
    ensure_private_dir(config.data_dir)
    path = db_path(config)
    if _needs_schema_reset(path):
        _reset_db(path)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    _init_schema(conn)
    ensure_private_file(path)
    return conn


def _init_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            text TEXT NOT NULL,
            status TEXT NOT NULL,
            pinned INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )

    conn.execute("UPDATE items SET status = 'inbox' WHERE status NOT IN ('inbox', 'kept', 'discarded')")
    conn.execute("UPDATE items SET pinned = 0 WHERE status <> 'kept'")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_items_status_created ON items(status, created_at DESC, id DESC)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_items_focus ON items(pinned, updated_at DESC, id DESC)")
    conn.commit()


def _needs_schema_reset(path: Path) -> bool:
    if not path.exists():
        return False
    try:
        with sqlite3.connect(path) as conn:
            conn.row_factory = sqlite3.Row
            tables = [
                str(row["name"])
                for row in conn.execute(
                    """
                    SELECT name
                    FROM sqlite_master
                    WHERE type = 'table' AND name NOT LIKE 'sqlite_%'
                    ORDER BY name ASC
                    """
                ).fetchall()
            ]
            if not tables:
                return False
            if tables != ["items"]:
                return True
            rows = conn.execute("PRAGMA table_info(items)").fetchall()
    except sqlite3.DatabaseError:
        return True

    actual = [
        (
            str(row["name"]),
            str(row["type"]).upper(),
            int(row["notnull"]),
            str(row["dflt_value"]) if row["dflt_value"] is not None else None,
            int(row["pk"]),
        )
        for row in rows
    ]
    return actual != _EXPECTED_ITEMS_SCHEMA


def _reset_db(path: Path) -> None:
    for target in (
        path,
        Path(f"{path}-wal"),
        Path(f"{path}-shm"),
        Path(f"{path}-journal"),
    ):
        try:
            os.remove(target)
        except FileNotFoundError:
            continue


def _require_item(conn: sqlite3.Connection, item_id: int) -> None:
    row = conn.execute("SELECT id FROM items WHERE id = ?", (item_id,)).fetchone()
    if row is None:
        raise KeyError(item_id)
