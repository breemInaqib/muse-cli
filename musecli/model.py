from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping


@dataclass
class AppConfig:
    """Represent user configuration for MuseCLI."""

    data_dir: Path
    date_format: str
    editor: str | None
    export_dir: Path
    insights_enabled: bool
    debug: bool
    encryption_enabled: bool
    encryption_provider: str | None
    encryption_recipient: str | None

    @classmethod
    def defaults(cls, base_dir: Path | None = None) -> AppConfig:
        """Build a default configuration anchored at the base directory."""
        root = (base_dir or _default_data_dir()).expanduser()
        return cls(
            data_dir=root,
            date_format="%Y-%m-%d",
            editor=None,
            export_dir=root / "exports",
            insights_enabled=False,
            debug=False,
            encryption_enabled=False,
            encryption_provider=None,
            encryption_recipient=None,
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialise the configuration into JSON-friendly values."""
        return {
            "data_dir": str(self.data_dir),
            "date_format": self.date_format,
            "editor": self.editor,
            "export_dir": str(self.export_dir),
            "insights_enabled": self.insights_enabled,
            "debug": self.debug,
            "encryption_enabled": self.encryption_enabled,
            "encryption_provider": self.encryption_provider,
            "encryption_recipient": self.encryption_recipient,
        }

    @classmethod
    def from_dict(
        cls,
        data: Mapping[str, Any],
        base_dir: Path | None = None,
    ) -> AppConfig:
        """Create a configuration merging stored values onto defaults."""
        defaults = cls.defaults(base_dir)
        data_dir = _coerce_path(data.get("data_dir"), defaults.data_dir)
        export_dir = _coerce_path(data.get("export_dir"), defaults.export_dir)
        editor = data.get("editor")
        date_format = str(data.get("date_format", defaults.date_format))
        insights_enabled = bool(data.get("insights_enabled", defaults.insights_enabled))
        debug = bool(data.get("debug", defaults.debug))
        encryption_enabled = bool(data.get("encryption_enabled", defaults.encryption_enabled))
        encryption_provider = data.get("encryption_provider")
        encryption_recipient = data.get("encryption_recipient")
        return cls(
            data_dir=data_dir,
            date_format=date_format,
            editor=str(editor) if editor is not None else None,
            export_dir=export_dir,
            insights_enabled=insights_enabled,
            debug=debug,
            encryption_enabled=encryption_enabled,
            encryption_provider=str(encryption_provider) if encryption_provider else None,
            encryption_recipient=str(encryption_recipient) if encryption_recipient else None,
        )


@dataclass
class JournalEntry:
    """Represent a single mood log entry."""

    timestamp: datetime
    mood: int
    tags: tuple[str, ...]
    note: str
    long_note: str | None = None

    def __post_init__(self) -> None:
        """Normalise timestamp to UTC and clean tag values."""
        if self.timestamp.tzinfo is None:
            self.timestamp = self.timestamp.replace(tzinfo=timezone.utc)
        else:
            self.timestamp = self.timestamp.astimezone(timezone.utc)
        self.tags = tuple(tag.strip() for tag in self.tags if tag.strip())

    def to_dict(self) -> dict[str, Any]:
        """Serialise the journal entry for JSON storage."""
        return {
            "timestamp": self.timestamp.astimezone(timezone.utc).isoformat(),
            "mood": self.mood,
            "tags": list(self.tags),
            "note": self.note,
            "long_note": self.long_note,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> JournalEntry:
        """Create a journal entry from stored JSON values."""
        raw_timestamp = data.get("timestamp")
        if not isinstance(raw_timestamp, str):
            raise ValueError("entry timestamp missing or invalid")
        timestamp = datetime.fromisoformat(raw_timestamp)
        mood = int(data.get("mood", 0))
        tags_data = data.get("tags") or []
        note = str(data.get("note", ""))
        long_note = data.get("long_note")
        tags: Iterable[str]
        if isinstance(tags_data, Iterable) and not isinstance(tags_data, (str, bytes)):
            tags = (str(item) for item in tags_data)
        else:
            tags = []
        if long_note is not None:
            long_note = str(long_note)
        return cls(
            timestamp=timestamp,
            mood=mood,
            tags=tuple(tags),
            note=note,
            long_note=long_note,
        )


def _coerce_path(raw: Any, fallback: Path) -> Path:
    """Turn a raw path value into a Path instance."""
    if isinstance(raw, Path):
        return raw.expanduser()
    if isinstance(raw, str) and raw.strip():
        return Path(raw).expanduser()
    return fallback


def _default_data_dir() -> Path:
    """Pick a platform-native default data directory."""
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "musecli"
    xdg_home = os.environ.get("XDG_DATA_HOME")
    if xdg_home:
        return Path(xdg_home) / "musecli"
    return Path.home() / ".local" / "share" / "musecli"
