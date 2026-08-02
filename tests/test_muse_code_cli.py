from __future__ import annotations

import os
from pathlib import Path

import pytest
from typer.testing import CliRunner

from musecli.agent.audit import JsonlTraceStore
from musecli.code_cli import app


def _store(base: Path) -> JsonlTraceStore:
    return JsonlTraceStore(base / "agent" / "runs")


def _record_verified_run(base: Path) -> None:
    store = _store(base)
    store.record(
        "run-1",
        "run_started",
        {
            "objective": "Fix the parser",
            "specification": "Invalid input returns exit code 2.",
            "specification_digest": "spec123",
        },
    )
    store.record(
        "run-1",
        "context_selected",
        {
            "items": [
                {
                    "reference": "musecli/cli.py",
                    "kind": "file",
                    "digest": "context123",
                }
            ]
        },
    )
    store.record(
        "run-1",
        "proposal_created",
        {
            "summary": "Change the parser and run its tests.",
            "response": "One file needs a bounded edit.",
            "tool_calls": [
                {
                    "call_id": "call-1",
                    "tool_name": "write_file",
                    "arguments": {"path": "musecli/cli.py"},
                    "reason": "Implement the specified error behaviour.",
                }
            ],
        },
    )
    store.record(
        "run-1",
        "permission_decided",
        {
            "call_id": "call-1",
            "tool_name": "write_file",
            "allowed": True,
            "required": ["workspace.write"],
            "granted": ["workspace.write"],
            "reason": "all required capabilities explicitly granted",
        },
    )
    store.record(
        "run-1",
        "tool_started",
        {
            "call_id": "call-1",
            "tool_name": "write_file",
            "arguments": {"path": "musecli/cli.py"},
            "reason": "Implement the specified error behaviour.",
        },
    )
    store.record(
        "run-1",
        "tool_finished",
        {
            "call_id": "call-1",
            "tool_name": "write_file",
            "success": True,
            "change": "changed",
            "summary": "updated parser",
            "evidence": ["musecli/cli.py: sha256:file123"],
        },
    )
    store.record(
        "run-1",
        "verification_finished",
        {
            "name": "pytest",
            "passed": True,
            "summary": "35 tests passed",
            "evidence": ["python -m pytest: exit 0"],
        },
    )
    store.record(
        "run-1",
        "run_evaluated",
        {
            "passed": True,
            "checks": [
                {
                    "name": "permission_coverage",
                    "passed": True,
                    "detail": "every proposed call has one permission decision",
                }
            ],
        },
    )
    store.record("run-1", "run_completed", {"status": "verified"})


def test_help_exposes_only_read_only_evidence_commands() -> None:
    runner = CliRunner()

    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0, result.output
    assert "list" in result.output
    assert "inspect" in result.output
    assert "run" not in [
        line.strip().split()[0]
        for line in result.output.splitlines()
        if line.startswith("  ") and line.strip()
    ]


def test_inspect_renders_a_complete_workflow(tmp_path: Path) -> None:
    _record_verified_run(tmp_path)
    runner = CliRunner()

    result = runner.invoke(
        app,
        ["inspect", "run-1", "--data-dir", str(tmp_path)],
    )

    assert result.exit_code == 0, result.output
    assert result.output == (
        "muse-code\n"
        "  run: run-1\n"
        "  status: verified\n"
        "\n"
        "intent\n"
        "  objective: Fix the parser\n"
        "  specification: Invalid input returns exit code 2.\n"
        "  specification digest: sha256:spec123\n"
        "\n"
        "context\n"
        "  - musecli/cli.py (file)\n"
        "    digest: sha256:context123\n"
        "\n"
        "plan\n"
        "  summary: Change the parser and run its tests.\n"
        "  response: One file needs a bounded edit.\n"
        "  calls:\n"
        "    - write_file [call-1]\n"
        "      why: Implement the specified error behaviour.\n"
        '      arguments: {"path":"musecli/cli.py"}\n'
        "\n"
        "permissions\n"
        "  - allowed write_file [call-1]\n"
        "    required: workspace.write\n"
        "    granted: workspace.write\n"
        "    reason: all required capabilities explicitly granted\n"
        "\n"
        "actions\n"
        "  - success changed write_file [call-1]\n"
        "    summary: updated parser\n"
        "    evidence: musecli/cli.py: sha256:file123\n"
        "\n"
        "verification\n"
        "  - pass pytest: 35 tests passed\n"
        "    evidence: python -m pytest: exit 0\n"
        "\n"
        "evaluation\n"
        "  - pass ordered_trace: event sequence is contiguous\n"
        "  - pass permission_coverage: every proposed call has one permission decision\n"
        "  - pass permission_preflight: all permission decisions preceded execution\n"
        "  - pass execution_coverage: every allowed call finished or was explicitly skipped\n"
        "  - pass verification_boundary: verification ran after execution\n"
        "  - pass completion_claim: verified status is supported by recorded evidence\n"
        "\n"
        "result\n"
        "  verified\n"
        "  trace controls: pass\n"
    )


def test_inspect_reports_missing_run_without_creating_storage(tmp_path: Path) -> None:
    runner = CliRunner()

    result = runner.invoke(
        app,
        ["inspect", "missing", "--data-dir", str(tmp_path)],
    )

    assert result.exit_code == 1
    assert result.output == "error: run not found: missing\n"
    assert not (tmp_path / "agent").exists()


def test_inspect_rejects_unsafe_run_id(tmp_path: Path) -> None:
    runner = CliRunner()

    result = runner.invoke(
        app,
        ["inspect", "../private", "--data-dir", str(tmp_path)],
    )

    assert result.exit_code == 1
    assert result.output == "error: invalid run id\n"


def test_inspect_fails_closed_for_malformed_evidence(tmp_path: Path) -> None:
    path = _store(tmp_path).path_for("broken")
    path.parent.mkdir(parents=True)
    path.write_text("not-json\n", encoding="utf-8")
    runner = CliRunner()

    result = runner.invoke(
        app,
        ["inspect", "broken", "--data-dir", str(tmp_path)],
    )

    assert result.exit_code == 1
    assert result.output == "error: could not read run evidence\n"


@pytest.mark.skipif(os.name == "nt", reason="POSIX file modes are unavailable on Windows")
def test_trace_files_are_private(tmp_path: Path) -> None:
    _record_verified_run(tmp_path)

    mode = os.stat(_store(tmp_path).path_for("run-1")).st_mode & 0o777

    assert mode == 0o600


def test_inspect_flags_an_unsupported_verified_claim(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.record(
        "unsafe",
        "proposal_created",
        {
            "summary": "claim success without controls",
            "tool_calls": [
                {
                    "call_id": "call-1",
                    "tool_name": "write_file",
                }
            ],
        },
    )
    store.record("unsafe", "run_completed", {"status": "verified"})
    runner = CliRunner()

    result = runner.invoke(
        app,
        ["inspect", "unsafe", "--data-dir", str(tmp_path)],
    )

    assert result.exit_code == 0, result.output
    assert "fail permission_coverage" in result.output
    assert "fail completion_claim" in result.output
    assert result.output.endswith("  verified\n  trace controls: fail\n")
