from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Iterable, List

from .model import JournalEntry


@dataclass
class StatsSummary:
    """Summary statistics over a window of journal entries."""

    start: date
    end: date
    count: int
    average_mood: float
    top_tags: list[str]
    daily_averages: list[float | None]


def summarise(
    entries: Iterable[JournalEntry],
    *,
    start: date,
    end: date,
) -> StatsSummary:
    """Summarise entries across a date window."""
    tag_counter: Counter[str] = Counter()
    daily: dict[date, List[int]] = defaultdict(list)
    total_mood = 0
    count = 0
    for entry in entries:
        local_date = entry.timestamp.astimezone().date()
        if local_date < start or local_date > end:
            continue
        count += 1
        total_mood += entry.mood
        tag_counter.update(entry.tags)
        daily[local_date].append(entry.mood)
    span = (end - start).days + 1
    averages: list[float | None] = []
    day_cursor = start
    for _ in range(span):
        moods = daily.get(day_cursor)
        if moods:
            averages.append(sum(moods) / len(moods))
        else:
            averages.append(None)
        day_cursor += timedelta(days=1)
    average_mood = (total_mood / count) if count else 0.0
    top_tags = [tag for tag, _ in tag_counter.most_common(3)]
    return StatsSummary(
        start=start,
        end=end,
        count=count,
        average_mood=average_mood,
        top_tags=top_tags,
        daily_averages=averages,
    )
