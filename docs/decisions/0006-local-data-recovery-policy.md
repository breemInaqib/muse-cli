# 0006: Local user-data recovery policy

Status: **Accepted**

Implementation: **Release baseline implemented for non-destructive detection and failure.**
Automatic migration, repair, and a built-in destructive reset remain absent.

## Context

Agent evidence degrades malformed runs visibly and does not repair them. Before
this release correction, the original queue could delete and recreate an
incompatible or corrupt SQLite database, including sidecars, while journal
reads silently skipped malformed lines. That behavior conflicted with a
local-first evidence product.

## Decision

museCLI must not silently destroy or conceal local user data in the name of
recovery.

- Incompatible schemas and corrupt databases remain preserved when a safe
  automatic migration is unavailable.
- Approved migration or repair creates a recoverable backup before mutation,
  including relevant SQLite sidecars.
- Migration failure leaves the original recoverable and emits a visible error.
- A read-only diagnosis path precedes destructive recovery.
- Destructive reset requires an explicit command or confirmation that identifies
  affected paths and consequences.
- Malformed journal records remain preserved and produce a visible diagnostic;
  valid records may still be read when isolation is not misleading.

This is a release-readiness gate. It is deliberately separate from the first
agent implementation.

## Rationale

Local-first trust requires preservation and inspectability of user-owned data.
Convenient automatic reset is not an acceptable substitute for explicit
recovery, and silent journal skipping conceals evidence of corruption.

## Consequences

Ordinary queue and journal operations now fail or degrade non-destructively.
Because no automatic migration, repair, or reset is supported, museCLI creates
no backup implicitly. Any future built-in recovery operation must add the
backup, permission, and failure tests required by this decision.

## Alternatives considered

- Keeping automatic reset was rejected because it can destroy the only local
  copy without consent.
- Failing without diagnostic or recovery information was rejected as safe but
  insufficiently usable.
- Repairing files in place without backup was rejected because failure could
  compound corruption.

## Trust and privacy implications

Backups are private local user data and must inherit restrictive permissions.
Diagnostics should identify affected paths without printing stored content.
Recovery must not upload or inspect data through network services.

## Verification implications

Future tests must cover schema mismatch, corrupt SQLite, sidecars, failed and
successful migration, backup permissions, malformed journal lines, mixed valid
and malformed journal evidence, read-only diagnosis, and explicit destructive
reset. They must prove originals survive failure.

## Reversible elements

Backup naming, migration command syntax, diagnostic formatting, and retention
policy may be selected during release-readiness implementation.

## Deferred work

No migration, recovery command, reset confirmation, or journal repair is
implemented in this design-decision pass.
