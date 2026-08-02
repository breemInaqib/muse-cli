# museCLI design

The original capture workflow remains a first-class part of the broader
[product and agent contract](product-contract.md). Future agent capabilities
use explicit specialist entry points; they do not silently reinterpret the
capture commands or ordinary workspace input.

## model

museCLI uses one visible flow:

```text
capture -> inbox -> focus -> done
check-in -> today
```

Specialist capabilities form explicit adjacent flows over shared local-first
foundations:

```text
muse       -> personal workflow and general presentation shell
muse-code  -> coding capability and coding-run evidence
muse-search (future) -> explicit search/research capability
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
- The interactive session keeps explicit process-local activity state. It is
  visible in both presentations and is discarded on exit.
- Durable state remains limited to the queue database, journal files, config
  file, and append-only agent run evidence.

## storage

Default root: `~/.muse`

- `~/.muse/muse.db` for queue state
- `~/.muse/journal/YYYY/MM/YYYY-MM-DD.jsonl` for journal entries
- `~/.muse/config.json` for paths
- `~/.muse/agent/runs/RUN_ID.jsonl` for private agent run evidence

Interactive session activities are not persisted.

For real agent work, persisted `TraceEvent`s are authoritative. A display-safe
`Activity` may be projected only after its source event is persisted; the
projection never changes durable evidence. See
[ADR 0002](decisions/0002-agent-run-evidence-and-activity-projection.md).
