# Contributing

## Environment

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install --upgrade pip
python3 -m pip install -e ".[dev]"
```

## Checks

```bash
./scripts/check.sh
```

## Packaging Smoke Tests

```bash
python3 -m build
python3 -m pip install -e .
muse --help
```

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
