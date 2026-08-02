"""Journal storage for museCLI."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

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


@dataclass(frozen=True)
class JournalIssue:
    """One safely described malformed journal line."""

    line_number: int
    kind: str


@dataclass(frozen=True)
class JournalReadResult:
    """Valid entries plus explicit degradation evidence for one journal file."""

    path: Path
    entries: tuple[JournalEntry, ...]
    issues: tuple[JournalIssue, ...]


class JournalReadError(RuntimeError):
    """Raised when a strict journal read encounters malformed records."""

    def __init__(self, result: JournalReadResult) -> None:
        super().__init__("journal contains malformed records")
        self.result = result


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
    """Strictly read a day, failing visibly if any record is malformed."""
    result = read_day(target, config)
    if result.issues:
        raise JournalReadError(result)
    return list(result.entries)


def read_day(target: date, config: AppConfig) -> JournalReadResult:
    """Read valid records while retaining safe evidence of malformed lines."""
    path = day_path(target, config)
    if not path.exists():
        return JournalReadResult(path=path, entries=(), issues=())
    entries: list[JournalEntry] = []
    issues: list[JournalIssue] = []
    with path.open("rb") as handle:
        for line_number, raw in enumerate(handle, start=1):
            try:
                line = raw.decode("utf-8").strip()
            except UnicodeDecodeError:
                issues.append(JournalIssue(line_number=line_number, kind="invalid encoding"))
                continue
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                issues.append(JournalIssue(line_number=line_number, kind="malformed JSON"))
                continue
            if not isinstance(payload, Mapping):
                issues.append(JournalIssue(line_number=line_number, kind="invalid record"))
                continue
            try:
                entries.append(JournalEntry.from_dict(payload))
            except (TypeError, ValueError):
                issues.append(JournalIssue(line_number=line_number, kind="invalid record"))
    entries.sort(key=lambda entry: entry.timestamp)
    return JournalReadResult(path=path, entries=tuple(entries), issues=tuple(issues))
