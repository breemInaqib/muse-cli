# Architecture decisions

These records define the accepted product and trust boundaries for museCLI's
first real agent capability. Read the consolidated
[product and agent contract](../product-contract.md) first.

| Record | Status | Scope |
| --- | --- | --- |
| [0001](0001-product-surfaces.md) | Accepted | Product surfaces and stable bare `muse` behavior |
| [0002](0002-agent-run-evidence-and-activity-projection.md) | Accepted | Durable evidence authority and visible projection |
| [0003](0003-first-read-only-muse-code-capability.md) | Accepted | First operational capability and lifecycle |
| [0004](0004-permissions-and-record-time-privacy.md) | Accepted | Pre-context approval, fail-closed rules, and data minimisation |
| [0005](0005-session-durability-and-workspace.md) | Accepted | Durable/process-local state and Textual ownership |
| [0006](0006-local-data-recovery-policy.md) | Accepted | Non-destructive local-data recovery release gate |

Acceptance records a design constraint, not an implemented capability. The
formal implementation gate and required future tests are in the consolidated
contract. Provider selection, exact `analyse` syntax, Python support changes,
Textual packaging changes, executable tools, replay, and export remain
reversible or deferred as stated there.
