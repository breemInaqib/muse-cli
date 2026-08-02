from __future__ import annotations

import subprocess
import sys
from collections.abc import Iterable
from pathlib import Path

import pytest

from musecli.config import AppConfig
from musecli.interactive import run_application, run_simple
from musecli.session import Presentation, PresentationResult, SessionController


class ScriptedReader:
    def __init__(self, values: Iterable[str | BaseException]) -> None:
        self._values = iter(values)
        self.prompts: list[str] = []

    def __call__(self, prompt: str) -> str:
        self.prompts.append(prompt)
        value = next(self._values)
        if isinstance(value, BaseException):
            raise value
        return value


def _controller(tmp_path: Path) -> SessionController:
    return SessionController(
        AppConfig.defaults(base_dir=tmp_path),
        session_id="session-1234567890",
    )


def test_simple_view_renders_exact_honest_demonstration(tmp_path: Path) -> None:
    controller = _controller(tmp_path)
    reader = ScriptedReader(("Fix the parser", "/exit"))
    output: list[str] = []

    result = run_simple(
        controller,
        home_lines=("museCLI", "", "  inbox: 0"),
        reader=reader,
        writer=output.append,
    )

    assert result == PresentationResult(Presentation.EXIT, exit_code=0)
    assert reader.prompts == ["› ", "› "]
    assert output == [
        "museCLI",
        "",
        "  inbox: 0",
        "",
        "muse · local · demo",
        "  session: session-",
        "  model: none · tools: off · network: off",
        "1. intent · complete: Fix the parser",
        "   User-provided intent.",
        "2. plan · complete: Record the intent.",
        "   Expose it through both presentations.",
        "   Finish without external execution.",
        "3. context · skipped: No context was gathered.",
        "4. permission · skipped: No permission was requested or granted.",
        "5. tool · skipped: No tool, shell, network, or mutation ran.",
        "6. verification · skipped: There was no generated change to verify.",
        ("7. result · complete: Demonstration completed; the requested task was not executed."),
        "   No model, tools, permissions, network, or files were used.",
    ]


def test_simple_commands_are_explicit_and_do_not_create_activity(tmp_path: Path) -> None:
    controller = _controller(tmp_path)
    reader = ScriptedReader(
        (
            "",
            "/HELP",
            "/context",
            "/plan",
            "/permissions",
            "/sources",
            "/simple",
            "/unknown",
            "/plan extra",
            "!pwd",
            "/exit",
        )
    )
    output: list[str] = []

    result = run_simple(controller, reader=reader, writer=output.append)

    assert result == PresentationResult(Presentation.EXIT)
    assert controller.state.activities == []
    assert "commands" in output
    assert "context" in output
    assert "  none selected" in output
    assert "plan" in output
    assert "  none" in output
    assert "permissions" in output
    assert "  model execution: off" in output
    assert "  context retrieval: off" in output
    assert "  tool and shell execution: off" in output
    assert "  network access: off" in output
    assert "  file mutation: off" in output
    assert "sources" in output
    assert "already in simple view" in output
    assert "error: unknown command /unknown" in output
    assert "error: command does not accept arguments: /plan" in output
    assert "error: shell execution is unavailable" in output


def test_command_errors_do_not_emit_terminal_control_characters(tmp_path: Path) -> None:
    output: list[str] = []

    run_simple(
        _controller(tmp_path),
        reader=ScriptedReader(("/unknown\x1b[31m", "/exit")),
        writer=output.append,
    )

    assert "\x1b" not in "\n".join(output)


def test_plan_and_context_commands_reflect_shared_session_state(tmp_path: Path) -> None:
    controller = _controller(tmp_path)
    reader = ScriptedReader(("Review the parser", "/plan", "/context", "/exit"))
    output: list[str] = []

    run_simple(controller, reader=reader, writer=output.append)

    assert "  1. Record the intent." in output
    assert "  2. Expose it through both presentations." in output
    assert "  3. Finish without external execution." in output
    assert "  skipped: No context was gathered." in output


def test_runs_is_lazy_read_only_and_reuses_workflow_renderer(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    controller = _controller(tmp_path)
    reader = ScriptedReader(("/runs", "/exit"))
    output: list[str] = []
    calls = 0

    def load(_store) -> list[object]:
        nonlocal calls
        calls += 1
        return []

    monkeypatch.setattr("musecli.interactive.load_workflow_index", load)

    run_simple(controller, reader=reader, writer=output.append)

    assert calls == 1
    assert output[-6:] == [
        "muse-code runs",
        "",
        "  no saved runs",
        "",
        "inspect a run: muse-code inspect RUN_ID",
        "open workspace: /workspace",
    ]
    assert not (tmp_path / "agent").exists()


def test_saved_runs_are_not_loaded_during_simple_startup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    controller = _controller(tmp_path)

    def fail(_store) -> list[object]:
        raise AssertionError("run evidence must stay lazy")

    monkeypatch.setattr("musecli.interactive.load_workflow_index", fail)

    result = run_simple(
        controller,
        reader=ScriptedReader(("/exit",)),
        writer=lambda _line: None,
    )

    assert result == PresentationResult(Presentation.EXIT)


def test_runs_reports_a_stable_read_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail(_store) -> list[object]:
        raise OSError("private path must not be exposed")

    monkeypatch.setattr("musecli.interactive.load_workflow_index", fail)
    output: list[str] = []

    run_simple(
        _controller(tmp_path),
        reader=ScriptedReader(("/runs", "/exit")),
        writer=output.append,
    )

    assert "error: could not list run evidence" in output
    assert "private path" not in "\n".join(output)


def test_switching_presentations_reuses_controller_without_duplicate_submission(
    tmp_path: Path,
) -> None:
    controller = _controller(tmp_path)
    reader = ScriptedReader(("Fix parser", "/workspace", "/exit"))
    output: list[str] = []
    workspace_calls: list[SessionController] = []

    def run_workspace(active: SessionController) -> PresentationResult:
        workspace_calls.append(active)
        assert len(active.state.activities) == 7
        return PresentationResult(Presentation.SIMPLE)

    exit_code = run_application(
        controller,
        home_lines=("home",),
        reader=reader,
        writer=output.append,
        workspace_runner=run_workspace,
    )

    assert exit_code == 0
    assert workspace_calls == [controller]
    assert len(controller.state.activities) == 7
    assert output.count("home") == 1
    assert output.count("muse · local · demo") == 1
    assert "muse · resumed · session: session- · activities: 7" in output
    assert "  latest: Demonstration completed; the requested task was not executed." in output


def test_starting_in_workspace_resumes_simple_without_replaying_home(tmp_path: Path) -> None:
    controller = _controller(tmp_path)
    output: list[str] = []

    exit_code = run_application(
        controller,
        initial_presentation=Presentation.WORKSPACE,
        home_lines=("must not be shown",),
        reader=ScriptedReader(("/exit",)),
        writer=output.append,
        workspace_runner=lambda _controller: PresentationResult(Presentation.SIMPLE),
    )

    assert exit_code == 0
    assert "must not be shown" not in output
    assert output == ["muse · resumed · session: session- · activities: 0"]


def test_simple_session_does_not_import_textual_presentation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delitem(sys.modules, "musecli.tui", raising=False)

    exit_code = run_application(
        _controller(tmp_path),
        reader=ScriptedReader(("/exit",)),
        writer=lambda _line: None,
    )

    assert exit_code == 0
    assert "musecli.tui" not in sys.modules


def test_simple_import_defers_historical_evidence_modules() -> None:
    root = Path(__file__).parents[1]
    code = """
import sys
import musecli.interactive

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


def test_workspace_keyboard_interrupt_exits_130(tmp_path: Path) -> None:
    def interrupt(_controller: SessionController) -> PresentationResult:
        raise KeyboardInterrupt

    exit_code = run_application(
        _controller(tmp_path),
        initial_presentation=Presentation.WORKSPACE,
        workspace_runner=interrupt,
    )

    assert exit_code == 130


@pytest.mark.parametrize(
    ("failure", "exit_code"),
    [
        (EOFError(), 0),
        (KeyboardInterrupt(), 130),
    ],
)
def test_simple_input_exit_conditions(
    tmp_path: Path,
    failure: BaseException,
    exit_code: int,
) -> None:
    result = run_simple(
        _controller(tmp_path),
        reader=ScriptedReader((failure,)),
        writer=lambda _line: None,
    )

    assert result == PresentationResult(Presentation.EXIT, exit_code=exit_code)
