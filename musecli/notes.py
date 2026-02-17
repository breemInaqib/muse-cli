from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import secrets
import sqlite3
import tarfile
from dataclasses import dataclass
from datetime import date, datetime, time, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from .model import AppConfig

_ENTRY_KEYS = (
    "id",
    "created_at",
    "updated_at",
    "kind",
    "text",
    "url",
    "title",
    "project",
    "source",
    "tags",
    "archived",
)
_ALLOWED_KINDS = {"note", "thought", "snippet", "link"}
_CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


@dataclass(frozen=True)
class NoteEntry:
    """Represent a canonical muse entry used by v0 commands."""

    id: str
    created_at: datetime
    updated_at: datetime
    kind: str
    text: str
    url: str | None
    title: str | None
    project: str | None
    source: str
    tags: tuple[str, ...]
    archived: bool = False

    def __post_init__(self) -> None:
        created = _to_utc(self.created_at)
        updated = _to_utc(self.updated_at)
        normalised_kind = self.kind.strip().lower()
        if normalised_kind not in _ALLOWED_KINDS:
            raise ValueError("kind must be one of: note, thought, snippet, link")
        if normalised_kind == "thought":
            normalised_kind = "note"
        source = self.source.strip().lower()
        if not source:
            source = "cli"
        cleaned_tags = tuple(sorted({tag.strip().lower() for tag in self.tags if tag.strip()}))
        object.__setattr__(self, "created_at", created)
        object.__setattr__(self, "updated_at", updated)
        object.__setattr__(self, "kind", normalised_kind)
        object.__setattr__(self, "text", self.text.strip())
        object.__setattr__(self, "url", self.url.strip() if self.url else None)
        object.__setattr__(self, "title", self.title.strip() if self.title else None)
        object.__setattr__(self, "project", self.project.strip() if self.project else None)
        object.__setattr__(self, "source", source)
        object.__setattr__(self, "tags", cleaned_tags)

    def to_dict(self) -> dict[str, Any]:
        """Serialise in canonical key order for deterministic scripting output."""
        return {
            "id": self.id,
            "created_at": _iso_utc(self.created_at),
            "updated_at": _iso_utc(self.updated_at),
            "kind": self.kind,
            "text": self.text,
            "url": self.url,
            "title": self.title,
            "project": self.project,
            "source": self.source,
            "tags": list(self.tags),
            "archived": self.archived,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> NoteEntry:
        """Create an entry from persisted JSON data."""
        tags_raw = data.get("tags") or []
        tags: list[str] = []
        if isinstance(tags_raw, Iterable) and not isinstance(tags_raw, (str, bytes)):
            tags = [str(item) for item in tags_raw]

        return cls(
            id=str(data.get("id", "")).strip(),
            created_at=_parse_timestamp(data.get("created_at")),
            updated_at=_parse_timestamp(data.get("updated_at")),
            kind=str(data.get("kind", "thought")),
            text=str(data.get("text", "")),
            url=_optional_text(data.get("url")),
            title=_optional_text(data.get("title")),
            project=_optional_text(data.get("project")),
            source=str(data.get("source", "cli")),
            tags=tuple(tags),
            archived=bool(data.get("archived", False)),
        )


def entries_root(config: AppConfig) -> Path:
    """Return the source-of-truth JSONL directory."""
    return config.data_dir / "entries"


def index_path(config: AppConfig) -> Path:
    """Return the sqlite index path."""
    return config.data_dir / "index.sqlite"


def backups_root(config: AppConfig) -> Path:
    """Return the backup folder."""
    return config.data_dir / "backups"


def make_entry(
    *,
    text: str,
    kind: str,
    tags: Sequence[str],
    url: str | None = None,
    title: str | None = None,
    project: str | None = None,
    source: str = "cli",
    now: datetime | None = None,
) -> NoteEntry:
    """Create a new entry with a ULID-like identifier."""
    current = _to_utc(now or datetime.now(timezone.utc)).replace(microsecond=0)
    return NoteEntry(
        id=generate_entry_id(current),
        created_at=current,
        updated_at=current,
        kind=kind,
        text=text,
        url=url,
        title=title,
        project=project,
        source=source,
        tags=tuple(tags),
        archived=False,
    )


def append_snapshot(entry: NoteEntry, config: AppConfig) -> Path:
    """Append a full entry snapshot to the day shard."""
    shard_path = _entry_shard_path(entry.updated_at, config)
    _ensure_private_dir(shard_path.parent)
    payload = json.dumps(entry.to_dict(), ensure_ascii=False, separators=(",", ":"))
    with shard_path.open("a", encoding="utf-8") as handle:
        handle.write(payload + "\n")
    _set_private_file(shard_path)
    return shard_path


def rebuild_index(config: AppConfig) -> tuple[int, int]:
    """Rebuild sqlite index from append-only JSONL source files."""
    with _open_index(config) as conn:
        conn.execute("DELETE FROM entry_tags")
        conn.execute("DELETE FROM entry_fts")
        conn.execute("DELETE FROM entries")
        snapshots = 0
        for payload in iter_snapshots(config):
            entry = NoteEntry.from_dict(payload)
            _upsert_entry(conn, entry)
            snapshots += 1
        conn.commit()
        current = conn.execute("SELECT COUNT(*) FROM entries").fetchone()[0]
        return snapshots, int(current)


def index_entry(entry: NoteEntry, config: AppConfig) -> None:
    """Upsert one entry into sqlite index."""
    with _open_index(config) as conn:
        _upsert_entry(conn, entry)
        conn.commit()


def get_entry(entry_id: str, config: AppConfig) -> NoteEntry | None:
    """Load one entry by id from index."""
    with _open_index(config) as conn:
        row = conn.execute(
            """
            SELECT id, created_at, updated_at, kind, text, url, title, project, source, tags_json, archived
            FROM entries
            WHERE id = ?
            """,
            (entry_id,),
        ).fetchone()
    if row is None:
        return None
    return _row_to_entry(row)


def query_entries(
    config: AppConfig,
    *,
    query: str | None = None,
    tags: Sequence[str] = (),
    kind: str | None = None,
    project: str | None = None,
    source: str | None = None,
    since: str | None = None,
    until: str | None = None,
    include_archived: bool = False,
    sort: str = "created_at",
    order: str = "asc",
    limit: int | None = 50,
) -> list[NoteEntry]:
    """Query entries with deterministic ordering and optional FTS filtering."""
    sort_key = sort.strip().lower()
    if sort_key not in {"created_at", "updated_at", "id"}:
        raise ValueError("sort must be one of: created_at, updated_at, id")
    direction = order.strip().lower()
    if direction not in {"asc", "desc"}:
        raise ValueError("order must be one of: asc, desc")

    where: list[str] = []
    params: list[Any] = []

    if not include_archived:
        where.append("e.archived = 0")
    if kind:
        where.append("e.kind = ?")
        params.append(kind.strip().lower())
    if project:
        where.append("e.project = ?")
        params.append(project.strip())
    if source:
        where.append("e.source = ?")
        params.append(source.strip().lower())
    if since:
        where.append("e.created_at >= ?")
        params.append(parse_temporal_filter(since, is_end=False))
    if until:
        where.append("e.created_at <= ?")
        params.append(parse_temporal_filter(until, is_end=True))
    for token in tags:
        clean = token.strip().lower()
        if not clean:
            continue
        where.append(
            "EXISTS (SELECT 1 FROM entry_tags t WHERE t.entry_id = e.id AND t.tag = ?)"
        )
        params.append(clean)
    if query:
        where.append("e.id IN (SELECT id FROM entry_fts WHERE entry_fts MATCH ?)")
        params.append(query)

    predicate = ""
    if where:
        predicate = "WHERE " + " AND ".join(where)

    sql = (
        "SELECT e.id, e.created_at, e.updated_at, e.kind, e.text, e.url, e.title, e.project, e.source, e.tags_json, e.archived "
        "FROM entries e "
        f"{predicate} "
        f"ORDER BY e.{sort_key} {direction.upper()}, e.id {direction.upper()}"
    )

    if limit is not None:
        sql += " LIMIT ?"
        params.append(max(0, int(limit)))

    with _open_index(config) as conn:
        rows = conn.execute(sql, tuple(params)).fetchall()
    return [_row_to_entry(row) for row in rows]


def update_tags(config: AppConfig, *, entry_id: str, add: Sequence[str], remove: Sequence[str]) -> NoteEntry:
    """Apply add/remove tag changes and persist as a new snapshot."""
    existing = get_entry(entry_id, config)
    if existing is None:
        raise KeyError(entry_id)
    updated_tags = set(existing.tags)
    for token in add:
        clean = token.strip().lower()
        if clean:
            updated_tags.add(clean)
    for token in remove:
        clean = token.strip().lower()
        if clean:
            updated_tags.discard(clean)

    updated = NoteEntry(
        id=existing.id,
        created_at=existing.created_at,
        updated_at=datetime.now(timezone.utc).replace(microsecond=0),
        kind=existing.kind,
        text=existing.text,
        url=existing.url,
        title=existing.title,
        project=existing.project,
        source=existing.source,
        tags=tuple(sorted(updated_tags)),
        archived=existing.archived,
    )
    append_snapshot(updated, config)
    index_entry(updated, config)
    return updated


def set_archived(config: AppConfig, *, entry_id: str, archived: bool) -> NoteEntry:
    """Archive or unarchive an entry and persist as a new snapshot."""
    existing = get_entry(entry_id, config)
    if existing is None:
        raise KeyError(entry_id)
    updated = NoteEntry(
        id=existing.id,
        created_at=existing.created_at,
        updated_at=datetime.now(timezone.utc).replace(microsecond=0),
        kind=existing.kind,
        text=existing.text,
        url=existing.url,
        title=existing.title,
        project=existing.project,
        source=existing.source,
        tags=existing.tags,
        archived=archived,
    )
    append_snapshot(updated, config)
    index_entry(updated, config)
    return updated


def create_backup(config: AppConfig, output: Path | None = None) -> Path:
    """Create a tar.gz backup with a checksum manifest."""
    root = config.data_dir
    _ensure_private_dir(root)
    destination = output.expanduser() if output else backups_root(config) / _default_backup_name()
    _ensure_private_dir(destination.parent)

    files = _collect_backup_files(config)
    manifest_lines = [f"{_sha256(path)}  {rel.as_posix()}" for rel, path in files]
    manifest_blob = "\n".join(manifest_lines)
    if manifest_blob:
        manifest_blob += "\n"

    with tarfile.open(destination, "w:gz") as archive:
        for rel, path in files:
            archive.add(path, arcname=rel.as_posix(), recursive=False)
        manifest_data = manifest_blob.encode("utf-8")
        info = tarfile.TarInfo(name="manifest.sha256")
        info.size = len(manifest_data)
        info.mode = 0o600
        archive.addfile(info, io.BytesIO(manifest_data))

    _set_private_file(destination)
    return destination


def restore_backup(
    config: AppConfig,
    *,
    archive_path: Path,
    dry_run: bool,
    force: bool,
) -> list[Path]:
    """Restore a backup archive after validating checksums."""
    source = archive_path.expanduser()
    if not source.exists():
        raise FileNotFoundError(source)

    with tarfile.open(source, "r:gz") as archive:
        members = {member.name: member for member in archive.getmembers() if member.isfile()}
        if "manifest.sha256" not in members:
            raise RuntimeError("backup missing manifest.sha256")
        manifest = archive.extractfile(members["manifest.sha256"])
        if manifest is None:
            raise RuntimeError("could not read backup manifest")
        expected = _parse_manifest(manifest.read().decode("utf-8"))

        planned: list[Path] = []
        for rel_name, checksum in expected.items():
            member = members.get(rel_name)
            if member is None:
                raise RuntimeError(f"backup missing expected file: {rel_name}")
            payload = archive.extractfile(member)
            if payload is None:
                raise RuntimeError(f"could not read backup file: {rel_name}")
            content = payload.read()
            actual = hashlib.sha256(content).hexdigest()
            if actual != checksum:
                raise RuntimeError(f"checksum mismatch for {rel_name}")
            rel_path = Path(rel_name)
            if rel_path.is_absolute() or ".." in rel_path.parts:
                raise RuntimeError(f"unsafe path in backup: {rel_name}")
            destination = config.data_dir / rel_path
            planned.append(destination)
            if dry_run:
                continue
            if destination.exists() and not force:
                raise RuntimeError(f"refusing to overwrite existing file: {destination}")
            _ensure_private_dir(destination.parent)
            destination.write_bytes(content)
            _set_private_file(destination)

    return planned


def export_entries_csv(entries: Sequence[NoteEntry], target: Path) -> None:
    """Write deterministic CSV output for note entries."""
    _ensure_private_dir(target.parent)
    with target.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(_ENTRY_KEYS))
        writer.writeheader()
        for entry in entries:
            payload = entry.to_dict()
            payload["tags"] = ",".join(entry.tags)
            writer.writerow(payload)
    _set_private_file(target)


def export_entries_jsonl(entries: Sequence[NoteEntry], target: Path) -> None:
    """Write deterministic JSONL output for note entries."""
    _ensure_private_dir(target.parent)
    with target.open("w", encoding="utf-8") as handle:
        for entry in entries:
            handle.write(json.dumps(entry.to_dict(), ensure_ascii=False, separators=(",", ":")) + "\n")
    _set_private_file(target)


def iter_snapshots(config: AppConfig) -> Iterable[dict[str, Any]]:
    """Yield all JSON snapshots from source files in lexical order."""
    root = entries_root(config)
    if not root.exists():
        return []
    payloads: list[dict[str, Any]] = []
    for year_dir in sorted(path for path in root.iterdir() if path.is_dir()):
        for month_dir in sorted(path for path in year_dir.iterdir() if path.is_dir()):
            for shard in sorted(month_dir.glob("*.jsonl")):
                for line in shard.read_text(encoding="utf-8").splitlines():
                    raw = line.strip()
                    if not raw:
                        continue
                    try:
                        payload = json.loads(raw)
                    except json.JSONDecodeError:
                        continue
                    if isinstance(payload, dict):
                        payloads.append(payload)
    return payloads


def parse_temporal_filter(value: str, *, is_end: bool) -> str:
    """Convert date/datetime values into canonical UTC timestamps."""
    cleaned = value.strip()
    if not cleaned:
        raise ValueError("time filter cannot be empty")
    if "T" in cleaned:
        dt = datetime.fromisoformat(cleaned.replace("Z", "+00:00"))
        return _iso_utc(_to_utc(dt))
    day = date.fromisoformat(cleaned)
    dt = datetime.combine(day, time.max if is_end else time.min, tzinfo=timezone.utc)
    if is_end:
        dt = dt.replace(microsecond=0)
    return _iso_utc(dt)


def generate_entry_id(moment: datetime) -> str:
    """Generate a 26-char ULID-compatible identifier."""
    stamp_ms = int(_to_utc(moment).timestamp() * 1000)
    if stamp_ms < 0 or stamp_ms >= (1 << 48):
        raise ValueError("timestamp out of ULID range")
    random_bits = int.from_bytes(secrets.token_bytes(10), "big")
    value = (stamp_ms << 80) | random_bits
    chars = ["0"] * 26
    for index in range(25, -1, -1):
        chars[index] = _CROCKFORD[value & 0x1F]
        value >>= 5
    return "".join(chars)


def _open_index(config: AppConfig) -> sqlite3.Connection:
    _ensure_private_dir(config.data_dir)
    path = index_path(config)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    _init_schema(conn)
    _set_private_file(path)
    return conn


def _init_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS entries (
            id TEXT PRIMARY KEY,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            kind TEXT NOT NULL,
            text TEXT NOT NULL,
            url TEXT,
            title TEXT,
            project TEXT,
            source TEXT NOT NULL,
            tags_json TEXT NOT NULL,
            archived INTEGER NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS entry_tags (
            entry_id TEXT NOT NULL,
            tag TEXT NOT NULL,
            PRIMARY KEY (entry_id, tag),
            FOREIGN KEY (entry_id) REFERENCES entries(id) ON DELETE CASCADE
        )
        """
    )
    _ensure_entry_columns(conn)
    _ensure_fts_table(conn)


def _ensure_entry_columns(conn: sqlite3.Connection) -> None:
    columns = {
        row[1] for row in conn.execute("PRAGMA table_info(entries)")
    }
    if "project" not in columns:
        conn.execute("ALTER TABLE entries ADD COLUMN project TEXT")
    if "source" not in columns:
        conn.execute("ALTER TABLE entries ADD COLUMN source TEXT NOT NULL DEFAULT 'cli'")


def _ensure_fts_table(conn: sqlite3.Connection) -> None:
    target = ["id", "text", "title", "url", "project", "source", "tags"]
    existing = [row[1] for row in conn.execute("PRAGMA table_info(entry_fts)")]
    if existing and existing != target:
        conn.execute("DROP TABLE entry_fts")
    try:
        conn.execute(
            """
            CREATE VIRTUAL TABLE IF NOT EXISTS entry_fts
            USING fts5(id, text, title, url, project, source, tags)
            """
        )
    except sqlite3.OperationalError as exc:
        raise RuntimeError("sqlite FTS5 is required but unavailable") from exc


def _upsert_entry(conn: sqlite3.Connection, entry: NoteEntry) -> None:
    conn.execute(
        """
        INSERT INTO entries (id, created_at, updated_at, kind, text, url, title, project, source, tags_json, archived)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            created_at = excluded.created_at,
            updated_at = excluded.updated_at,
            kind = excluded.kind,
            text = excluded.text,
            url = excluded.url,
            title = excluded.title,
            project = excluded.project,
            source = excluded.source,
            tags_json = excluded.tags_json,
            archived = excluded.archived
        """,
        (
            entry.id,
            _iso_utc(entry.created_at),
            _iso_utc(entry.updated_at),
            entry.kind,
            entry.text,
            entry.url,
            entry.title,
            entry.project,
            entry.source,
            json.dumps(list(entry.tags), separators=(",", ":")),
            1 if entry.archived else 0,
        ),
    )
    conn.execute("DELETE FROM entry_tags WHERE entry_id = ?", (entry.id,))
    for tag in entry.tags:
        conn.execute(
            "INSERT INTO entry_tags (entry_id, tag) VALUES (?, ?)",
            (entry.id, tag),
        )
    conn.execute("DELETE FROM entry_fts WHERE id = ?", (entry.id,))
    conn.execute(
        "INSERT INTO entry_fts (id, text, title, url, project, source, tags) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            entry.id,
            entry.text,
            entry.title or "",
            entry.url or "",
            entry.project or "",
            entry.source,
            " ".join(entry.tags),
        ),
    )


def _row_to_entry(row: sqlite3.Row) -> NoteEntry:
    tags = json.loads(row["tags_json"])
    return NoteEntry(
        id=str(row["id"]),
        created_at=_parse_timestamp(row["created_at"]),
        updated_at=_parse_timestamp(row["updated_at"]),
        kind=str(row["kind"]),
        text=str(row["text"]),
        url=_optional_text(row["url"]),
        title=_optional_text(row["title"]),
        project=_optional_text(row["project"]),
        source=str(row["source"] or "cli"),
        tags=tuple(str(tag) for tag in tags if str(tag).strip()),
        archived=bool(row["archived"]),
    )


def _entry_shard_path(moment: datetime, config: AppConfig) -> Path:
    local_day = _to_utc(moment).date()
    return (
        entries_root(config)
        / f"{local_day.year:04d}"
        / f"{local_day.month:02d}"
        / f"{local_day.isoformat()}.jsonl"
    )


def _default_backup_name() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%SZ")
    return f"muse-backup-{stamp}.tar.gz"


def _collect_backup_files(config: AppConfig) -> list[tuple[Path, Path]]:
    files: list[tuple[Path, Path]] = []

    config_file = config.data_dir / "config.json"
    if config_file.exists() and config_file.is_file():
        files.append((Path("config.json"), config_file))

    sqlite_file = index_path(config)
    if sqlite_file.exists() and sqlite_file.is_file():
        files.append((Path("index.sqlite"), sqlite_file))

    root = entries_root(config)
    if root.exists():
        for year_dir in sorted(path for path in root.iterdir() if path.is_dir()):
            for month_dir in sorted(path for path in year_dir.iterdir() if path.is_dir()):
                for shard in sorted(month_dir.glob("*.jsonl")):
                    rel = shard.relative_to(config.data_dir)
                    files.append((rel, shard))

    return sorted(files, key=lambda item: item[0].as_posix())


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8192), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _parse_manifest(raw: str) -> dict[str, str]:
    expected: dict[str, str] = {}
    for line in raw.splitlines():
        text = line.strip()
        if not text:
            continue
        checksum, _, rel = text.partition("  ")
        if not checksum or not rel:
            raise RuntimeError("invalid manifest format")
        expected[rel] = checksum
    return expected


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _parse_timestamp(value: Any) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("timestamp is required")
    return _to_utc(datetime.fromisoformat(value.replace("Z", "+00:00")))


def _to_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _iso_utc(value: datetime) -> str:
    return _to_utc(value).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _ensure_private_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(path, 0o700)
    except PermissionError:
        pass


def _set_private_file(path: Path) -> None:
    if not path.exists():
        return
    try:
        os.chmod(path, 0o600)
    except PermissionError:
        pass
