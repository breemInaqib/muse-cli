# Visible workspace

`muse` has two presentations over one process-local session:

```text
muse             simple terminal session
muse --tui       full-screen workspace
```

Inside a session, `/workspace` opens the full-screen presentation and
`/simple` returns to the line-oriented presentation. The session ID, ordered
activities, current plan, and latest result remain the same. Switching views
does not resubmit input or start another operation.

Bare `muse` only starts a session when both standard input and standard output
are terminals. Redirected and piped invocations retain the deterministic home
snapshot and exit, preserving the script-safe behaviour from earlier releases.
`muse --tui` requires a terminal.

## What the first slice does

Ordinary input records a small deterministic demonstration:

```text
intent        complete
plan          complete
context       skipped
permission    skipped
tool          skipped
verification  skipped
result        complete
```

The result means the demonstration finished. It does **not** mean the user's
request succeeded. The interface states that no model, context retrieval,
permission grant, tool, shell command, network request, file change, or task
verification occurred.

This slice establishes one session, one activity representation, and two
presentations. It deliberately does not add model execution, executable tools,
network retrieval, file mutation, interactive approvals, replay, or export.

## Commands

The session composer accepts ordinary text and these commands:

```text
/help          show available commands
/context       show gathered context
/plan          show the current plan
/permissions   show capability and permission state
/runs          discover saved muse-code runs
/sources       show retrieved sources
/workspace     open the full-screen presentation
/simple        return to the line-oriented presentation
/exit          end the session
```

Input beginning with `!` is refused because shell execution is unavailable.
Unknown slash commands are reported and do not change session state.

EOF and `/exit` exit successfully. Ctrl+C exits with status 130. No cancelled
activity is recorded because the deterministic demonstration completes before
the prompt returns.

## Workspace layout and keyboard use

The workspace adapts to terminal width:

```text
110 columns or wider   runs | activity | details
70–109 columns         activity | details
under 70 columns       activity, with secondary screens
```

The composer remains visible in every layout. Tab and Shift+Tab move focus,
arrow keys navigate focused lists, Enter opens a selected item, Esc closes a
secondary screen, and Ctrl+K opens the command palette. State words remain
visible when colour is disabled:

```bash
NO_COLOR=1 muse --tui
```

### Presentation framework

The workspace uses `textual>=8.2,<9`, with Textual 8.2.8 resolved in
`uv.lock`. It preserves the project's Python 3.9 floor and provides the
responsive classes, keyboard focus, command palette, and headless `run_test()`
surface needed by this slice without introducing another application or
storage framework.

Textual is a lazy-loaded presentation dependency. Simple startup, redirected
snapshot output, help, and existing subcommands do not import the workspace
module. Textual workers perform only explicit read-only evidence access here;
their completion or cancellation is not agent evidence.

## Saved run evidence

`/runs` reads the configured `agent/runs` directory only when requested. It
reuses the same privacy-bounded summaries and deterministic evaluator as:

```bash
muse-code list
```

Run rows distinguish the saved final status from recomputed trace controls.
A run that claims `verified` while controls fail remains visibly
contradictory. Malformed, incomplete, mismatched, and unreadable files remain
visible in a degraded state rather than being silently omitted.

The overview does not show raw context content, specifications, or tool
arguments. Opening a run is an explicit deep-inspection action and uses the
same detailed renderer as:

```bash
muse-code inspect RUN_ID
```

Detailed evidence is private local material and may contain specifications,
tool arguments, and verification evidence.

## State and trust boundaries

Application state consists of the session ID, ordered activities, and current
plan. Widget focus, scroll position, open dialogs, and palette state belong to
the presentation and need not survive a view change.

Session activities are in memory only. They are not audit evidence and
disappear at process exit. Existing append-only JSONL agent runs remain the
only durable workflow evidence.

The agent harness, default-deny permission policy, controlled tool interface,
verification contracts, trace evaluator, and JSONL schema are unchanged.
There is no live harness adapter in this slice.

## Startup measurement

Run the standard-library pseudo-terminal measurement from the environment
containing the installed `muse` executable:

```bash
python scripts/measure_startup.py --muse /path/to/muse
```

The helper ships in the repository and source distribution as development
evidence tooling. It is not installed into the runtime wheel.

The helper depends on the Unix pseudo-terminal API and is supported on macOS
and Linux. On Windows, use the framework-supported headless workspace smoke
tests instead:

```powershell
uv run --locked --extra dev python -m pytest tests/test_tui.py
```

That verifies Textual interaction without claiming a pseudo-terminal startup
measurement for Windows.

It records the first fresh-process launch as cold and the median of five
subsequent fresh-process launches as warm. The boundary is process start to a
visible input-ready marker. It measures both simple and workspace
presentations and requires each `/exit` request to finish with status 0.
Forced termination is cleanup after a failed measurement, never a successful
sample.

The final post-change installed-wheel measurements were:

| Python | presentation | cold | warm median |
| --- | --- | ---: | ---: |
| 3.13.5 | simple | 84.3 ms | 88.3 ms |
| 3.13.5 | workspace | 363.7 ms | 264.5 ms |
| 3.9.6 | simple | 106.4 ms | 83.4 ms |
| 3.9.6 | workspace | 1,289.2 ms | 1,247.6 ms |

These were recorded on `2026-07-30` on macOS 26.5.2 arm64, using Textual
8.2.8, the built `musecli-0.1.0` wheel, and five warm samples. The helper
prints its exact environment and timestamp. Cold results were visibly
filesystem-cache-sensitive, so warm medians are the more useful comparison.

Before the change, repeatable warm medians were 95.2 ms simple / 267.0 ms
workspace on Python 3.13 and 99.2 ms simple / 1,262.6 ms workspace on Python
3.9. The implemented change defers historical audit, index, and detailed
renderer imports until `/runs` or explicit inspection. A separate seven-sample
Python 3.9 import probe moved the `musecli.tui` median from 176.9 ms to
166.6 ms, a 10.3 ms improvement consistent with the small boundary that was
changed. The full readiness results show a similarly modest effect; no TUI
redesign was justified.

Python 3.9 workspace startup therefore remains above one second. Most of that
time occurs during Textual application startup and first render, not museCLI's
historical evidence imports. It remains a documented performance limitation,
not a passing claim.

The application initializes local configuration and storage before showing
input. It does not invoke a model, access the network, build embeddings, index
a repository, or scan historical runs during startup.

## Known limitation

Switching while a model, network request, mutation, subprocess, or verifier is
active is not yet supported. Safe cancellation requires an application-owned
cancellation token, adapter checkpoints, subprocess termination, and observed
completion evidence. Textual worker cancellation alone is not sufficient
proof that an underlying operation stopped.
