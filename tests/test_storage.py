from __future__ import annotations

import json
from datetime import datetime, timezone

from musecli.config import AppConfig
from musecli.journal import JournalEntry, append_entry, journal_root


def test_append_entry_creates_journal_tree(tmp_path) -> None:
    config = AppConfig.defaults(base_dir=tmp_path)
    entry = JournalEntry(
        timestamp=datetime(2024, 1, 1, 9, 30, tzinfo=timezone.utc),
        mood=4,
        note="morning check",
    )

    path, created = append_entry(entry, config)

    assert created is True
    assert path.exists()
    assert path.parent.parent.parent == journal_root(config)

    lines = path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    payload = json.loads(lines[0])
    assert payload["mood"] == 4
    assert payload["note"] == "morning check"
