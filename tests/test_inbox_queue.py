from __future__ import annotations

from datetime import datetime, timezone

from musecli.config import AppConfig
from musecli.queue import add_item, discard_item, keep_item, list_inbox_items, list_pinned_items


def test_keep_and_discard_change_queue_state(tmp_path) -> None:
    config = AppConfig.defaults(base_dir=tmp_path)
    item = add_item(
        config,
        text="keep me",
        now=datetime(2026, 3, 5, 9, 0, tzinfo=timezone.utc),
    )

    changed = keep_item(
        config,
        item_id=item.id,
        pinned=True,
        now=datetime(2026, 3, 5, 9, 1, tzinfo=timezone.utc),
    )
    assert changed is True
    assert list_inbox_items(config) == []
    assert [focus_item.id for focus_item in list_pinned_items(config)] == [item.id]

    discarded = discard_item(
        config,
        item_id=item.id,
        now=datetime(2026, 3, 5, 9, 2, tzinfo=timezone.utc),
    )
    assert discarded is True
    assert list_pinned_items(config) == []


def test_inbox_ordering_newest_first(tmp_path) -> None:
    config = AppConfig.defaults(base_dir=tmp_path)
    oldest = add_item(
        config,
        text="oldest",
        now=datetime(2026, 3, 5, 8, 0, tzinfo=timezone.utc),
    )
    middle = add_item(
        config,
        text="middle",
        now=datetime(2026, 3, 5, 9, 0, tzinfo=timezone.utc),
    )
    newest = add_item(
        config,
        text="newest",
        now=datetime(2026, 3, 5, 10, 0, tzinfo=timezone.utc),
    )

    items = list_inbox_items(config)
    assert [item.id for item in items] == [newest.id, middle.id, oldest.id]
