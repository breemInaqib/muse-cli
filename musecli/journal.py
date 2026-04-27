"""Journal storage for museCLI."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterator, Mapping

from .config import AppConfig
from .utils import ensure_private_dir, ensure_private_file, iso_utc, parse_timestamp, to_utc


@dataclass
class JournalEntry:
    """One journal check-in row."""

    timestamp: datetime
    mood: int
    note: str

    def __post_init__(self) -> None:
        self.timestamp = to_utc(self.timestamp)
        self.mood = int(self.mood)
        self.note = self.note.strip()
        if not 1 <= self.mood <= 5:
            raise ValueError("mood must be between 1 and 5")
        if not self.note:
            raise ValueError("note is required")

    def to_dict(self) -> dict[str, Any]:
        """Serialize a journal entry for JSONL."""
        return {
            "timestamp": iso_utc(self.timestamp),
            "mood": self.mood,
            "note": self.note,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> JournalEntry:
        """Create a journal entry from persisted JSON."""
        return cls(
            timestamp=parse_timestamp(data.get("timestamp")),
            mood=int(data.get("mood", 0)),
            note=str(data.get("note", "")),
        )


def journal_root(config: AppConfig) -> Path:
    """Return the root folder for journal entries."""
    return config.journal_dir


def day_path(moment: datetime | date, config: AppConfig) -> Path:
    """Return the JSONL path for a local day."""
    target = moment.astimezone().date() if isinstance(moment, datetime) else moment
    return (
        journal_root(config)
        / f"{target.year:04d}"
        / f"{target.month:02d}"
        / f"{target.isoformat()}.jsonl"
    )


def append_entry(entry: JournalEntry, config: AppConfig) -> tuple[Path, bool]:
    """Append one journal entry to its day file."""
    target = day_path(entry.timestamp, config)
    created = not target.parent.exists()
    ensure_private_dir(target.parent)
    with target.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry.to_dict(), ensure_ascii=True) + "\n")
    ensure_private_file(target)
    return target, created


def read_entries_for_day(target: date, config: AppConfig) -> list[JournalEntry]:
    """Read and sort all journal entries for one day."""
    path = day_path(target, config)
    if not path.exists():
        return []
    entries = list(_iter_entries(path))
    entries.sort(key=lambda entry: entry.timestamp)
    return entries


def _iter_entries(path: Path) -> Iterator[JournalEntry]:
    with path.open("r", encoding="utf-8") as handle:
        for raw in handle:
            line = raw.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            try:
                yield JournalEntry.from_dict(payload)
            except ValueError:
                continue
