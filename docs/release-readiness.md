# Release-readiness evidence

This document defines the compatibility claims supported by the release
baseline. The GitHub Actions workflow is the authoritative hosted record; local
observations supplement it rather than substituting for it.

## Hosted CI

The `ci` workflow verifies:

- the complete test suite, Ruff lint, Ruff formatting, and the locked dependency
  graph on Ubuntu with Python 3.9, 3.11, and 3.13;
- the complete test suite, generated `muse` and `muse-code` launchers,
  non-interactive output, and Textual headless behavior on macOS and Windows
  with Python 3.13;
- real simple-session and Textual workspace pseudo-terminal readiness on macOS;
- the source distribution and wheel on Ubuntu with Python 3.13, including
  deterministic content checks, a fresh wheel installation, `pip check`, both
  console entry points, non-interactive output, synthetic historical-run
  inspection, and installed-wheel pseudo-terminal readiness.

Action dependencies are pinned to commits. CI network access is used only for
dependency and action acquisition; museCLI runtime tests require no network.

## Locally observed

On macOS 26.5.2 arm64, clean locked source environments and clean wheel
environments were exercised with Python 3.9.6 and 3.13.5. Observations include:

- `uv sync --locked`, lock validation, the full test suite, Ruff, and package
  construction;
- deterministic wheel and source-distribution verification;
- import-origin checks proving wheel smoke tests did not use the source tree;
- `muse --help`, non-interactive `muse`, `muse --tui`, `muse-code --help`,
  `muse-code list`, and explicit `muse-code inspect` behavior;
- clean `/exit` through pseudo-terminals for the simple and Textual views;
- the startup measurements recorded in [Visible workspace](workspace.md).

Python 3.11 was not installed locally. Its support claim comes from the hosted
Ubuntu job, not a local simulation.

## Configured but not directly observed

The Windows job proves framework-supported headless interaction, generated
launchers, non-interactive behavior, storage tests, and the non-TTY `--tui`
guard. It does not prove behavior in every interactive Windows terminal host.
The Unix pseudo-terminal measurement helper is intentionally unsupported on
Windows.

No Linux terminal was manually operated during this baseline pass. Linux
pseudo-terminal readiness is covered by the installed-wheel package job, while
the Ubuntu matrix covers non-interactive and headless behavior.

## Support boundary

The supported Python versions are 3.9, 3.11, and 3.13. Textual is a required
runtime dependency because a normal installation must make `muse --tui`
immediately available; it remains lazily imported for help, subcommands, and
non-interactive snapshot startup.

This evidence does not claim that Windows interactive terminal behavior is
identical to Unix, that Python versions outside the configured matrix work, or
that the current workspace performs real agent execution.
