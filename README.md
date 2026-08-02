# museCLI

museCLI is a small, local-first CLI for capturing thoughts and working through them step by
step. In an interactive terminal, `muse` also provides a visible session for inspecting how
agent-shaped work is represented without silently invoking a model or tools.

It is designed to feel calm, simple, and predictable to return to every day.

Command: `muse`

---

## Running museCLI

Prerequisites: Python 3.9 or newer and [uv](https://docs.astral.sh/uv/).
From the repository root, the recommended path is:

```bash
uv sync --locked
uv run muse
uv run muse --tui
uv run muse-code list
uv run muse-code inspect RUN_ID
```

The lockfile is the canonical dependency set. The interactive `muse` views
need a usable terminal; `muse-code list` is a deterministic, read-only view of
local run evidence.

Without `uv`, use a local virtual environment.

Unix and macOS:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e .
```

Windows PowerShell:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e .
```

After activation, run `muse`, `muse --tui`, or `muse-code list` directly.

To verify a checkout, install the locked development dependencies and run:

```bash
uv sync --locked --extra dev
uv lock --check
./scripts/check.sh  # Unix and macOS
uv run --locked --extra dev python -m pytest
uv run --locked --extra dev python -m ruff check .
uv run --locked --extra dev python -m ruff format --check .
uv run --locked --extra dev python -m build
uv run --locked --extra dev python scripts/verify_wheel.py dist/musecli-0.1.0-py3-none-any.whl
uv run --locked --extra dev python scripts/verify_sdist.py dist/musecli-0.1.0.tar.gz
```

On Windows, use the explicit `uv run` checks; the pseudo-terminal startup
measurement is Unix-only. Windows CI covers the generated launchers,
non-interactive output, and the Textual workspace through headless tests. See
[Contributing](CONTRIBUTING.md) and [Visible workspace](docs/workspace.md) for
the exact verification boundary.

### Compatibility boundary

The release workflow tests the full suite on Ubuntu with Python 3.9, 3.11, and
3.13. It also tests Python 3.13 on macOS and Windows. macOS and Linux support
real pseudo-terminal readiness checks; Windows uses generated-launcher,
non-interactive, and framework-supported headless Textual checks. This does not
claim that interactive Windows terminal behavior is identical to Unix PTYs.

Textual is a declared runtime dependency but remains lazily imported: help,
subcommands, and redirected snapshot startup do not start the TUI. Python 3.9
Textual startup around 1.25 seconds remains a known performance limitation, not
a compatibility failure.

---

## flow

```text
add -> inbox -> focus -> check-in -> today
```

A simple loop:

- capture something
- decide what to do with it
- keep a small set of active items
- reflect briefly

---

## interactive session

Run `muse` in a terminal to see your current state and open the simple session:

```text
museCLI

  inbox: 0

focus
  empty

today
  no check-in

muse · local · demo
  session: a1b2c3d4
  model: none · tools: off · network: off

›
```

The opening snapshot shows:

- how many items are waiting
- what you are currently focused on
- your latest check-in today

Ordinary input creates a deterministic, process-local demonstration of visible
intent, plan, context, permission, tool, verification, and result activities.
It does not execute the request. The result says so explicitly.

Use `/workspace` to open the full-screen view over the same session, or launch
it directly:

```bash
muse --tui
```

Use `/simple` to return. `/help` lists the session commands. A redirected or
non-interactive bare `muse` invocation keeps the existing snapshot-and-exit
behaviour for scripts.

See [Visible workspace](docs/workspace.md) for the interface, safety, privacy,
and persistence boundaries.

The accepted responsibilities of `muse`, `muse-code`, the workspace, and the
first future read-only coding capability are recorded in the
[product and agent contract](docs/product-contract.md). This is a design
contract, not a claim that model-backed analysis is implemented today.

---

## capture

Add something quickly:

```bash
muse add "text"
muse add --stdin
muse add --clipboard  # uses clipboard if available
```

Output:

```text
added
```

---

## inbox

Process items one at a time:

```text
inbox

  task text

  [k] keep   [d] discard   [p] pin   [q] quit
```

- `k` keep it
- `d` discard it
- `p` pin it to focus
- `q` exit

Empty:

```text
inbox

  empty
```

---

## focus

Work through pinned items:

```text
focus

  task text

  [d] done   [q] quit
```

- `d` mark as done (removes it from focus)
- `q` exit

Empty:

```text
focus

  empty
```

---

## check-in

Record a simple reflection:

```bash
muse check-in --mood 4 --note "steady"
```

Output:

```text
saved
```

---

## today

View today’s latest check-in:

```text
today

  no check-in
```

or:

```text
today

  mood: 4
  note: steady
```

---

## storage

All data is stored locally in `~/.muse`:

- queue: `~/.muse/muse.db`
- journal: `~/.muse/journal/YYYY/MM/YYYY-MM-DD.jsonl`
- agent run evidence: `~/.muse/agent/runs/RUN_ID.jsonl`

Interactive session activities are process-local and are not written to this
directory. Switching between simple and workspace views preserves them;
exiting `muse` discards them.

You can override the location:

```bash
muse --data-dir PATH
```

### Storage failures and recovery

Normal commands never delete, reset, replace, or repair an incompatible or
corrupt queue database. They fail with an actionable error and preserve
`muse.db` plus its SQLite sidecars. museCLI currently creates no automatic
backup and provides no destructive reset command.

When a journal contains malformed lines, valid entries remain visible with a
warning containing safe line numbers; malformed contents are not printed and
the file is not rewritten. See [Local-data recovery](docs/recovery.md) before
moving queue files or handling degraded journal evidence.

---

## muse-code evidence

Discover and inspect saved local coding-agent workflows:

```bash
muse-code list
muse-code list --data-dir PATH
muse-code inspect RUN_ID
muse-code inspect RUN_ID --data-dir PATH
```

The read-only list shows start time, concise intent, saved status, and
recomputed trace-control status without exposing context or tool details.
`inspect` shows the selected run's intent, gathered-context references,
proposal, permission decisions, actions, verification, evaluation, and result.
Run evidence stays local under `~/.muse/agent/runs`.

`muse-code` does not yet include a model provider or built-in code tools. See
[`docs/muse-code.md`](docs/muse-code.md) for the current boundaries and privacy
notes.

---

## notes

museCLI keeps things intentionally small.

It is not a full note system or task manager.  
It is a simple loop for capturing, deciding, focusing, and reflecting.

The goal is to reduce noise, not organise everything.
