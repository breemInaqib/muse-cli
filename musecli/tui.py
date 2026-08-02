"""Textual presentation for one shared, process-local muse session."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import TYPE_CHECKING

from rich.text import Text
from textual import on
from textual.app import App, ComposeResult, SystemCommand
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Input, ListItem, ListView, Static
from textual.worker import WorkerCancelled, WorkerFailed

from .session import (
    Activity,
    ActivityKind,
    Presentation,
    PresentationResult,
    SessionCommand,
    SessionController,
)
from .utils import iso_utc

if TYPE_CHECKING:
    from .agent.audit import JsonlTraceStore
    from .agent.contracts import TraceEvent
    from .workflow_index import WorkflowIndexEntry


class ActivityItem(ListItem):
    """Selectable, display-safe representation of one session activity."""

    def __init__(self, activity: Activity) -> None:
        self.activity = activity
        label = (
            f"{activity.sequence:02d}  {activity.kind.value} · {activity.status.value}\n"
            f"    {activity.summary}"
        )
        super().__init__(Static(Text(label), classes="list-label"))


class RunItem(ListItem):
    """Selectable privacy-bounded representation of one saved run."""

    def __init__(self, entry: WorkflowIndexEntry) -> None:
        self.entry = entry
        started = iso_utc(entry.started_at) if entry.started_at is not None else "unknown"
        issues = f"\n    issue: {'; '.join(entry.issues)}" if entry.issues else ""
        label = (
            f"{started}  {entry.lookup_id}\n"
            f"    {entry.objective}\n"
            f"    saved: {entry.saved_status} · controls: {entry.controls}"
            f"{issues}"
        )
        super().__init__(Static(Text(label), classes="list-label"))


class WorkspaceApp(App[PresentationResult]):
    """Full-screen view over a shared ``SessionController``."""

    TITLE = "muse"
    SUB_TITLE = "visible agentic workspace"
    HORIZONTAL_BREAKPOINTS = [
        (0, "-narrow"),
        (70, "-medium"),
        (110, "-wide"),
    ]
    COMMAND_PALETTE_BINDING = "ctrl+k"
    ESCAPE_TO_MINIMIZE = False
    BINDINGS = [
        Binding("question_mark", "help", "Help"),
        Binding("escape", "back", "Back", show=False),
        Binding("ctrl+c", "interrupt", show=False, priority=True),
    ]
    CSS = """
    Screen {
        background: $surface;
        color: $text;
    }

    #workspace-header {
        height: 3;
        padding: 1 2;
        background: $panel;
        border-bottom: solid $primary;
        text-style: bold;
    }

    #workspace-main {
        height: 1fr;
        layout: horizontal;
    }

    .pane {
        height: 1fr;
        border: solid $secondary;
        background: $surface;
    }

    .pane-title {
        height: 3;
        padding: 1 1;
        background: $panel;
        text-style: bold;
    }

    .pane-status {
        height: auto;
        min-height: 2;
        padding: 0 1 1 1;
        color: $text-muted;
    }

    #runs-pane {
        width: 32%;
        min-width: 28;
    }

    #activity-pane {
        width: 39%;
        min-width: 30;
    }

    #detail-pane {
        width: 1fr;
        padding: 0 1 1 1;
        overflow-y: auto;
    }

    #run-list, #activity-list {
        height: 1fr;
    }

    ListItem {
        height: auto;
        min-height: 3;
        padding: 0 1;
    }

    ListItem:focus, ListItem.--highlight {
        background: $boost;
    }

    .list-label {
        height: auto;
    }

    #detail-content {
        height: auto;
        padding: 0 1 1 1;
    }

    #composer {
        dock: bottom;
        height: 3;
        border: tall $primary;
        background: $panel;
    }

    Screen.-medium #runs-pane {
        display: none;
    }

    Screen.-medium #activity-pane {
        width: 48%;
    }

    Screen.-narrow #runs-pane,
    Screen.-narrow #detail-pane {
        display: none;
    }

    Screen.-narrow #activity-pane {
        width: 1fr;
        min-width: 1;
    }

    Screen.-medium.-runs-open #runs-pane,
    Screen.-narrow.-runs-open #runs-pane {
        display: block;
        width: 1fr;
        min-width: 1;
    }

    Screen.-medium.-runs-open #activity-pane,
    Screen.-medium.-runs-open #detail-pane,
    Screen.-narrow.-runs-open #activity-pane,
    Screen.-narrow.-runs-open #detail-pane {
        display: none;
    }

    Screen.-narrow.-detail-open #detail-pane,
    Screen.-medium.-detail-open #detail-pane {
        display: block;
        width: 1fr;
    }

    Screen.-narrow.-detail-open #activity-pane,
    Screen.-narrow.-detail-open #runs-pane,
    Screen.-medium.-detail-open #activity-pane,
    Screen.-medium.-detail-open #runs-pane {
        display: none;
    }
    """

    def __init__(
        self,
        controller: SessionController,
        *,
        trace_store: JsonlTraceStore | None = None,
    ) -> None:
        super().__init__()
        self.controller = controller
        self._trace_store = trace_store

    def compose(self) -> ComposeResult:
        session = self.controller.state.session_id[:8]
        yield Static(
            Text(
                f"muse · session {session} · local · demo runner · "
                "model off · tools off · network off"
            ),
            id="workspace-header",
        )
        with Horizontal(id="workspace-main"):
            with Vertical(classes="pane", id="runs-pane"):
                yield Static(Text("SAVED RUNS"), classes="pane-title")
                yield Static(
                    Text("Not loaded · enter /runs or use Ctrl+K."),
                    classes="pane-status",
                    id="run-status",
                )
                yield ListView(id="run-list")
            with Vertical(classes="pane", id="activity-pane"):
                yield Static(Text("ACTIVE WORK SESSION"), classes="pane-title")
                yield Static(
                    Text("No activity yet · enter an intent below."),
                    classes="pane-status",
                    id="activity-status",
                )
                yield ListView(id="activity-list")
            with Vertical(classes="pane", id="detail-pane"):
                yield Static(Text("CONTEXT / DETAIL"), classes="pane-title")
                yield Static(
                    Text(
                        "Select an activity or load saved runs.\n\n"
                        "No model, tools, network, or repository context are active."
                    ),
                    id="detail-content",
                )
        yield Input(
            placeholder="starting workspace…",
            id="composer",
        )

    async def on_mount(self) -> None:
        """Render existing shared state without loading historical evidence."""
        await self.refresh_activities()
        composer = self.query_one("#composer", Input)
        composer.focus()
        composer.placeholder = "ask, direct, reference or command"

    def get_system_commands(self, screen: Screen) -> Iterable[SystemCommand]:
        """Expose the small application vocabulary in Textual's palette."""
        del screen
        yield SystemCommand("Simple view", "Return to the simple terminal view", self.action_simple)
        yield SystemCommand("Runs", "Discover saved local run evidence", self.action_runs)
        yield SystemCommand("Plan", "Show the current process-local plan", self.action_plan)
        yield SystemCommand(
            "Permissions",
            "Show the disabled capability boundary",
            self.action_permissions,
        )
        yield SystemCommand("Help", "Show workspace commands and keys", self.action_help)
        yield SystemCommand("Exit", "End this process-local session", self.action_exit)

    async def refresh_activities(self) -> None:
        """Project the current shared activities into the timeline."""
        activity_list = self.query_one("#activity-list", ListView)
        await activity_list.clear()
        activities = tuple(self.controller.state.activities)
        if activities:
            await activity_list.extend(ActivityItem(activity) for activity in activities)
            self.query_one("#activity-status", Static).update(
                Text(f"{len(activities)} display-safe activities · newest last.")
            )
        else:
            self.query_one("#activity-status", Static).update(
                Text("No activity yet · enter an intent below.")
            )

    @on(Input.Submitted, "#composer")
    async def handle_submission(self, event: Input.Submitted) -> None:
        """Handle input without giving the presentation its own agent."""
        text = event.value.strip()
        event.input.value = ""
        if not text:
            event.input.focus()
            return
        if text.startswith("/"):
            await self._handle_command(text)
        else:
            try:
                created = self.controller.submit(text)
            except ValueError as exc:
                self._show_detail(f"error: {exc}")
            else:
                await self.refresh_activities()
                if created:
                    self._show_activity(created[-1])
        if self.is_running:
            event.input.focus()

    async def _handle_command(self, command: str) -> None:
        dispatch = self.controller.dispatch_command(command)
        if dispatch.error is not None:
            self._show_detail(dispatch.error)
            return
        normalized = dispatch.command
        assert normalized is not None
        if normalized is SessionCommand.SIMPLE:
            self.action_simple()
        elif normalized is SessionCommand.EXIT:
            self.action_exit()
        elif normalized is SessionCommand.WORKSPACE:
            self._show_detail("Already in workspace view.")
        elif normalized is SessionCommand.RUNS:
            await self.load_runs()
        elif normalized is SessionCommand.PLAN:
            self.action_plan()
        elif normalized is SessionCommand.CONTEXT:
            self._show_activity_group(ActivityKind.CONTEXT, "context")
        elif normalized is SessionCommand.PERMISSIONS:
            self.action_permissions()
        elif normalized is SessionCommand.SOURCES:
            self._show_detail("sources\n\nnone — no context or external sources were gathered.")
        elif normalized is SessionCommand.HELP:
            self.action_help()

    @on(ListView.Highlighted, "#activity-list")
    def show_highlighted_activity(self, event: ListView.Highlighted) -> None:
        if isinstance(event.item, ActivityItem):
            self._show_activity(event.item.activity)

    @on(ListView.Selected, "#activity-list")
    def open_activity(self, event: ListView.Selected) -> None:
        if isinstance(event.item, ActivityItem):
            self._show_activity(event.item.activity)
            self._open_detail_view()

    @on(ListView.Highlighted, "#run-list")
    def show_run_overview(self, event: ListView.Highlighted) -> None:
        if isinstance(event.item, RunItem):
            self._show_run_summary(event.item.entry)

    @on(ListView.Selected, "#run-list")
    async def inspect_run(self, event: ListView.Selected) -> None:
        if not isinstance(event.item, RunItem):
            return
        from .agent.audit import AuditLogError

        entry = event.item.entry
        self.query_one("#run-status", Static).update(Text(f"Reading {entry.lookup_id}…"))
        worker = self.run_worker(
            lambda: self._read_workflow(entry.lookup_id),
            thread=True,
            name="inspect-workflow",
            exclusive=True,
            exit_on_error=False,
        )
        try:
            lines = await worker.wait()
        except (AuditLogError, OSError, ValueError, WorkerCancelled, WorkerFailed):
            self._show_detail(
                "saved run detail\n\n"
                f"run: {entry.lookup_id}\n"
                "detailed evidence unavailable\n\n"
                "The overview remains visible; no evidence was repaired or inferred."
            )
            self.query_one("#run-status", Static).update(
                Text(f"{len(self.query_one('#run-list', ListView).children)} saved runs.")
            )
            self._open_detail_view()
            return
        self._show_detail("PRIVATE TRACE DETAIL — explicitly opened\n\n" + "\n".join(lines))
        self.query_one("#run-status", Static).update(Text(f"Opened {entry.lookup_id}."))
        self._open_detail_view()

    async def load_runs(self) -> None:
        """Discover saved evidence only after an explicit user action."""
        status = self.query_one("#run-status", Static)
        status.update(Text("Loading saved run evidence…"))
        worker = self.run_worker(
            lambda: load_workflow_index(self._store()),
            thread=True,
            name="load-workflow-index",
            exclusive=True,
            exit_on_error=False,
        )
        try:
            entries = await worker.wait()
        except (OSError, WorkerCancelled, WorkerFailed):
            status.update(Text("Could not list run evidence; no files were changed."))
            self._show_detail("saved runs\n\nunavailable — run evidence could not be read.")
            return

        run_list = self.query_one("#run-list", ListView)
        await run_list.clear()
        if entries:
            await run_list.extend(RunItem(entry) for entry in entries)
            status.update(Text(f"{len(entries)} saved runs · overview is privacy-bounded."))
        else:
            status.update(Text("No saved runs."))
        if self.size.width < 110:
            self.screen.remove_class("-detail-open")
            self.screen.add_class("-runs-open")
        run_list.focus()

    async def action_runs(self) -> None:
        """Open the saved-run browser after a read-only worker completes."""
        await self.load_runs()

    def action_plan(self) -> None:
        plan = self.controller.state.current_plan
        body = "\n".join(f"{index}. {step}" for index, step in enumerate(plan, start=1))
        self._show_detail(f"plan\n\n{body or 'none — submit an intent to create the demo plan.'}")
        self._open_detail_view()

    def action_permissions(self) -> None:
        capabilities = "\n".join(self.controller.capability_boundaries())
        self._show_detail(
            f"permissions\n\n{capabilities}\n\nNo permission was requested or granted."
        )
        self._open_detail_view()

    def action_help(self) -> None:
        self._show_detail(
            "help\n\n"
            "/workspace  already in this view\n"
            "/simple     return to the simple view\n"
            "/context    show context activity\n"
            "/plan       show the current plan\n"
            "/permissions show capabilities\n"
            "/runs       discover saved evidence\n"
            "/sources    show gathered sources\n"
            "/help       show this help\n"
            "/exit       end the session\n\n"
            "Ctrl+K commands · Tab focus · arrows navigate · Enter inspect · Esc back"
        )
        self._open_detail_view()

    def action_simple(self) -> None:
        self.exit(PresentationResult(Presentation.SIMPLE))

    def action_exit(self) -> None:
        self.exit(PresentationResult(Presentation.EXIT))

    def action_interrupt(self) -> None:
        self.exit(PresentationResult(Presentation.EXIT, exit_code=130))

    def action_back(self) -> None:
        if self.screen.has_class("-runs-open") or self.screen.has_class("-detail-open"):
            self.screen.remove_class("-runs-open", "-detail-open")
            self.query_one("#composer", Input).focus()
        else:
            self.query_one("#composer", Input).focus()

    def _store(self) -> JsonlTraceStore:
        from .agent.audit import JsonlTraceStore

        if self._trace_store is None:
            self._trace_store = JsonlTraceStore(self.controller.config.data_dir / "agent" / "runs")
        return self._trace_store

    def _read_workflow(self, run_id: str) -> list[str]:
        return render_workflow(run_id, self._store().read(run_id))

    def _show_activity(self, activity: Activity) -> None:
        details = "\n".join(activity.display_details) or "No additional display-safe detail."
        run = f"\nrun: {activity.run_id}" if activity.run_id else ""
        self._show_detail(
            f"{activity.kind.value} · {activity.status.value}\n\n"
            f"{activity.summary}\n\n{details}{run}"
        )

    def _show_activity_group(self, kind: ActivityKind, title: str) -> None:
        activities = self.controller.activities_for(kind)
        if not activities:
            self._show_detail(f"{title}\n\nnone")
            return
        lines = [f"{item.kind.value} · {item.status.value}: {item.summary}" for item in activities]
        self._show_detail(f"{title}\n\n" + "\n".join(lines))

    def _show_run_summary(self, entry: WorkflowIndexEntry) -> None:
        started = iso_utc(entry.started_at) if entry.started_at is not None else "unknown"
        issues = "\n".join(f"- {issue}" for issue in entry.issues) or "none"
        self._show_detail(
            "saved run overview\n\n"
            f"run: {entry.lookup_id}\n"
            f"started: {started}\n"
            f"intent: {entry.objective}\n"
            f"saved status: {entry.saved_status}\n"
            f"recomputed controls: {entry.controls}\n"
            f"issues:\n{issues}\n\n"
            "Press Enter to explicitly open detailed trace evidence."
        )

    def _show_detail(self, text: str) -> None:
        self.query_one("#detail-content", Static).update(Text(text))

    def _open_detail_view(self) -> None:
        if self.size.width < 110:
            self.screen.remove_class("-runs-open")
            self.screen.add_class("-detail-open")


def load_workflow_index(store: JsonlTraceStore) -> list[WorkflowIndexEntry]:
    """Load saved-run summaries only after an explicit user action."""
    from .workflow_index import load_workflow_index as load

    return load(store)


def render_workflow(run_id: str, events: Sequence[TraceEvent]) -> list[str]:
    """Render private trace detail only after explicit inspection."""
    from .workflow_view import render_workflow as render

    return render(run_id, events)


def run_workspace(controller: SessionController) -> PresentationResult:
    """Run the full-screen presentation and return its requested transition."""
    try:
        result = WorkspaceApp(controller).run()
    except KeyboardInterrupt:
        return PresentationResult(Presentation.EXIT, exit_code=130)
    return result or PresentationResult(Presentation.EXIT)
