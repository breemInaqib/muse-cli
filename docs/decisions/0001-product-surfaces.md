# 0001: Product surfaces and bare `muse`

Status: **Accepted**

## Context

museCLI began as a local capture and personal workflow CLI. It now also has a
process-local visible workspace and the read-only `muse-code` evidence viewer.
Ordinary workspace input is an honest demonstration, not agent execution.

## Decision

museCLI is one local-first product with specialist entry points over shared
foundations:

- `muse` owns the original personal workflow, compact snapshot, and general
  process-local presentation shell;
- `muse-code` owns explicit coding operations and coding-run evidence;
- future entry points such as `muse-search` may own similarly explicit bounded
  capabilities;
- shared agent infrastructure remains internal and provider-neutral.

The original `add`, `inbox`, `focus`, `check-in`, and `today` commands remain
first-class behavior. Non-interactive bare `muse` remains a deterministic
snapshot with no agent or model activity. Interactive bare `muse` may open the
session shell, but ordinary input must not silently become a coding operation.

## Rationale

Explicit specialist entry points preserve the useful small CLI, keep capability
intent visible, and give coding operations an understandable permission and
evidence boundary. Making every prompt an agent request would turn a general
workspace affordance into implicit authorization.

## Consequences

The first real capability will not make ordinary `muse` input operational.
Specialist results may later appear in the workspace through persisted evidence
without moving execution ownership into the presentation.

## Alternatives considered

- Treating `muse`, `muse-code`, and `muse-search` as separate products would
  duplicate foundations and obscure their shared local state.
- Making ordinary `muse` input the first coding surface would weaken explicit
  intent and couple execution to the unfinished live-session lifecycle.
- Enabling both surfaces simultaneously would expand the test and permission
  surface before the first capability proves useful.

## Trust and privacy implications

Capability entry is deliberate and visible. Snapshot startup and ordinary
workspace input cannot trigger repository access. Specialist modes share the
same default-deny and evidence requirements.

## Verification implications

Future tests must preserve byte-for-byte non-interactive snapshot output,
original commands, explicit specialist invocation, and absence of model,
context, trace, or repository loading during snapshot startup.

## Reversible elements

Specialist capabilities may later be reachable through explicit workspace
commands. Exact command names and presentation affordances remain reversible.

## Deferred work

No `/code` command, model selection UI, or specialist-mode convergence is
accepted here. The Python floor and Textual packaging remain release decisions.
