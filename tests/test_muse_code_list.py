from __future__ import annotations

from datetime import datetime
from importlib.metadata import distribution
from pathlib import Path

from typer.testing import CliRunner

from musecli.agent.audit import JsonlTraceStore
from musecli.code_cli import app
from musecli.workflow_index import (
    load_workflow_index,
    render_workflow_index,
    summarize_workflow,
)


def _store(base: Path, timestamp: str = "2026-07-27T15:00:00Z") -> JsonlTraceStore:
    instant = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    return JsonlTraceStore(base / "agent" / "runs", clock=lambda: instant)


def _record_verified_run(
    base: Path,
    run_id: str = "run-1",
    *,
    timestamp: str = "2026-07-27T15:00:00Z",
    objective: str = "Fix the parser",
) -> None:
    store = _store(base, timestamp)
    store.record(
        run_id,
        "run_started",
        {
            "objective": objective,
            "specification": "PRIVATE acceptance specification",
        },
    )
    store.record(
        run_id,
        "context_selected",
        {
            "items": [
                {
                    "reference": "private/path.py",
                    "kind": "file",
                    "digest": "private-digest",
                    "content": "PRIVATE retrieved context",
                }
            ]
        },
    )
    store.record(
        run_id,
        "proposal_created",
        {
            "summary": "PRIVATE proposal summary",
            "response": "PRIVATE model response",
            "tool_calls": [],
            "arguments": {"token": "PRIVATE tool argument"},
        },
    )
    store.record(
        run_id,
        "verification_finished",
        {
            "name": "pytest",
            "passed": True,
            "summary": "tests passed",
            "evidence": ["PRIVATE verification evidence"],
        },
    )
    store.record(run_id, "run_evaluated", {"passed": True})
    store.record(run_id, "run_completed", {"status": "verified"})


def _record_rejected_run(
    base: Path,
    run_id: str,
    *,
    timestamp: str,
    objective: str,
) -> None:
    store = _store(base, timestamp)
    store.record(run_id, "run_started", {"objective": objective})
    store.record(run_id, "context_selected", {"items": []})
    store.record(
        run_id,
        "proposal_created",
        {
            "summary": "Write a file",
            "tool_calls": [{"call_id": "call-1", "tool_name": "write_file"}],
        },
    )
    store.record(
        run_id,
        "permission_decided",
        {
            "call_id": "call-1",
            "tool_name": "write_file",
            "allowed": False,
        },
    )
    store.record(run_id, "run_evaluated", {"passed": True})
    store.record(run_id, "run_completed", {"status": "rejected"})


def _record_failed_run(
    base: Path,
    run_id: str,
    *,
    timestamp: str,
    objective: str,
) -> None:
    store = _store(base, timestamp)
    store.record(run_id, "run_started", {"objective": objective})
    store.record(run_id, "context_selected", {"items": []})
    store.record(
        run_id,
        "proposal_created",
        {"summary": "Prepare a proposal", "tool_calls": []},
    )
    store.record(run_id, "run_failed", {"reason": "runner failed"})
    store.record(run_id, "run_evaluated", {"passed": True})
    store.record(run_id, "run_completed", {"status": "failed"})


def _invoke_list(data_dir: Path) -> object:
    return CliRunner().invoke(app, ["list", "--data-dir", str(data_dir)])


def test_list_reports_empty_state_without_creating_run_directory(tmp_path: Path) -> None:
    result = _invoke_list(tmp_path)

    assert result.exit_code == 0, result.output
    assert result.output == "muse-code runs\n\n  no saved runs\n"
    assert not (tmp_path / "agent").exists()


def test_list_reports_empty_run_directory(tmp_path: Path) -> None:
    runs = tmp_path / "agent" / "runs"
    runs.mkdir(parents=True)

    result = _invoke_list(tmp_path)

    assert result.exit_code == 0, result.output
    assert result.output == "muse-code runs\n\n  no saved runs\n"


def test_list_renders_one_verified_run_with_exact_output(tmp_path: Path) -> None:
    _record_verified_run(tmp_path)

    result = _invoke_list(tmp_path)

    assert result.exit_code == 0, result.output
    assert result.output == (
        "muse-code runs\n"
        "\n"
        "2026-07-27T15:00:00Z  saved: verified  controls: pass\n"
        "  run: run-1\n"
        "  intent: Fix the parser\n"
    )


def test_list_uses_recorded_start_time_newest_first_with_stable_fallback(
    tmp_path: Path,
) -> None:
    _record_verified_run(
        tmp_path,
        "older",
        timestamp="2026-07-25T09:00:00Z",
        objective="Older run",
    )
    _record_rejected_run(
        tmp_path,
        "newer",
        timestamp="2026-07-27T09:00:00Z",
        objective="Newer run",
    )
    runs = tmp_path / "agent" / "runs"
    (runs / "z-broken.jsonl").write_text("not-json\n", encoding="utf-8")
    (runs / "a-empty.jsonl").write_text("", encoding="utf-8")

    entries = load_workflow_index(_store(tmp_path))

    assert [entry.lookup_id for entry in entries] == [
        "newer",
        "older",
        "a-empty",
        "z-broken",
    ]


def test_list_renders_supported_rejected_and_failed_runs(tmp_path: Path) -> None:
    _record_rejected_run(
        tmp_path,
        "rejected",
        timestamp="2026-07-27T11:00:00Z",
        objective="Attempt restricted edit",
    )
    _record_failed_run(
        tmp_path,
        "failed",
        timestamp="2026-07-27T12:00:00Z",
        objective="Ask unavailable runner",
    )

    result = _invoke_list(tmp_path)

    assert result.exit_code == 0, result.output
    assert (
        "2026-07-27T12:00:00Z  saved: failed  controls: pass\n"
        "  run: failed\n"
        "  intent: Ask unavailable runner"
    ) in result.output
    assert (
        "2026-07-27T11:00:00Z  saved: rejected  controls: pass\n"
        "  run: rejected\n"
        "  intent: Attempt restricted edit"
    ) in result.output


def test_list_flags_verified_claim_without_supporting_controls(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.record("contradictory", "run_started", {"objective": "Claim success"})
    store.record(
        "contradictory",
        "proposal_created",
        {
            "summary": "Unsupported proposal",
            "tool_calls": [{"call_id": "call-1", "tool_name": "write_file"}],
        },
    )
    store.record("contradictory", "run_evaluated", {"passed": True})
    store.record("contradictory", "run_completed", {"status": "verified"})

    result = _invoke_list(tmp_path)

    assert result.exit_code == 0, result.output
    assert "saved: verified  controls: fail" in result.output
    assert "issue: verified claim is not supported by trace controls" in result.output


def test_list_degrades_malformed_jsonl_without_exposing_raw_content(
    tmp_path: Path,
) -> None:
    path = _store(tmp_path).path_for("broken")
    path.parent.mkdir(parents=True)
    path.write_text('{"secret":"PRIVATE malformed content"}\n', encoding="utf-8")

    result = _invoke_list(tmp_path)

    assert result.exit_code == 0, result.output
    assert result.output == (
        "muse-code runs\n"
        "\n"
        "unknown  saved: unreadable  controls: unavailable\n"
        "  run: broken\n"
        "  intent: unavailable\n"
        "  issue: malformed evidence\n"
    )
    assert "PRIVATE" not in result.output


def test_list_treats_malformed_timestamp_as_unreadable_fallback(
    tmp_path: Path,
) -> None:
    _record_verified_run(
        tmp_path,
        "valid",
        timestamp="2026-07-27T15:00:00Z",
        objective="Valid run",
    )
    valid_path = _store(tmp_path).path_for("valid")
    malformed_path = valid_path.with_name("malformed-time.jsonl")
    malformed_path.write_text(
        valid_path.read_text(encoding="utf-8").replace(
            "2026-07-27T15:00:00Z",
            "not-a-timestamp",
        ),
        encoding="utf-8",
    )

    entries = load_workflow_index(_store(tmp_path))

    assert [entry.lookup_id for entry in entries] == ["valid", "malformed-time"]
    assert entries[1].saved_status == "unreadable"
    assert entries[1].issues == ("malformed evidence",)


def test_list_marks_missing_required_events_as_incomplete(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.record("incomplete", "run_started", {"objective": "Only started"})

    result = _invoke_list(tmp_path)

    assert result.exit_code == 0, result.output
    assert "saved: incomplete  controls: fail" in result.output
    assert "issue: missing run_completed" in result.output


def test_list_uses_filename_as_inspect_key_and_reports_recorded_id_mismatch(
    tmp_path: Path,
) -> None:
    _record_verified_run(tmp_path, "recorded")
    source = _store(tmp_path).path_for("recorded")
    source.rename(source.with_name("lookup.jsonl"))

    result = _invoke_list(tmp_path)

    assert result.exit_code == 0, result.output
    assert "saved: verified  controls: fail" in result.output
    assert "  run: lookup\n" in result.output
    assert "  issue: filename/recorded run ID mismatch (recorded: recorded)\n" in result.output

    inspect_result = CliRunner().invoke(
        app,
        ["inspect", "lookup", "--data-dir", str(tmp_path)],
    )
    assert inspect_result.exit_code == 1
    assert inspect_result.output == "error: could not read run evidence\n"


def test_list_truncates_long_objective_deterministically(tmp_path: Path) -> None:
    _record_verified_run(tmp_path, objective="x" * 80)

    entry = load_workflow_index(_store(tmp_path))[0]

    assert entry.objective == ("x" * 57) + "..."
    assert len(entry.objective) == 60


def test_list_keeps_valid_run_when_another_run_is_malformed(tmp_path: Path) -> None:
    _record_verified_run(tmp_path, "valid")
    broken = _store(tmp_path).path_for("broken")
    broken.write_text("not-json\n", encoding="utf-8")

    result = _invoke_list(tmp_path)

    assert result.exit_code == 0, result.output
    assert result.output.index("  run: valid\n") < result.output.index("  run: broken\n")
    assert "saved: verified  controls: pass" in result.output
    assert "saved: unreadable  controls: unavailable" in result.output


def test_list_uses_custom_data_directory_only(tmp_path: Path) -> None:
    custom = tmp_path / "custom"
    other = tmp_path / "other"
    _record_verified_run(custom, "custom-run")
    _record_verified_run(other, "other-run")

    result = _invoke_list(custom)

    assert result.exit_code == 0, result.output
    assert "  run: custom-run\n" in result.output
    assert "other-run" not in result.output


def test_list_without_override_uses_loaded_default(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _record_verified_run(tmp_path, "default-run")

    def load_test_config(base_dir=None):
        from musecli.config import AppConfig

        assert base_dir is None
        return AppConfig.defaults(tmp_path), False

    monkeypatch.setattr("musecli.code_cli.load_config", load_test_config)

    result = CliRunner().invoke(app, ["list"])

    assert result.exit_code == 0, result.output
    assert "  run: default-run\n" in result.output


def test_list_does_not_render_private_trace_fields(tmp_path: Path) -> None:
    _record_verified_run(tmp_path)

    rendered = "\n".join(render_workflow_index(load_workflow_index(_store(tmp_path))))

    assert "Fix the parser" in rendered
    assert "PRIVATE" not in rendered
    assert "private/path.py" not in rendered
    assert "private-digest" not in rendered


def test_summarize_workflow_marks_unreadable_evidence_without_partial_metadata(
    tmp_path: Path,
    monkeypatch,
) -> None:
    path = _store(tmp_path).path_for("unreadable")
    path.parent.mkdir(parents=True)
    path.touch()
    store = _store(tmp_path)

    def fail_read(_path):
        raise OSError("permission denied")

    monkeypatch.setattr(store, "read_path", fail_read)

    entry = load_workflow_index(store)[0]

    assert entry.saved_status == "unreadable"
    assert entry.controls == "unavailable"
    assert entry.objective == "unavailable"
    assert entry.issues == ("unreadable evidence",)


def test_summary_and_renderer_are_independently_testable(tmp_path: Path) -> None:
    _record_verified_run(tmp_path)
    store = _store(tmp_path)
    path = store.path_for("run-1")

    entry = summarize_workflow(path, store.read("run-1"))

    assert render_workflow_index([entry])[-2:] == [
        "  run: run-1",
        "  intent: Fix the parser",
    ]


def test_distribution_entry_point_supports_list_in_process(tmp_path: Path) -> None:
    _record_verified_run(tmp_path, "installed-run")
    entry_point = next(
        entry
        for entry in distribution("musecli").entry_points
        if entry.group == "console_scripts" and entry.name == "muse-code"
    )

    result = CliRunner().invoke(
        entry_point.load(),
        ["list", "--data-dir", str(tmp_path)],
    )

    assert result.exit_code == 0, result.output
    assert "  run: installed-run\n" in result.output
    assert "saved: verified  controls: pass" in result.output
