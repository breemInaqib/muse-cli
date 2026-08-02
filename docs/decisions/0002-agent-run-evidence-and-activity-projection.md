# 0002: Agent-run evidence and Activity projection

Status: **Accepted**

## Context

The agent harness records durable `TraceEvent`s. The simple and Textual
presentations display process-local, privacy-safe `Activity` objects. Current
activities are deterministic demonstration fixtures and are not audit evidence.

## Decision

`TraceEvent` is authoritative for real agent-run history. A real-run `Activity`
may be projected only after its source event has been successfully persisted.
Projection is one-way and deterministic:

```text
persisted TraceEvent -> privacy-safe projection -> Activity
```

Projection may omit fields, group several events, and change display summaries.
It may not mutate the trace, invent unsupported progress, or reinterpret run
truth. A persistence failure blocks or visibly degrades the operation before a
completed activity is shown. Presentation switching does not create, duplicate,
or change evidence.

Pure UI notices do not require trace events. Demonstration activities remain
explicit fixtures and must be visually distinguishable from projected real-run
activities.

## Rationale

The trace schema serves audit and deterministic evaluation; `Activity` serves
readable presentation. Keeping them separate avoids coupling private evidence
to UI needs. Making persistence the visibility boundary prevents two competing
accounts of what happened.

## Consequences

A future adapter must own projection ordering, privacy filtering, grouping, and
idempotency. The TUI cannot optimistically claim persisted progress. Display
wording may evolve without a trace-schema migration.

## Alternatives considered

- Merging both models would place presentation concerns in durable evidence.
- Producing them independently would permit contradiction or lost audit data.
- Projecting before persistence would show progress the system cannot later
  substantiate.

## Trust and privacy implications

Raw trace dictionaries, specifications, content, arguments, credentials, and
unredacted paths never enter `Activity`. Projection is not a redaction fallback:
record-time privacy still applies to the durable event.

## Verification implications

Tests must prove persistence-before-visibility, deterministic and idempotent
projection, private-field exclusion, immutable traces, visible write failure,
and no duplicate projection during presentation switching.

## Reversible elements

Activity wording, grouping, filters, and which low-level events are displayed
may change without changing trace authority.

## Deferred work

The adapter, event subscription, streaming, replay, and concurrent writers are
not designed or implemented by this record.
