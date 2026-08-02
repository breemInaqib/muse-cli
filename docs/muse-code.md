# muse-code workflow evidence

`muse-code` is the read-only CLI surface for discovering and understanding
local coding-agent runs.

```bash
muse-code list
muse-code inspect RUN_ID
```

Use the same data-directory override as `muse` when needed:

```bash
muse-code list --data-dir PATH
muse-code inspect RUN_ID --data-dir PATH
```

Listing and inspection never execute tools or change a recorded run.

## discovering runs

`muse-code list` scans the local run directory directly; it does not create or
maintain a separate index. It renders one privacy-bounded entry per `*.jsonl`
candidate:

```text
muse-code runs

2026-07-27T15:00:00Z  saved: verified  controls: pass
  run: parser-fix
  intent: Fix parser error handling

2026-07-27T14:30:00Z  saved: verified  controls: fail
  run: unsupported-claim
  intent: Update command validation
  issue: verified claim is not supported by trace controls

unknown  saved: unreadable  controls: unavailable
  run: broken
  intent: unavailable
  issue: malformed evidence
```

Entries with exactly one valid recorded `run_started` event are ordered by
that event's timestamp, newest first. Equal timestamps use filename order.
Entries without a usable start timestamp follow, also in filename order. If
the run directory does not exist or contains no JSONL candidates, the command
prints `no saved runs` and exits successfully.

The `saved` value is the terminal status recorded in `run_completed`. The
`controls` value is recomputed from the complete trace using the same
deterministic evaluator as `inspect`. A saved `verified` claim can therefore
appear with `controls: fail`; listing never infers success from prose or trusts
the saved evaluation label by itself.

Malformed JSON, unsupported schema versions, invalid timestamps, mixed
recorded run IDs, and unreadable files appear as degraded entries when the
filename can be listed safely. One bad file does not prevent other files from
being shown. Incomplete but structurally readable traces show their available
start time and objective, an `incomplete` or invalid saved state, failed
controls, and concise issues for missing evidence.

The filename stem identifies the stored artifact and is what appears after
`run:`. The recorded event ID is independently validated. If they disagree,
neither is accepted as authoritative evidence: the entry shows the mismatch,
controls fail, and strict `inspect` loading refuses the trace. This avoids
turning a renamed or inconsistent file into an apparently valid workflow.

Objectives are normalized to one line and shortened deterministically to 60
characters. The list does not render specifications, retrieved context,
context references, proposals, permission details, tool arguments, action
evidence, or verifier evidence. Use:

```bash
muse-code inspect RUN_ID
```

for the complete human-readable evidence of a valid run selected from the
list.

## workflow

The agent harness records these boundaries in order:

1. user objective and exact acceptance specification
2. selected context references and content digests
3. model-runner proposal and reasons for requested calls
4. explicit permission decisions for every proposed call
5. tool results, change status, and supporting evidence
6. deterministic verification results
7. evaluation of harness behaviour
8. terminal run status

A run is `verified` only when its tools succeed, every configured verifier
passes, and the trace evaluator finds the expected control evidence.
`muse-code inspect` recomputes those trace invariants from the saved events. It
does not trust a saved evaluation or terminal `verified` label by itself.

Permission checks happen for the complete proposal before any tool executes.
One denied or unknown tool rejects the proposal without partial execution. If a
tool fails after execution begins, later tools are explicitly skipped and
verification still inspects the resulting state.

## local storage

Run evidence is append-only JSONL:

```text
~/.muse/agent/runs/RUN_ID.jsonl
```

The data directory can be overridden. Run identifiers are restricted to safe
filename characters, directories are set to `0700`, and trace files are set to
`0600` where the platform permits.

Each event has:

- `schema_version`
- `run_id`
- `sequence`
- `timestamp`
- `event_type`
- structured `data`

Malformed records and sequence mismatches fail closed during inspection and
appear in a degraded state during listing.

## evidence and privacy

The private local trace stores the exact user specification, proposal,
permission decisions, tool arguments, summaries, and verifier evidence.
Retrieved context content is not copied into the trace; its reference, kind,
and SHA-256 digest are recorded instead.

Tool arguments and evidence may still contain local paths or private values.
Do not share the raw JSONL file without reviewing it. `muse-code list` limits
output to run identity, start time, objective, saved status, recomputed control
status, and fixed diagnostic messages. A redacted export format is
intentionally not part of this slice.

## current boundaries

This foundation does not yet provide:

- a model-provider adapter
- built-in file, shell, or network tools
- interactive permission approval
- replay or adaptation of a prior run
- redacted export
- trace repair, deletion, or mutation
- concurrent audit-log writers

Those capabilities should build on the existing runner, context, tool,
permission, verifier, trace, and evaluation contracts rather than bypassing
them.
