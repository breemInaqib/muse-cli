from __future__ import annotations

from datetime import date, datetime
from typing import Iterable, Sequence

_SPARKLINE_BINS = "▁▂▃▄▅▆▇█"


def truncate(text: str, width: int) -> str:
    """Trim text to the desired width with an ellipsis when needed."""
    if len(text) <= width:
        return text
    if width <= 3:
        return text[:width]
    return text[: width - 3] + "..."


def render_table(headers: Sequence[str], rows: Sequence[Sequence[str]]) -> str:
    """Render a plain ASCII table suitable for narrow terminals."""
    widths = [len(header) for header in headers]
    for row in rows:
        widths = [max(width, len(cell)) for width, cell in zip(widths, row)]

    def format_row(values: Sequence[str]) -> str:
        return " | ".join(value.ljust(widths[idx]) for idx, value in enumerate(values))

    header_line = format_row(headers)
    separator = "-+-".join("-" * width for width in widths)
    body_lines = [format_row(row) for row in rows]
    return "\n".join([header_line, separator, *body_lines]) if body_lines else "\n".join([header_line, separator])


def format_date(value: date, *, pattern: str) -> str:
    """Format a date using the configured pattern."""
    return value.strftime(pattern)


def day_header(value: date, *, pattern: str) -> str:
    """Return a short header label for a day."""
    formatted = value.strftime(pattern)
    weekday = value.strftime("%a")
    return f"{formatted} · {weekday}"


def format_local_time(timestamp: datetime) -> str:
    """Format the timestamp in the user's local timezone."""
    return timestamp.astimezone().strftime("%H:%M")


def join_tags(tags: Iterable[str]) -> str:
    """Join tags for display, showing a dash when empty."""
    return ", ".join(tags) if tags else "-"


def sparkline(
    values: Sequence[float | None],
    *,
    minimum: float = 1.0,
    maximum: float = 5.0,
) -> str:
    """Render a Unicode sparkline for the supplied values."""
    usable = [value for value in values if value is not None]
    if not usable:
        return ""
    min_value = minimum if minimum is not None else min(usable)
    max_value = maximum if maximum is not None else max(usable)
    if max_value <= min_value:
        max_value = min_value + 1e-6
    glyphs: list[str] = []
    last_non_space = -1
    for index, value in enumerate(values):
        if value is None:
            glyphs.append(" ")
            continue
        clamped = min(max(value, min_value), max_value)
        ratio = (clamped - min_value) / (max_value - min_value)
        glyph_index = int(round(ratio * (len(_SPARKLINE_BINS) - 1)))
        glyphs.append(_SPARKLINE_BINS[glyph_index])
        last_non_space = index
    if last_non_space >= 0:
        glyphs = glyphs[: last_non_space + 1]
    return "".join(glyphs)
