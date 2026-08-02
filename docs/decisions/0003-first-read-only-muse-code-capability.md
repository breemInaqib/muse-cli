# 0003: First read-only `muse-code` capability

Status: **Accepted**

## Context

`muse-code` currently lists and inspects evidence but creates no runs. The
provider-neutral harness is synchronous and has no observer, cancellation, or
subprocess lifecycle. Connecting it to the TUI first would combine several
unproven boundaries.

## Decision

The first real capability belongs to an explicit `muse-code` command and
performs bounded read-only repository analysis. Conceptually:

```bash
muse-code analyse "Explain the parser architecture" --path PATH
```

The objective and path are explicit. After permission preflight, registered
context operations may read only the approved scope. A configured
provider-neutral runner returns a structurally validated analysis or proposal.
Deterministic checks cover approved-scope confinement, the selected-context
manifest and digests, response-schema validity, source-reference integrity,
prohibited-capability absence, and trace controls before a supported outcome is
claimed. These checks do not establish absolute semantic correctness. Evidence
is saved for `list` and `inspect`.

The first run is synchronous and process-bound. It has no file mutation,
subprocess, shell, network, background loop, replay, or automatic resumption.
Ctrl+C terminates the command; interruption is recorded only when persistence
can honestly confirm it. Otherwise the trace remains visibly incomplete.

## Rationale

Read-only analysis exercises context, model, permission, privacy, trace, and
verification foundations without rollback or subprocess termination. A
specialist command keeps intent explicit and avoids making the TUI the first
execution owner.

## Consequences

The implementation will need bounded context selection, a runner adapter,
structured output validation, pre-context approval, record-time redaction, and
deterministic analysis verification. It will not validate live TUI streaming.

## Alternatives considered

- Ordinary `muse` input was rejected because it would be implicit capability
  entry and blur demonstration versus execution.
- Simultaneous CLI and TUI integration was rejected because lifecycle,
  projection, and cancellation are not yet defined in code.
- Mutation and shell tools were rejected because their verification and
  recovery obligations exceed the first slice.

## Trust and privacy implications

Read access is restricted to a visible canonical scope. Ignored, binary, large,
out-of-scope, and secret-bearing data follows ADR 0004 and fails closed where
safe minimisation cannot be proven.

## Verification implications

Tests must show explicit invocation, bounded context, structural output
validation, durable evidence, recomputed controls, honest interruption, and the
absence of mutation, subprocess, shell, and network capabilities.

## Reversible elements

`analyse` spelling, path option syntax, model adapter, response schema, and
deterministic context limits remain provisional within the accepted boundary.

## Deferred work

Live workspace execution, cooperative cancellation, writes, subprocesses,
network search, replay, export, and durable live sessions are deferred.
