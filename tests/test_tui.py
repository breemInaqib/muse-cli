from __future__ import annotations

import asyncio
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import pytest
from textual.app import CommandPalette
from textual.widgets import Input, ListView, Static

from musecli.agent.audit import JsonlTraceStore
from musecli.config import AppConfig
from musecli.session import Presentation, PresentationResult, SessionController
from musecli.tui import RunItem, WorkspaceApp


def _controller(data_dir: Path, *, session_id: str = "session-12345678") -> SessionController:
    return SessionController(AppConfig.defaults(data_dir), session_id=session_id)


def _text(widget: Static) -> str:
    rendered = widget.render()
    return rendered.plain if hasattr(rendered, "plain") else str(rendered)


def _item_text(item: object) -> str:
    assert isinstance(item, RunItem)
    return _text(item.query_one(Static))


def _store(base: Path, timestamp: str = "2026-07-29T12:00:00Z") -> JsonlTraceStore:
    instant = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    return JsonlTraceStore(base / "agent" / "runs", clock=lambda: instant)


def _record_verified_run(base: Path, run_id: str = "valid") -> None:
    store = _store(base)
    store.record(
        run_id,
        "run_started",
        {
            "objective": "Fix the parser",
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


def _record_contradictory_run(base: Path) -> None:
    store = _store(base, "2026-07-29T13:00:00Z")
    store.record("contradictory", "run_started", {"objective": "Claim unsupported success"})
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


def test_workspace_mounts_without_discovering_runs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0

    def unexpected_load(store: JsonlTraceStore) -> list[object]:
        del store
        nonlocal calls
        calls += 1
        return []

    monkeypatch.setattr("musecli.tui.load_workflow_index", unexpected_load)
    controller = _controller(tmp_path)
    app = WorkspaceApp(controller)

    async def scenario() -> None:
        async with app.run_test(size=(120, 36)):
            header = _text(app.query_one("#workspace-header", Static))
            assert "session session-" in header
            assert "local · demo runner" in header
            assert "model off · tools off · network off" in header
            assert (
                app.query_one("#composer", Input).placeholder == "ask, direct, reference or command"
            )
            assert _text(app.query_one("#run-status", Static)) == (
                "Not loaded · enter /runs or use Ctrl+K."
            )
            assert app.query_one("#composer", Input).has_focus
            assert calls == 0
            assert not (tmp_path / "agent").exists()

    asyncio.run(scenario())


def test_workspace_import_defers_historical_evidence_modules() -> None:
    root = Path(__file__).parents[1]
    code = """
import sys
import musecli.tui

historical_modules = {
    "musecli.agent.audit",
    "musecli.workflow_index",
    "musecli.workflow_view",
}
loaded = historical_modules.intersection(sys.modules)
assert not loaded, sorted(loaded)
"""

    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr


def test_submission_uses_shared_controller_and_renders_honest_activity(
    tmp_path: Path,
) -> None:
    controller = _controller(tmp_path)
    state = controller.state
    app = WorkspaceApp(controller)

    async def scenario() -> None:
        async with app.run_test(size=(120, 36)) as pilot:
            composer = app.query_one("#composer", Input)
            composer.value = "Improve the parser"
            await pilot.press("enter")
            await pilot.pause()

            assert controller.state is state
            assert len(state.activities) == 7
            assert len(app.query_one("#activity-list", ListView).children) == 7
            timeline = "\n".join(
                _text(item.query_one(Static))
                for item in app.query_one("#activity-list", ListView).children
            )
            assert "intent · complete" in timeline
            assert "context · skipped" in timeline
            assert "permission · skipped" in timeline
            assert "tool · skipped" in timeline
            assert "verification · skipped" in timeline
            assert "result · complete" in timeline
            assert "requested task was not executed" in timeline
            detail = _text(app.query_one("#detail-content", Static))
            assert "No model, tools, permissions, network, or files were used." in detail

    asyncio.run(scenario())


def test_shell_syntax_and_unknown_command_fail_without_activity(
    tmp_path: Path,
) -> None:
    controller = _controller(tmp_path)
    app = WorkspaceApp(controller)

    async def scenario() -> None:
        async with app.run_test(size=(100, 30)) as pilot:
            composer = app.query_one("#composer", Input)
            composer.value = "!rm something"
            await pilot.press("enter")
            assert _text(app.query_one("#detail-content", Static)) == (
                "error: shell execution is unavailable"
            )
            assert controller.state.activities == []

            composer.value = "/unknown"
            await pilot.press("enter")
            assert _text(app.query_one("#detail-content", Static)) == (
                "error: unknown command /unknown"
            )
            assert controller.state.activities == []

            composer.value = "/help extra"
            await pilot.press("enter")
            assert _text(app.query_one("#detail-content", Static)) == (
                "error: command does not accept arguments: /help"
            )

            composer.value = "/permissions"
            await pilot.press("enter")
            boundaries = _text(app.query_one("#detail-content", Static))
            assert "model execution: off" in boundaries
            assert "context retrieval: off" in boundaries
            assert "tool and shell execution: off" in boundaries
            assert "network access: off" in boundaries
            assert "file mutation: off" in boundaries

            composer.value = "/unsafe\x1b[31m"
            await pilot.press("enter")
            reflected = _text(app.query_one("#detail-content", Static))
            assert reflected == "error: command does not accept arguments: /unsafe"
            assert "\x1b" not in reflected

    asyncio.run(scenario())


def test_simple_command_returns_same_session_without_resubmission(
    tmp_path: Path,
) -> None:
    controller = _controller(tmp_path)
    controller.submit("Keep this intent")
    activities = tuple(controller.state.activities)
    app = WorkspaceApp(controller)

    async def scenario() -> None:
        async with app.run_test(size=(100, 30)) as pilot:
            composer = app.query_one("#composer", Input)
            composer.value = "/simple"
            await pilot.press("enter")

    asyncio.run(scenario())

    assert app.return_value == PresentationResult(Presentation.SIMPLE)
    assert tuple(controller.state.activities) == activities


def test_interrupt_returns_130_without_false_cancellation(tmp_path: Path) -> None:
    controller = _controller(tmp_path)
    app = WorkspaceApp(controller)

    async def scenario() -> None:
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.press("ctrl+c")

    asyncio.run(scenario())

    assert app.return_value == PresentationResult(Presentation.EXIT, exit_code=130)
    assert controller.state.activities == []


def test_responsive_layout_and_narrow_run_view(tmp_path: Path) -> None:
    controller = _controller(tmp_path)
    app = WorkspaceApp(controller, trace_store=_store(tmp_path))

    async def scenario() -> None:
        async with app.run_test(size=(120, 36)) as pilot:
            runs = app.query_one("#runs-pane")
            activity = app.query_one("#activity-pane")
            detail = app.query_one("#detail-pane")
            assert app.screen.has_class("-wide")
            assert runs.display and activity.display and detail.display

            await pilot.resize_terminal(90, 30)
            assert app.screen.has_class("-medium")
            assert not runs.display
            assert activity.display and detail.display

            await pilot.resize_terminal(60, 18)
            assert app.screen.has_class("-narrow")
            assert not runs.display and activity.display and not detail.display

            composer = app.query_one("#composer", Input)
            composer.value = "/runs"
            await pilot.press("enter")
            await pilot.pause()
            assert app.screen.has_class("-runs-open")
            assert runs.display and not activity.display and not detail.display

            await pilot.press("escape")
            assert not app.screen.has_class("-runs-open")
            assert activity.display and not runs.display and not detail.display

    asyncio.run(scenario())


def test_keyboard_focus_navigation_opens_and_closes_activity_detail(tmp_path: Path) -> None:
    controller = _controller(tmp_path)
    controller.submit("Inspect keyboard navigation")
    app = WorkspaceApp(controller)

    async def scenario() -> None:
        async with app.run_test(size=(90, 30)) as pilot:
            composer = app.query_one("#composer", Input)
            activity_list = app.query_one("#activity-list", ListView)
            assert composer.has_focus

            await pilot.press("shift+tab")
            assert activity_list.has_focus
            await pilot.press("down", "enter")
            await pilot.pause()
            assert app.screen.has_class("-detail-open")
            assert "complete" in _text(app.query_one("#detail-content", Static))

            await pilot.press("escape")
            assert not app.screen.has_class("-detail-open")
            assert composer.has_focus

    asyncio.run(scenario())


def test_run_overview_is_private_and_malformed_evidence_remains_visible(
    tmp_path: Path,
) -> None:
    _record_verified_run(tmp_path)
    malformed = _store(tmp_path).path_for("broken")
    malformed.write_text('{"secret":"PRIVATE malformed content"}\n', encoding="utf-8")
    controller = _controller(tmp_path)
    app = WorkspaceApp(controller, trace_store=_store(tmp_path))

    async def scenario() -> None:
        async with app.run_test(size=(120, 36)) as pilot:
            composer = app.query_one("#composer", Input)
            composer.value = "/runs"
            await pilot.press("enter")
            await pilot.pause()

            run_list = app.query_one("#run-list", ListView)
            assert len(run_list.children) == 2
            overview = "\n".join(_item_text(item) for item in run_list.children)
            assert "Fix the parser" in overview
            assert "malformed evidence" in overview
            assert "PRIVATE acceptance specification" not in overview
            assert "PRIVATE retrieved context" not in overview
            assert "PRIVATE tool argument" not in overview
            assert "PRIVATE malformed content" not in overview

            run_list.index = 0
            run_list.focus()
            await pilot.press("enter")
            await pilot.pause()
            explicit_detail = _text(app.query_one("#detail-content", Static))
            assert explicit_detail.startswith("PRIVATE TRACE DETAIL — explicitly opened")
            assert "PRIVATE acceptance specification" in explicit_detail

    asyncio.run(scenario())


def test_incomplete_and_mismatched_run_evidence_remains_visible(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.record("incomplete", "run_started", {"objective": "Only started"})
    _record_verified_run(tmp_path, "recorded")
    recorded = store.path_for("recorded")
    recorded.rename(recorded.with_name("lookup.jsonl"))
    app = WorkspaceApp(_controller(tmp_path), trace_store=store)

    async def scenario() -> None:
        async with app.run_test(size=(120, 30)):
            await app.load_runs()
            rows = "\n".join(
                _item_text(item) for item in app.query_one("#run-list", ListView).children
            )
            assert "incomplete" in rows
            assert "saved: incomplete · controls: fail" in rows
            assert "missing run_completed" in rows
            assert "lookup" in rows
            assert "filename/recorded run ID mismatch (recorded: recorded)" in rows

    asyncio.run(scenario())


def test_contradictory_saved_success_is_visibly_recomputed(tmp_path: Path) -> None:
    _record_contradictory_run(tmp_path)
    controller = _controller(tmp_path)
    app = WorkspaceApp(controller, trace_store=_store(tmp_path))

    async def scenario() -> None:
        async with app.run_test(size=(120, 30)) as pilot:
            await app.load_runs()
            await pilot.pause()
            run_list = app.query_one("#run-list", ListView)
            assert len(run_list.children) == 1
            row = _item_text(run_list.children[0])
            assert "saved: verified · controls: fail" in row
            assert "verified claim is not supported by trace controls" in row

    asyncio.run(scenario())


def test_run_list_read_failure_degrades_without_exiting(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unavailable(store: JsonlTraceStore) -> list[object]:
        del store
        raise OSError("private operating-system detail")

    monkeypatch.setattr("musecli.tui.load_workflow_index", unavailable)
    app = WorkspaceApp(_controller(tmp_path))

    async def scenario() -> None:
        async with app.run_test(size=(120, 30)):
            await app.load_runs()
            assert _text(app.query_one("#run-status", Static)) == (
                "Could not list run evidence; no files were changed."
            )
            detail = _text(app.query_one("#detail-content", Static))
            assert detail == "saved runs\n\nunavailable — run evidence could not be read."
            assert "private operating-system detail" not in detail

    asyncio.run(scenario())


def test_run_inspection_failure_degrades_without_exiting(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _record_verified_run(tmp_path)

    def unavailable(self: WorkspaceApp, lookup_id: str) -> list[str]:
        del self, lookup_id
        raise OSError("private operating-system detail")

    monkeypatch.setattr(WorkspaceApp, "_read_workflow", unavailable)
    app = WorkspaceApp(_controller(tmp_path), trace_store=_store(tmp_path))

    async def scenario() -> None:
        async with app.run_test(size=(120, 30)) as pilot:
            await app.load_runs()
            run_list = app.query_one("#run-list", ListView)
            run_list.index = 0
            run_list.focus()
            await pilot.press("enter")
            await pilot.pause()
            detail = _text(app.query_one("#detail-content", Static))
            assert "detailed evidence unavailable" in detail
            assert "no evidence was repaired or inferred" in detail
            assert "private operating-system detail" not in detail

    asyncio.run(scenario())


def test_ctrl_k_opens_textual_command_palette(tmp_path: Path) -> None:
    app = WorkspaceApp(_controller(tmp_path))

    async def scenario() -> None:
        async with app.run_test(size=(100, 30)) as pilot:
            commands = list(app.get_system_commands(app.screen))
            assert [command.title for command in commands] == [
                "Simple view",
                "Runs",
                "Plan",
                "Permissions",
                "Help",
                "Exit",
            ]
            await pilot.press("ctrl+k")
            await pilot.pause()
            assert isinstance(app.screen, CommandPalette)

    asyncio.run(scenario())


def test_status_meaning_does_not_depend_on_colour(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("NO_COLOR", "1")
    controller = _controller(tmp_path)
    controller.submit("Show semantic labels")
    app = WorkspaceApp(controller)

    async def scenario() -> None:
        async with app.run_test(size=(60, 10)):
            assert app.no_color
            timeline = "\n".join(
                _text(item.query_one(Static))
                for item in app.query_one("#activity-list", ListView).children
            )
            assert "intent · complete" in timeline
            assert "context · skipped" in timeline
            assert "result · complete" in timeline
            composer = app.query_one("#composer", Input)
            assert composer.display
            assert composer.region.height > 0

    asyncio.run(scenario())
