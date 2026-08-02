# Contributing

## Environment

```bash
uv sync --locked --extra dev
```

This creates the locked development environment used by the source-checkout
commands in the README. Without `uv`, create and activate `.venv` using the
README's Unix/macOS or Windows instructions, then run
`python -m pip install -e ".[dev]"`.

## Verification

On Unix and macOS, run the repository smoke checks first:

```bash
./scripts/check.sh
```

Then run the explicit test, style, format, and build checks on every platform:

```bash
uv lock --check
uv run --locked --extra dev python -m pytest
uv run --locked --extra dev python -m ruff check .
uv run --locked --extra dev python -m ruff format --check .
uv run --locked --extra dev python -m build
uv run --locked --extra dev python scripts/verify_wheel.py dist/musecli-0.1.0-py3-none-any.whl
uv run --locked --extra dev python scripts/verify_sdist.py dist/musecli-0.1.0.tar.gz
```

On Windows, the full pytest command includes the supported headless Textual
workspace smoke tests. The pseudo-terminal startup measurement is Unix-only;
see `docs/workspace.md` for the platform boundary.

## Workflow

- Keep changes small and reversible.
- Add/update tests with behavior changes.
- Preserve deterministic CLI output for script-safe commands.
- Do not add telemetry or runtime network access.
- Keep the primary workflow coherent: capture, triage, retrieve/export, reflect.
- Treat compatibility commands as stable only when they are tested and documented.

## Versioning

- We use `0.x` semver.
- `0.x.y` patch: bug fixes.
- `0.(x+1).0` minor: new commands/options with compatibility notes.
