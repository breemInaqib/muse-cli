from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from musecli.model import JournalEntry
from musecli.stats import summarise


def test_summarise_empty_window() -> None:
    end = date.today()
    start = end - timedelta(days=6)

    summary = summarise([], start=start, end=end)

    assert summary.count == 0
    assert summary.average_mood == 0.0
    assert summary.top_tags == []
    assert summary.daily_averages == [None] * 7


def test_summarise_with_entries() -> None:
    end = date(2024, 5, 7)
    start = end - timedelta(days=6)
    entry_one = JournalEntry(
        timestamp=datetime(2024, 5, 6, 20, 0, tzinfo=timezone.utc),
        mood=4,
        tags=("focus", "calm"),
        note="good evening",
        long_note=None,
    )
    entry_two = JournalEntry(
        timestamp=datetime(2024, 5, 7, 8, 0, tzinfo=timezone.utc),
        mood=2,
        tags=("tired",),
        note="slow start",
        long_note=None,
    )

    summary = summarise([entry_one, entry_two], start=start, end=end)

    assert summary.count == 2
    assert summary.average_mood == 3.0
    assert {"focus", "calm"}.issuperset(summary.top_tags[:2])
    assert len(summary.daily_averages) == 7
    assert summary.daily_averages[-1] == 2.0
