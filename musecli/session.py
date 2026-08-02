"""Framework-neutral state for one visible muse work session."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
from uuid import uuid4

from .config import AppConfig


class ActivityKind(str, Enum):
    """A user-visible boundary in the intelligence workflow."""

    INTENT = "intent"
    PLAN = "plan"
    CONTEXT = "context"
    PERMISSION = "permission"
    TOOL = "tool"
    VERIFICATION = "verification"
    RESULT = "result"


class ActivityStatus(str, Enum):
    """Inspectable lifecycle state for an activity."""

    PENDING = "pending"
    ACTIVE = "active"
    COMPLETE = "complete"
    BLOCKED = "blocked"
    FAILED = "failed"
    SKIPPED = "skipped"
    CANCELLED = "cancelled"


@dataclass(frozen=True)
class Activity:
    """One immutable, display-safe session activity."""

    sequence: int
    kind: ActivityKind
    status: ActivityStatus
    summary: str
    display_details: tuple[str, ...] = ()
    run_id: Optional[str] = None  # noqa: UP045

    def __post_init__(self) -> None:
        if self.sequence < 1:
            raise ValueError("activity sequence must be positive")
        if not self.summary.strip():
            raise ValueError("activity summary must not be empty")
        object.__setattr__(self, "display_details", tuple(self.display_details))


@dataclass
class SessionState:
    """Process-local state shared by simple and workspace presentations."""

    session_id: str
    activities: list[Activity] = field(default_factory=list)
    current_plan: tuple[str, ...] = ()


class Presentation(str, Enum):
    """A presentation selected by the session coordinator."""

    SIMPLE = "simple"
    WORKSPACE = "workspace"
    EXIT = "exit"


class SessionCommand(str, Enum):
    """Commands shared by both process-local presentations."""

    HELP = "/help"
    CONTEXT = "/context"
    PLAN = "/plan"
    PERMISSIONS = "/permissions"
    RUNS = "/runs"
    SOURCES = "/sources"
    WORKSPACE = "/workspace"
    SIMPLE = "/simple"
    EXIT = "/exit"


@dataclass(frozen=True)
class CommandDispatch:
    """A normalized command or a display-safe parsing error."""

    command: Optional[SessionCommand] = None  # noqa: UP045
    error: Optional[str] = None  # noqa: UP045

    def __post_init__(self) -> None:
        if (self.command is None) == (self.error is None):
            raise ValueError("command dispatch must contain exactly one result")


@dataclass(frozen=True)
class PresentationResult:
    """The next presentation and process exit status requested by a view."""

    presentation: Presentation
    exit_code: int = 0


_DEMONSTRATION_PLAN = (
    "Record the intent.",
    "Expose it through both presentations.",
    "Finish without external execution.",
)

_CAPABILITY_BOUNDARIES = (
    "model execution: off",
    "context retrieval: off",
    "tool and shell execution: off",
    "network access: off",
    "file mutation: off",
)


class SessionController:
    """The sole serial mutator of one process-local session."""

    def __init__(
        self,
        config: AppConfig,
        session_id: Optional[str] = None,  # noqa: UP045
    ) -> None:
        resolved_session_id = session_id.strip() if session_id is not None else str(uuid4())
        if not resolved_session_id:
            raise ValueError("session id must not be empty")
        self.config = config
        self.state = SessionState(session_id=resolved_session_id)

    def submit(self, text: str) -> tuple[Activity, ...]:
        """Record one honest demonstration without executing the requested task."""
        raw_intent = text.strip()
        if not raw_intent:
            return ()
        if raw_intent.startswith("!"):
            raise ValueError("shell execution is unavailable")
        intent = _display_line(raw_intent)
        if not intent:
            return ()
        if intent.startswith("!"):
            raise ValueError("shell execution is unavailable")

        start = len(self.state.activities) + 1
        activities = (
            Activity(
                sequence=start,
                kind=ActivityKind.INTENT,
                status=ActivityStatus.COMPLETE,
                summary=intent,
                display_details=("User-provided intent.",),
            ),
            Activity(
                sequence=start + 1,
                kind=ActivityKind.PLAN,
                status=ActivityStatus.COMPLETE,
                summary=_DEMONSTRATION_PLAN[0],
                display_details=_DEMONSTRATION_PLAN[1:],
            ),
            Activity(
                sequence=start + 2,
                kind=ActivityKind.CONTEXT,
                status=ActivityStatus.SKIPPED,
                summary="No context was gathered.",
            ),
            Activity(
                sequence=start + 3,
                kind=ActivityKind.PERMISSION,
                status=ActivityStatus.SKIPPED,
                summary="No permission was requested or granted.",
            ),
            Activity(
                sequence=start + 4,
                kind=ActivityKind.TOOL,
                status=ActivityStatus.SKIPPED,
                summary="No tool, shell, network, or mutation ran.",
            ),
            Activity(
                sequence=start + 5,
                kind=ActivityKind.VERIFICATION,
                status=ActivityStatus.SKIPPED,
                summary="There was no generated change to verify.",
            ),
            Activity(
                sequence=start + 6,
                kind=ActivityKind.RESULT,
                status=ActivityStatus.COMPLETE,
                summary="Demonstration completed; the requested task was not executed.",
                display_details=("No model, tools, permissions, network, or files were used.",),
            ),
        )
        self.state.activities.extend(activities)
        self.state.current_plan = _DEMONSTRATION_PLAN
        return activities

    def activities_for(self, kind: ActivityKind) -> tuple[Activity, ...]:
        """Return activities of one kind in stable sequence order."""
        return tuple(activity for activity in self.state.activities if activity.kind is kind)

    def dispatch_command(self, text: str) -> CommandDispatch:
        """Normalize one presentation command without performing its action."""
        parts = _display_line(text).split(maxsplit=1)
        token = parts[0].lower() if parts else ""
        if len(parts) > 1:
            return CommandDispatch(error=f"error: command does not accept arguments: {token}")
        try:
            command = SessionCommand(token)
        except ValueError:
            return CommandDispatch(error=f"error: unknown command {token}")
        return CommandDispatch(command=command)

    def capability_boundaries(self) -> tuple[str, ...]:
        """Return the shared, display-safe capability state."""
        return _CAPABILITY_BOUNDARIES

    def latest_result(self) -> Optional[Activity]:  # noqa: UP045
        """Return the latest result activity, if one has been recorded."""
        for activity in reversed(self.state.activities):
            if activity.kind is ActivityKind.RESULT:
                return activity
        return None


def _display_line(value: str) -> str:
    """Return one printable line suitable for direct terminal rendering."""
    printable = "".join(character if character.isprintable() else " " for character in value)
    return " ".join(printable.split())
