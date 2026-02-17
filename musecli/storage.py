from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Iterable, Iterator, Tuple

from .model import AppConfig, JournalEntry

_CONFIG_FILENAME = "config.json"
_JOURNAL_DIRNAME = "journal"


def config_path(config: AppConfig) -> Path:
    """Return the path to the configuration file."""
    return config.data_dir / _CONFIG_FILENAME


def journal_root(config: AppConfig) -> Path:
    """Return the root directory for journal entries."""
    return config.data_dir / _JOURNAL_DIRNAME


def day_path(moment: datetime | date, config: AppConfig) -> Path:
    """Return the path to the journal file for the given moment."""
    if isinstance(moment, datetime):
        target = moment.astimezone().date()
    else:
        target = moment
    return (
        journal_root(config)
        / f"{target.year:04d}"
        / f"{target.month:02d}"
        / f"{target.isoformat()}.jsonl"
    )


def load_config(base_dir: Path | None = None) -> tuple[AppConfig, bool]:
    """Load configuration from disk or return defaults with a warning flag."""
    defaults = AppConfig.defaults(base_dir)
    path = config_path(defaults)
    if not path.exists():
        return defaults, False
    raw = path.read_text(encoding="utf-8")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return defaults, True
    return AppConfig.from_dict(data, base_dir=defaults.data_dir), False


def save_config(config: AppConfig) -> None:
    """Persist configuration to disk, creating directories as needed."""
    config.data_dir.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(config.to_dict(), indent=2, sort_keys=True)
    config_path(config).write_text(payload + "\n", encoding="utf-8")


def append_entry(entry: JournalEntry, config: AppConfig) -> Tuple[Path, bool]:
    """Append a journal entry to the appropriate day file."""
    entry_path = day_path(entry.timestamp, config)
    parent = entry_path.parent
    created = False
    if not parent.exists():
        parent.mkdir(parents=True, exist_ok=True)
        created = True
    with entry_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry.to_dict(), ensure_ascii=True) + "\n")
    return entry_path, created


def read_entries_for_day(target: date, config: AppConfig) -> list[JournalEntry]:
    """Read all entries for the given day."""
    path = day_path(target, config)
    if not path.exists():
        return []
    entries = list(_iter_entries_from_file(path))
    entries.sort(key=lambda item: item.timestamp)
    return entries


def rewrite_day(entries: Iterable[JournalEntry], target: date, config: AppConfig) -> Path:
    """Rewrite the journal file for a given day."""
    entry_path = day_path(target, config)
    parent = entry_path.parent
    parent.mkdir(parents=True, exist_ok=True)
    tmp_path = entry_path.with_suffix(".tmp")
    try:
        with tmp_path.open("w", encoding="utf-8") as handle:
            for entry in sorted(entries, key=lambda item: item.timestamp):
                handle.write(json.dumps(entry.to_dict(), ensure_ascii=True) + "\n")
        tmp_path.replace(entry_path)
    finally:
        tmp_path.unlink(missing_ok=True)
    return entry_path


def iter_entries_between(
    start: date,
    end: date,
    config: AppConfig,
) -> Iterator[JournalEntry]:
    """Yield entries between two dates inclusive."""
    cursor = start
    while cursor <= end:
        for entry in read_entries_for_day(cursor, config):
            yield entry
        cursor += timedelta(days=1)


def iter_all_entries(config: AppConfig) -> Iterator[JournalEntry]:
    """Yield all stored entries in chronological order."""
    root = journal_root(config)
    if not root.exists():
        return
    for year_dir in sorted(p for p in root.iterdir() if p.is_dir()):
        for month_dir in sorted(p for p in year_dir.iterdir() if p.is_dir()):
            for day_file in sorted(month_dir.glob("*.jsonl")):
                yield from _iter_entries_from_file(day_file)


def ensure_export_dir(config: AppConfig) -> Path:
    """Create the export directory if it does not exist."""
    config.export_dir.mkdir(parents=True, exist_ok=True)
    return config.export_dir


def _iter_entries_from_file(path: Path) -> Iterator[JournalEntry]:
    """Yield entries parsed from a JSONL file."""
    with path.open("r", encoding="utf-8") as handle:
        for raw in handle:
            line = raw.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
                yield JournalEntry.from_dict(payload)
            except (json.JSONDecodeError, ValueError):
                continue


def iter_entries(
    start: date,
    end: date,
    config: AppConfig,
) -> Iterator[JournalEntry]:
    """Yield entries between two dates inclusive."""
    yield from iter_entries_between(start, end, config)
