# museCLI product and agent contract

Status: **Accepted**

This document defines how museCLI's original personal workflow and its future
specialist agent capabilities belong to one local-first product. The detailed
rationale and consequences are recorded in [architecture decisions](decisions/README.md).

## Product contract

museCLI is a calm, local-first personal workflow CLI that may host explicit,
inspectable specialist capabilities. The capture workflow remains useful in its
own right; agent capabilities do not replace it and are not silently inferred
from ordinary input.

```text
non-interactive muse
  -> compact local snapshot
  -> no model, repository context, agent run, or input loop
  -> deterministic exit

interactive muse
  -> general process-local session
  -> simple presentation <-> Textual workspace
  -> display-safe Activities and read-only historical-run views
  -> ordinary input remains an explicitly labelled demonstration until a
     specialist capability is deliberately entered

muse-code
  -> explicit coding capability
  -> first real slice: bounded read-only repository analysis
  -> visible scope and permission preflight
  -> provider-neutral runner and structured result
  -> deterministic structural verification
  -> persisted TraceEvents and durable outcome
  -> list / inspect

future specialist entry points, such as muse-search
  -> explicit bounded capability
  -> shared permission, evidence, privacy, and verification foundations

persisted TraceEvents
  -> authoritative durable evidence
  -> one-way privacy-safe projection
  -> Activities visible in a future live workspace
```

`muse`, `muse-code`, and future specialist entry points are not separate
products. They are specialised entry points over shared local configuration,
agent contracts, permission rules, trace evidence, and evaluation. `muse` owns
the general workflow and presentation shell. `muse-code` owns explicit coding
operations and coding-run evidence. Specialist entry points may converge in
presentation later, but their capability boundaries remain explicit.

The original commands remain stable product behavior:

```text
add
inbox
focus
check-in
today
```

### Bare `muse`

When either standard input or standard output is not a TTY, bare `muse` must:

- render the compact snapshot and exit deterministically;
- perform no agent execution or context gathering;
- load no model and enter no input loop;
- remain safe for redirection and scripts.

This is a compatibility contract, not a presentation preference.

When both streams are TTYs, bare `muse` may enter the process-local simple
session. The prompt is a general workspace shell for viewing plans, context,
permissions, sources, and historical evidence. Until a specialist capability
is explicitly connected, ordinary free text remains the visibly labelled
deterministic demonstration and must not be reinterpreted as an authorised
coding operation.

`/workspace` and `/simple` change presentations over the same `SessionState`.
Switching preserves the session ID, plan, and activities. Process-local state
disappears when the process exits.

### First real capability

The first operational agent capability belongs to `muse-code`. Its user-level
contract is bounded read-only repository analysis:

- the user supplies an explicit objective and repository or path scope;
- museCLI shows the scope and requested read capabilities before access;
- a configured provider-neutral model runner receives bounded context and must
  return a structurally validated analysis or proposal;
- registered operations may read only the approved local scope;
- no file mutation, subprocess, shell, network, or implicit escalation exists;
- deterministic checks verify approved-scope confinement, the context manifest
  and digests, structured-response schema, source-reference integrity,
  prohibited-capability absence, and trace controls;
- successfully recorded evidence remains discoverable through `list` and
  inspectable through `inspect`.

The conceptual command is:

```bash
muse-code analyse "Explain the parser architecture" --path PATH
```

`analyse` communicates a read-only result and does not imply file mutation.
The exact spelling and option names remain provisional until CLI usability is
tested; ownership, read-only scope, and explicit invocation are accepted.

## Evidence and visibility contract

`TraceEvent` is authoritative for agent-run history. A visible `Activity`
representing real agent work may be created only from a `TraceEvent` after that
event has been successfully persisted. Projection is one-way:

```text
persisted TraceEvent -> deterministic privacy filter -> display-safe Activity
```

Projection may omit private fields, combine low-level events, or change display
wording. It must not mutate, replace, or reinterpret durable evidence. A trace
write failure must block or visibly degrade the operation; it must never produce
a completed activity unsupported by evidence. Presentation switching must not
record, duplicate, or alter events.

Pure presentation notices need no trace. Existing deterministic demonstration
activities remain fixtures and are not agent evidence. Real-run activities must
be visibly distinguishable from demonstrations.

## Permission contract

Starting an explicit read-only command requests capability; it does not itself
grant access. Before any repository content is read, museCLI must show:

- the canonical repository or path scope;
- the registered read capabilities requested;
- the absence of mutation, subprocess, and network capabilities;
- the decision required from the user.

In an interactive terminal the user must explicitly approve this preflight.
Non-interactive execution fails closed unless a separately designed, explicit
approval flag or policy is present. No such flag is accepted by this decision.
Unknown capabilities and paths outside the approved scope fail closed. Model
output can request an operation but cannot grant or expand permission.

The current harness performs tool permission preflight after context gathering.
The first real slice therefore requires a distinct pre-context scope approval
boundary; the existing tool-call permission checks remain necessary after a
proposal. Both decisions must be recorded with capability, canonical scope,
decision, reason or source, event time, and relation to the operation.

## Record-time privacy contract

Local storage is private, not automatically safe to share. Redaction and
minimisation happen before `TraceStore.record()`; rendering is not a substitute
for safe recording. Redaction failure fails closed.

The classifications are: `public display` for fixed application vocabulary that
contains no user data; `local summary` for bounded display-safe metadata;
`sensitive local evidence` for private material requiring minimisation; and
`secret or prohibited` for data the first capability must not intentionally
read or record.

| Data | Classification | Record-time rule |
| --- | --- | --- |
| Fixed status, capability, and control labels | public display | May be displayed and recorded without user-derived detail. |
| User objective | sensitive local evidence | Store locally and document that it may be sensitive. |
| Repository name | local summary | Store a user-facing name when it is not itself secret. |
| Absolute path | sensitive local evidence | Do not record by default; canonicalise for permission checks, then replace with an approved root label and relative path. |
| Relative path | local summary | Record only when within the approved root and safe for display. |
| File contents | sensitive local evidence | Do not copy into traces by default; record provenance and digest. Explicit future exceptions require size limits and approval. |
| File digest | local summary | Record with algorithm and provenance reference. |
| Model prompt | sensitive local evidence | Do not persist the assembled prompt by default; record template/version, bounded input references, and digest. |
| Model response | sensitive local evidence | Persist only the validated structured result needed to explain the run; exclude hidden reasoning and unneeded raw text. |
| Tool/context arguments | sensitive local evidence | Store a deterministic redacted representation after scope validation. |
| Permission scope | local summary | Store the approved root label, bounded relative scope, capabilities, and decision; omit unnecessary absolute paths. |
| Verifier output | sensitive local evidence | Store concise deterministic result and bounded evidence; redact paths and values first. |
| Environment variables | secret or prohibited | Never enumerate or intentionally record. |
| Credentials, tokens, secret-store values | secret or prohibited | Never intentionally read or record; detection causes fail-closed redaction or operation failure. |
| Ignored files | sensitive local evidence | Excluded by default; a future explicit inclusion policy is required. |
| Binary data | sensitive local evidence | Do not read or record in the first slice; metadata alone may explain exclusion. |
| Large files | sensitive local evidence | Exclude using deterministic limits; record only metadata and the exclusion reason. |

`muse-code list` remains limited to the privacy-bounded workflow index.
`muse-code inspect` is an explicit local deep-inspection action and may display
the redacted evidence actually stored in the trace. A future export requires a
separate redaction, review, and preview design; raw local traces are not a
shareable format.

## Result and verification semantics

Activity status describes one visible activity. Run status describes the
claimed outcome of the complete workflow. These namespaces must not be treated
as equivalent.

| Term | Precise meaning |
| --- | --- |
| `pending` | The activity is recorded but has not started. |
| `active` | The activity has started and has no terminal activity status. |
| `complete` | That activity's bounded work finished; it does not by itself mean the user's objective succeeded. |
| `skipped` | The activity deliberately did not run and cannot support claims that require it. |
| `blocked` | The activity cannot proceed without a permission, input, or prerequisite. |
| `failed` | The activity or run encountered a terminal error. |
| `rejected` | The run did not execute its proposal because permission or policy denied it. |
| `cancelled` | The owner confirmed termination before normal completion; a mere interrupt request is insufficient. |
| `verified` | Required operations succeeded, every configured verifier passed, and recomputed trace controls support the claim. |
| `controls: pass` | The saved trace satisfies the evaluator's deterministic structural and behavioural invariants. |

`verified` and `controls: pass` do not prove absolute semantic correctness,
complete context, verifier adequacy, or truth outside the evidence checked.
Skipped verification cannot support a verified run. A saved `verified` result
with failed recomputed controls remains visibly contradictory. Demonstration
completion must continue to say that only the demonstration completed and that
the requested task was not executed.

An interrupted process may leave an incomplete trace. It may record
interruption only when the system can persist that fact honestly. Otherwise
`list` and `inspect` must show the missing terminal evidence as incomplete, not
infer cancellation or success.

## Durability and presentation contract

Durable state:

- queue items;
- journal entries;
- configuration;
- successfully recorded agent `TraceEvent`s;
- historical-run summaries recomputed from traces.

Process-local application state:

- `SessionState` and `Activity` projections;
- current plan and composer input;
- selected presentation and view;
- focus, selection, scroll positions, open screens, and palette state.

The first real run is synchronous and process-bound. Successfully recorded
events survive process exit. An unfinished run is not automatically resumed,
replayed, or converted into durable session state.

The Textual workspace owns presentation, navigation, activity visibility,
plan/context/permission/source views, historical discovery, explicit deep
inspection, and switching to the simple presentation. It does not own model or
tool execution, permission truth, trace persistence, verification truth,
evaluation, durable state, or cancellation semantics.

The workspace is not the first execution owner. A later adapter may display
persisted `muse-code` events. Decorative panels, new workflow states, provider
selection, permission dialogs, and mutation previews remain frozen until a
real capability demonstrates the need.

## Local user-data safety gate

museCLI must not silently destroy or conceal local user data in the name of
recovery. Before release readiness can be claimed:

- incompatible or corrupt queue databases and SQLite sidecars must be
  preserved when safe migration is unavailable;
- approved migration or repair must create a recoverable backup first;
- migration failure must leave the original recoverable and fail visibly;
- malformed journal lines must be reported rather than silently discarded;
- read-only diagnosis must be available before destructive recovery;
- destructive reset must require an explicit command or confirmation with the
  affected paths and consequences visible.

The release baseline implements the non-destructive ordinary-operation side of
this gate: queue validation preserves the database and sidecars, and journal
reads surface malformed lines without rewriting them. No automatic migration,
backup, repair, or built-in destructive reset is provided. See
[local-data recovery](recovery.md).

## Formal implementation gate

Implementation of the first real agent capability may begin only when its work
plan and tests demonstrate all of the following:

- `muse-code` owns the capability and invocation is explicit;
- the operation is bounded read-only repository analysis;
- the objective and path-scope contract are visible;
- pre-context permission approval occurs before any repository read;
- unknown or expanded scope fails closed;
- no mutation, subprocess, shell, or network capability is registered;
- `TraceEvent` is durable authority and projection follows persistence;
- record-time minimisation and deterministic redaction are applied before
  storage, with fail-closed errors;
- verification and result terminology follows this contract;
- execution is synchronous and process-bound;
- the TUI remains a later consumer rather than execution owner;
- non-interactive bare `muse` and the original commands remain unchanged.

Required future tests include:

### Product boundaries

- byte-for-byte non-interactive `muse` snapshot compatibility;
- unchanged original command behavior;
- explicit `muse-code` invocation;
- ordinary interactive input never starting a coding run;
- no model, context, trace, or repository loading during snapshot startup.

### Trace projection

- no real activity before successful persistence;
- deterministic event projection and grouping;
- exclusion of every private event field from `Activity`;
- projection never mutating trace evidence;
- trace-write failure never appearing as completed work;
- presentation switching never duplicating projection.

### Permissions and privacy

- visible canonical scope before approval;
- non-interactive and unknown-capability failure closed;
- no scope escalation by context logic or model output;
- no mutation, subprocess, shell, or network registration;
- path normalisation and absolute-path redaction;
- secret-looking values excluded before persistence;
- redaction failure closed;
- privacy-bounded `list`, explicit `inspect`, and absence of export.

### Verification and lifecycle

- skipped verification never producing `verified`;
- contradictory saved status remaining visible;
- interruption producing incomplete or honestly failed evidence, never false
  success;
- controls always recomputed;
- unfinished runs not automatically resumed.

### Data safety and compatibility

- future incompatible storage handling preserving originals;
- malformed journal evidence becoming visible;
- destructive reset requiring explicit action;
- existing build, wheel, entry-point, and startup checks remaining intact;
- Textual remaining lazily loaded;
- supported Python versions decided using hosted CI evidence.

## Reversible and deferred choices

Reversible during the first slice:

- exact `analyse` command spelling and options;
- model-provider adapter;
- structured response schema details;
- context size and file limits, provided they remain deterministic and bounded;
- activity grouping and display summaries.

Deferred to hosted CI and release readiness:

- the current configured Python 3.9, 3.11, and 3.13 support matrix remains in
  force until hosted evidence is reviewed;
- Textual remains a required runtime dependency and lazily imported so
  non-interactive workflows do not start the TUI;
- any change to the Python 3.9/3.11/3.13 support policy;
- whether Textual remains a required dependency;
- implementation of the local-data recovery policy;
- platform-specific release claims.

Deferred to a later mutation-capable phase:

- file writes, subprocesses, shell access, and network access;
- background or autonomous work;
- cooperative cancellation and subprocess termination evidence;
- durable live sessions, crash recovery, replay, and concurrent trace writers;
- permission interfaces for consequential actions;
- redacted workflow export.
