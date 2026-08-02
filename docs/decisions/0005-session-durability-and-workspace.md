# 0005: Session durability, lifecycle, and workspace ownership

Status: **Accepted**

## Context

One `SessionState` currently survives simple-to-Textual presentation switching
but disappears at process exit. Agent traces are durable. The TUI navigates
Activities and historical runs but owns no execution or cancellation contract.

## Decision

Durable state is limited to queue items, journal entries, configuration,
successfully persisted agent traces, and summaries recomputed from those
traces. `SessionState`, projected Activities, current plan, composer input,
selected presentation, focus, selections, scroll positions, open screens, and
palette state remain process-local.

The first operational run is synchronous and process-bound. Persisted events
survive exit, but incomplete work is not resumed automatically. Missing terminal
evidence remains visibly incomplete. `cancelled` may be claimed only after the
operation owner confirms termination and that evidence is persisted; an
interrupt request alone is insufficient.

The Textual workspace owns presentation, navigation, visible activities,
plan/context/permission/source views, historical discovery, explicit deep
inspection, and switching presentations. It does not own model or tool
execution, permission truth, trace persistence, verification, evaluation,
durable state, or cancellation semantics.

Future persisted `muse-code` events may be projected into the workspace under
ADR 0002. The workspace is not the initial execution owner.

## Rationale

Durable live sessions would introduce recovery, replay, concurrency, and stale
state before the first capability proves useful. Keeping Textual presentational
preserves safety and permits the synchronous specialist slice to validate the
agent system independently.

## Consequences

Exiting loses process-local display state. A crash may leave a trace incomplete,
but it cannot be presented as success. Additional TUI panels and execution UI
remain frozen until persisted real events create a concrete need.

## Alternatives considered

- Persisting `SessionState` was rejected because it is not audit evidence and
  has no recovery contract.
- Making Textual the first execution owner was rejected because cancellation,
  worker ownership, and event subscription are absent.
- Treating Textual worker cancellation as operation cancellation was rejected
  because it cannot prove the underlying work stopped.

## Trust and privacy implications

Presentation state cannot change durable truth. Only privacy-safe projections
enter Activities. Incomplete and interrupted evidence remains inspectable
without inferred success.

## Verification implications

Tests must preserve one session across presentation switching, prevent duplicate
projection, distinguish projected and demonstration activity, show incomplete
traces honestly, and prove no automatic resume or false cancellation.

## Reversible elements

Activity grouping, workspace placement, and later opt-in session persistence may
be reconsidered after a recovery contract exists.

## Deferred work

Observer subscriptions, streaming, cooperative model cancellation, subprocess
termination, crash recovery, replay, durable live sessions, and concurrent
writers are deferred prerequisites for later live or executable work.
