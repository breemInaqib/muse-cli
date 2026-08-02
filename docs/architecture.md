# museCLI architecture

This document describes the implementation that exists today. The accepted
product direction, first real capability, authority rules, and implementation
gate are defined in the [product and agent contract](product-contract.md) and
the linked [architecture decisions](decisions/README.md). Accepted decisions
are constraints for future work, not claims that agent execution already
exists.

museCLI is a small Typer CLI with direct local persistence:

- `musecli/cli.py`
  Command routing, input validation, prompts, and output rendering.
- `musecli/session.py`
  Framework-neutral process-local session, activity, plan, shared command
  normalization, capability, and presentation-transition contracts.
- `musecli/interactive.py`
  Simple line-oriented session rendering and presentation coordination.
- `musecli/tui.py`
  Textual workspace rendering, navigation, and explicit read-only run
  inspection.
- `musecli/config.py`
  Data directory defaults and config persistence.
- `musecli/queue.py`
  SQLite queue storage for inbox, focus, and done items, with read-only
  validation and non-destructive classified failures for existing data.
- `musecli/journal.py`
  JSONL check-in storage for `today`, including explicit malformed-line
  evidence without automatic rewriting.
- `musecli/utils.py`
  Timestamps, file permissions, text truncation, and clipboard reads.
- `musecli/__init__.py`
  Package marker and version.
- `musecli/agent/`
  Provider-neutral contracts and orchestration for context, proposals,
  permissions, controlled tools, verification, evaluation, and audit events.
- `musecli/code_cli.py`
  Read-only `muse-code` command routing and evidence-loading errors.
- `musecli/workflow_index.py`
  Run discovery, privacy-bounded summaries, deterministic ordering, and list
  rendering.
- `musecli/workflow_view.py`
  Deterministic rendering of saved agent workflow evidence.

## commands

- `muse`
- `muse --tui`
- `muse add`
- `muse inbox`
- `muse focus`
- `muse check-in`
- `muse today`
- `muse-code list`
- `muse-code inspect RUN_ID`

`muse` with no command opens the simple session when standard input and output
are terminals. A non-terminal invocation prints the existing home snapshot
and exits. `muse --tui` opens the workspace directly.
`muse-code list` and `muse-code inspect` are separate, read-only commands so
the primary workflow and its locked command surface remain unchanged.

## interactive application

```text
Typer callback
  -> one SessionController
  -> simple presentation
       /workspace
  -> Textual presentation
       /simple
  -> same SessionState
```

`SessionState` owns the session ID, ordered display-safe activities, and the
current plan. A presentation transition returns a next-presentation value and
never submits work. Widget selection, focus, scrolling, and overlays remain
presentation state. Slash-command normalization and capability labels are
shared application semantics; each presentation only chooses how to render or
perform the resulting read-only UI action.

The first implementation uses an explicitly labelled deterministic
demonstration. It creates intent, plan, context, permission, tool,
verification, and result activities without running a model or tool. Skipped
states and the final result make that boundary visible. These activities stay
in memory and are not written as agent evidence.

Historical run discovery is lazy. Both presentations reuse
`load_workflow_index()` for privacy-bounded summaries and recomputed controls.
The workspace uses the existing strict loader and `render_workflow()` only
after the user explicitly opens a run. Evidence reads use non-fatal workers:
an operating-system or structural read failure degrades the selected panel
without exposing the underlying exception or exiting the workspace.

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
Incompatible, corrupt, locked, and inaccessible existing databases fail without
deleting or replacing the main file or SQLite sidecars. No automatic migration
or reset is performed. See [local-data recovery](recovery.md).

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

## agent workflow evidence

```text
explicit request
  -> context provider
  -> model runner returns a proposal
  -> permission preflight for every proposed call
  -> controlled tool execution
  -> deterministic verifiers
  -> trace evaluation
  -> verified, rejected, or failed result
  -> ~/.muse/agent/runs/RUN_ID.jsonl
```

This is the order implemented by the current harness. The accepted first
repository-analysis capability adds a user-approved, fail-closed scope
preflight **before** the context provider reads repository data. Existing
tool-call permission preflight remains required after the proposal. See
[ADR 0004](decisions/0004-permissions-and-record-time-privacy.md).

Model output is a proposal, not authorization. A denied call prevents the
complete proposal from executing. A run is only `verified` after tool,
verification, and trace-evaluation checks pass.

`muse-code list` discovers the JSONL files directly, loads each independently,
extracts only start time, objective, recorded completion state, and identity,
then recomputes trace controls. Valid start times sort newest first with
filename-order ties; entries without usable starts follow in filename order.
The strict single-run loader used by `inspect` continues to require the
filename and recorded run ID to agree.

Local agent evidence is stored under
`~/.muse/agent/runs/RUN_ID.jsonl`, alongside the queue database and journal
JSONL files.

See [muse-code workflow evidence](muse-code.md) for the trace format, discovery
and inspection commands, privacy boundary, and explicit exclusions.
See [visible workspace](workspace.md) for session behaviour, layout, commands,
and cancellation limits.
