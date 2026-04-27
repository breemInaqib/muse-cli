# museCLI design

## model

museCLI uses one visible flow:

```text
capture -> inbox -> focus -> done
check-in -> today
```

State names are literal:

- inbox: unprocessed
- focus: active
- done: discarded
- today: journal

## decisions

- `add` captures text.
- `inbox` decides whether an item is kept, focused, discarded, or left unchanged.
- `focus` only decides whether an active item is done or left unchanged.
- `check-in` writes one journal entry.
- `today` reads the latest journal entry for the local day.

## behavior

- Output is deterministic.
- Commands do one thing.
- Prompts show every available choice.
- Invalid input does not change state.
- There is no hidden state outside the queue database, journal files, and config file.

## storage

Default root: `~/.muse`

- `~/.muse/muse.db` for queue state
- `~/.muse/journal/YYYY/MM/YYYY-MM-DD.jsonl` for journal entries
- `~/.muse/config.json` for paths
