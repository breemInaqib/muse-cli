# museCLI architecture

museCLI is a small Typer CLI with two storage files:

- `musecli/cli.py`
  Command routing, input validation, prompts, and output rendering.
- `musecli/config.py`
  Data directory defaults and config persistence.
- `musecli/queue.py`
  SQLite queue storage for inbox, focus, and done items.
- `musecli/journal.py`
  JSONL check-in storage for `today`.
- `musecli/utils.py`
  Timestamps, file permissions, text truncation, and clipboard reads.
- `musecli/__init__.py`
  Package marker and version.

## commands

- `muse`
- `muse add`
- `muse inbox`
- `muse focus`
- `muse check-in`
- `muse today`

`muse` with no command prints a home snapshot and exits.

## state model

- inbox: unprocessed queue items
- focus: active pinned items
- done: discarded items
- today: journal entries for the local day

## queue transitions

```text
muse add "task"
  -> cli.add()
  -> queue.add_item()
  -> status=inbox, pinned=0

muse inbox
  -> k: status=kept, pinned=0
  -> p: status=kept, pinned=1
  -> d: status=discarded, pinned=0
  -> q: no change

muse focus
  -> d: status=discarded, pinned=0
  -> q: no change
```

Queue rows are stored in `~/.muse/muse.db`.

## journal flow

```text
muse check-in --mood 4 --note steady
  -> cli.check_in()
  -> journal.append_entry()
  -> ~/.muse/journal/YYYY/MM/YYYY-MM-DD.jsonl

muse today
  -> journal.read_entries_for_day()
  -> latest entry for the local day
```
