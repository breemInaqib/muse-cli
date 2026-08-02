"""Plain interactive presentation and presentation coordinator for museCLI."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from typing import TYPE_CHECKING, Optional

from .session import (
    Activity,
    ActivityKind,
    Presentation,
    PresentationResult,
    SessionCommand,
    SessionController,
)

if TYPE_CHECKING:
    from .agent.audit import JsonlTraceStore
    from .workflow_index import WorkflowIndexEntry

Reader = Callable[[str], str]
Writer = Callable[[str], None]
WorkspaceRunner = Callable[[SessionController], PresentationResult]

_PROMPT = "› "
_HELP_LINES = (
    "commands",
    "  /help          show these commands",
    "  /context       show selected context",
    "  /plan          show the current plan",
    "  /permissions   show capability boundaries",
    "  /runs          list saved agent runs",
    "  /sources       show selected sources",
    "  /workspace     open the full workspace",
    "  /simple        stay in the simple view",
    "  /exit          exit muse",
)


def run_application(
    controller: SessionController,
    *,
    initial_presentation: Presentation = Presentation.SIMPLE,
    home_lines: Iterable[str] = (),
    reader: Reader = input,
    writer: Writer = print,
    workspace_runner: Optional[WorkspaceRunner] = None,  # noqa: UP045
) -> int:
    """Run simple and workspace presentations over one shared session."""
    presentation = initial_presentation
    first_presentation = True
    rendered_home = False

    while presentation is not Presentation.EXIT:
        if presentation is Presentation.SIMPLE:
            initial_simple = first_presentation and not rendered_home
            result = run_simple(
                controller,
                home_lines=home_lines if initial_simple else (),
                resumed=not initial_simple,
                reader=reader,
                writer=writer,
            )
            rendered_home = True
        else:
            runner = workspace_runner or _run_workspace
            try:
                result = runner(controller)
            except KeyboardInterrupt:
                return 130

        first_presentation = False
        presentation = result.presentation
        if presentation is Presentation.EXIT:
            return result.exit_code

    return 0


def run_simple(
    controller: SessionController,
    *,
    home_lines: Iterable[str] = (),
    resumed: bool = False,
    reader: Reader = input,
    writer: Writer = print,
) -> PresentationResult:
    """Run the colour-free line-oriented presentation until it requests a switch."""
    if resumed:
        _write_lines(writer, _resume_lines(controller))
    else:
        _write_lines(writer, _startup_lines(controller, home_lines))

    while True:
        try:
            raw = reader(_PROMPT)
        except EOFError:
            return PresentationResult(Presentation.EXIT, exit_code=0)
        except KeyboardInterrupt:
            return PresentationResult(Presentation.EXIT, exit_code=130)

        text = raw.strip()
        if not text:
            continue
        if text.startswith("/"):
            result = _handle_command(
                text,
                controller=controller,
                writer=writer,
            )
            if result is not None:
                return result
            continue
        if text.startswith("!"):
            writer("error: shell execution is unavailable")
            continue

        try:
            activities = controller.submit(text)
        except ValueError as exc:
            writer(f"error: {exc}")
            continue
        _write_lines(writer, render_activities(activities))


def render_activities(activities: Iterable[Activity]) -> list[str]:
    """Render display-safe activities without relying on colour."""
    lines: list[str] = []
    for activity in activities:
        lines.append(
            f"{activity.sequence}. {activity.kind.value} · "
            f"{activity.status.value}: {activity.summary}"
        )
        lines.extend(f"   {detail}" for detail in activity.display_details)
    return lines


def _handle_command(
    text: str,
    *,
    controller: SessionController,
    writer: Writer,
) -> PresentationResult | None:
    dispatch = controller.dispatch_command(text)
    if dispatch.error is not None:
        writer(dispatch.error)
        return None
    command = dispatch.command
    assert command is not None

    if command is SessionCommand.HELP:
        _write_lines(writer, _HELP_LINES)
    elif command is SessionCommand.CONTEXT:
        _write_lines(
            writer,
            _activity_section(
                "context",
                controller.activities_for(ActivityKind.CONTEXT),
                empty="none selected",
            ),
        )
    elif command is SessionCommand.PLAN:
        _write_lines(writer, _plan_lines(controller))
    elif command is SessionCommand.PERMISSIONS:
        _write_lines(
            writer,
            ("permissions", *(f"  {line}" for line in controller.capability_boundaries())),
        )
    elif command is SessionCommand.RUNS:
        _write_lines(writer, _run_lines(controller))
    elif command is SessionCommand.SOURCES:
        _write_lines(writer, ("sources", "  none selected"))
    elif command is SessionCommand.WORKSPACE:
        return PresentationResult(Presentation.WORKSPACE)
    elif command is SessionCommand.SIMPLE:
        writer("already in simple view")
    elif command is SessionCommand.EXIT:
        return PresentationResult(Presentation.EXIT)
    return None


def _startup_lines(
    controller: SessionController,
    home_lines: Iterable[str],
) -> list[str]:
    lines = list(home_lines)
    if lines:
        lines.append("")
    lines.extend(
        (
            "muse · local · demo",
            f"  session: {_short_session_id(controller.state.session_id)}",
            "  model: none · tools: off · network: off",
        )
    )
    return lines


def _resume_lines(controller: SessionController) -> list[str]:
    lines = [
        (
            "muse · resumed · "
            f"session: {_short_session_id(controller.state.session_id)} · "
            f"activities: {len(controller.state.activities)}"
        )
    ]
    latest = controller.latest_result()
    if latest is not None:
        lines.append(f"  latest: {latest.summary}")
    return lines


def _plan_lines(controller: SessionController) -> list[str]:
    if not controller.state.current_plan:
        return ["plan", "  none"]
    return [
        "plan",
        *(
            f"  {index}. {step}"
            for index, step in enumerate(controller.state.current_plan, start=1)
        ),
    ]


def _activity_section(
    title: str,
    activities: Iterable[Activity],
    *,
    empty: str,
) -> list[str]:
    selected = list(activities)
    if not selected:
        return [title, f"  {empty}"]
    latest = selected[-1]
    return [
        title,
        f"  {latest.status.value}: {latest.summary}",
        *(f"    {detail}" for detail in latest.display_details),
    ]


def _run_lines(controller: SessionController) -> list[str]:
    from .agent.audit import JsonlTraceStore

    store = JsonlTraceStore(controller.config.data_dir / "agent" / "runs")
    try:
        lines = render_workflow_index(load_workflow_index(store))
    except OSError:
        return ["error: could not list run evidence"]
    return [
        *lines,
        "",
        "inspect a run: muse-code inspect RUN_ID",
        "open workspace: /workspace",
    ]


def load_workflow_index(store: JsonlTraceStore) -> list[WorkflowIndexEntry]:
    """Load the historical index only after an explicit ``/runs`` command."""
    from .workflow_index import load_workflow_index as load

    return load(store)


def render_workflow_index(entries: Sequence[WorkflowIndexEntry]) -> list[str]:
    """Render the historical index without importing it during startup."""
    from .workflow_index import render_workflow_index as render

    return render(entries)


def _short_session_id(session_id: str) -> str:
    return session_id[:8]


def _write_lines(writer: Writer, lines: Iterable[str]) -> None:
    for line in lines:
        writer(line)


def _run_workspace(controller: SessionController) -> PresentationResult:
    from .tui import run_workspace

    return run_workspace(controller)
