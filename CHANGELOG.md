# Changelog

## Unreleased

- Record the exact local, hosted-CI, and unobserved compatibility boundaries for
  the release-ready baseline.

- preserve incompatible or corrupt queue databases and SQLite sidecars instead of resetting them
- surface malformed journal lines while preserving valid entries and original JSONL evidence
- add deterministic source-distribution verification and stronger installed-wheel CI smoke checks
- add provider-neutral agent control and evidence boundaries
- add read-only `muse-code inspect RUN_ID` workflow inspection
- add deterministic, privacy-bounded `muse-code list` run discovery
- add one process-local visible activity session shared by simple and workspace views
- add the responsive, keyboard-first `muse --tui` workspace
- add lazy read-only navigation of existing muse-code run evidence in the workspace
- add shared, display-safe session command and capability semantics
- add clean-exit startup measurement for simple and workspace presentations
- defer historical evidence modules until a user requests runs or inspection
- verify package contents, runtime dependencies, entry points, and fresh-wheel behaviour
- expand CI across Python 3.9, 3.11, and 3.13, plus macOS and Windows smoke coverage
- modernize the proprietary licence expression used in package metadata
- document the locked source-checkout and cross-platform verification workflow

## v0.1.0

- initial release of museCLI
- minimal local-first CLI for capture, focus, and reflection
- commands: add, inbox, focus, check-in, today
