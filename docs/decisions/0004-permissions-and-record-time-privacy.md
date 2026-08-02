# 0004: Permissions and record-time privacy

Status: **Accepted**

## Context

The current permission policy is default-deny for proposed tool calls, but the
harness gathers context before that preflight. Current traces may contain exact
objectives, workspace paths, model responses, tool arguments, and verifier
evidence. Privacy-bounded rendering cannot remove data already persisted.

## Decision

The first capability has two permission boundaries:

1. Before repository access, a pre-context approval shows the canonical scope,
   requested read capabilities, exclusions, and decision. Interactive use
   requires explicit approval. Non-interactive use fails closed unless a later
   deliberate approval flag or policy is designed.
2. After a model proposal, the existing default-deny call preflight remains in
   force. Model output cannot grant or expand permission.

Unknown capability, scope escape, symlink escape, ambiguous canonicalisation,
or attempted escalation fails closed. No mutation, subprocess, shell, or
network permission exists in the first capability.

Permission evidence records the capability identifier, approved root label and
bounded relative scope, decision, reason or approval source, trace-event time,
and relation to the operation.

Privacy classification and field rules are normative in the consolidated
[product contract](../product-contract.md#record-time-privacy-contract).
Minimisation and deterministic redaction occur before `TraceStore.record()`.
Redaction failure fails closed. Environment variables, credentials, tokens,
secret-store values, binary contents, and ignored-file contents are prohibited
in the first slice. File content and assembled prompts are not persisted by
default; provenance, template/version information, bounded references, and
digests are preferred.

`list` remains privacy-bounded. `inspect` explicitly shows the redacted local
evidence stored. No trace is automatically safe to share and no export exists.

## Rationale

Repository reads are consequential local access and must precede context
gathering, not be retroactively authorised by tool permissions. Record-time
minimisation protects durable evidence; display filtering alone does not.

## Consequences

The existing harness order cannot be reused unchanged for repository context.
The first implementation needs a narrow pre-context decision contract and a
redaction boundary before trace storage. It must define deterministic canonical
scope and secret-handling behavior.

## Alternatives considered

- Treating command invocation as approval was rejected because the scope and
  capability set would not be visibly confirmed.
- Per-file prompts were rejected as excessive for bounded read-only analysis.
- Persisting full local content was rejected as unnecessary and unsafe.
- Presentation-only redaction was rejected because private data would remain in
  the trace.

## Trust and privacy implications

Approval is user-owned, scoped, visible, and non-transferable to broader model
requests. Local traces remain sensitive even after minimisation. Secret
detection is a fail-closed safety control, not a claim that all secrets can be
recognised.

## Verification implications

Tests must cover approval-before-read, canonical scope display, non-interactive
failure, unknown capability and scope-escape denial, model non-authority,
absolute-path redaction, content minimisation, secret sentinels, redaction
failure, private `list`, explicit `inspect`, and absence of export.

## Reversible elements

Prompt wording, a future explicit non-interactive approval mechanism, context
limits, and redaction presentation may evolve while preserving fail-closed
scope and record-time minimisation.

## Deferred work

A general approval framework, mutation permissions, network consent, export
preview, user-configurable redaction profiles, and secret-store integrations are
deferred.
