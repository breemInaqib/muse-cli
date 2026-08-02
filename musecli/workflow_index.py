"""Read-only discovery and concise rendering of saved agent workflows."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .agent.audit import AuditLogError, JsonlTraceStore, is_safe_run_id
from .agent.contracts import TraceEvent
from .agent.evaluation import evaluate_trace
from .utils import iso_utc, truncate

_OBJECTIVE_WIDTH = 60
_RUN_ID_WIDTH = 128
_VALID_STATUSES = {"failed", "rejected", "verified"}


@dataclass(frozen=True)
class WorkflowIndexEntry:
    """Privacy-bounded summary of one discovered trace file."""

    source_name: str
    lookup_id: str
    started_at: datetime | None
    objective: str
    saved_status: str
    controls: str
    issues: tuple[str, ...] = ()


def load_workflow_index(store: JsonlTraceStore) -> list[WorkflowIndexEntry]:
    """Load every candidate independently and return deterministic ordering."""
    entries = [_load_entry(store, path) for path in store.trace_paths()]
    fallback_order = sorted(entries, key=lambda entry: entry.source_name)
    with_start = sorted(
        (entry for entry in fallback_order if entry.started_at is not None),
        key=lambda entry: entry.started_at,
        reverse=True,
    )
    without_start = [entry for entry in fallback_order if entry.started_at is None]
    return [*with_start, *without_start]


def summarize_workflow(path: Path, events: list[TraceEvent]) -> WorkflowIndexEntry:
    """Extract only listing-safe metadata and recompute trace controls."""
    lookup_id = path.stem
    issues: list[str] = []
    identity_valid = is_safe_run_id(lookup_id)
    if not identity_valid:
        issues.append("filename is not a valid inspectable run ID")

    recorded_id = events[0].run_id if events else None
    identity_matches = recorded_id is None or recorded_id == lookup_id
    if not identity_matches:
        issues.append(
            f"filename/recorded run ID mismatch (recorded: {_bounded_text(recorded_id, width=40)})"
        )

    started_events = [event for event in events if event.event_type == "run_started"]
    started_at: datetime | None = None
    objective = "unavailable"
    start_valid = len(started_events) == 1
    if not started_events:
        issues.append("missing run_started")
    elif len(started_events) > 1:
        issues.append("multiple run_started events")
    else:
        started_at = started_events[0].timestamp
        raw_objective = started_events[0].data.get("objective")
        if isinstance(raw_objective, str) and _terminal_text(raw_objective):
            objective = _bounded_text(raw_objective, width=_OBJECTIVE_WIDTH)
        else:
            issues.append("missing objective")
            start_valid = False

    completion_events = [event for event in events if event.event_type == "run_completed"]
    completion_valid = len(completion_events) == 1
    if not completion_events:
        saved_status = "incomplete"
        issues.append("missing run_completed")
    elif len(completion_events) > 1:
        saved_status = "ambiguous"
        issues.append("multiple run_completed events")
    else:
        raw_status = completion_events[0].data.get("status")
        if isinstance(raw_status, str) and raw_status in _VALID_STATUSES:
            saved_status = raw_status
        else:
            saved_status = "invalid"
            completion_valid = False
            issues.append("invalid saved status")

    evaluation = evaluate_trace(events, require_completion=True)
    controls_pass = (
        evaluation.passed
        and identity_valid
        and identity_matches
        and start_valid
        and completion_valid
    )
    if not evaluation.passed:
        if saved_status == "verified":
            issues.append("verified claim is not supported by trace controls")
        elif not any(issue.startswith(("missing ", "multiple ", "invalid ")) for issue in issues):
            issues.append("trace controls failed")

    return WorkflowIndexEntry(
        source_name=path.name,
        lookup_id=_bounded_text(lookup_id, width=_RUN_ID_WIDTH) or "unavailable",
        started_at=started_at,
        objective=objective,
        saved_status=saved_status,
        controls="pass" if controls_pass else "fail",
        issues=tuple(issues),
    )


def render_workflow_index(entries: list[WorkflowIndexEntry]) -> list[str]:
    """Render a stable, colour-free terminal index."""
    lines = ["muse-code runs", ""]
    if not entries:
        lines.append("  no saved runs")
        return lines

    for index, entry in enumerate(entries):
        if index:
            lines.append("")
        started = iso_utc(entry.started_at) if entry.started_at is not None else "unknown"
        lines.append(f"{started}  saved: {entry.saved_status}  controls: {entry.controls}")
        lines.append(f"  run: {entry.lookup_id}")
        lines.append(f"  intent: {entry.objective}")
        lines.extend(f"  issue: {issue}" for issue in entry.issues)
    return lines


def _load_entry(store: JsonlTraceStore, path: Path) -> WorkflowIndexEntry:
    try:
        events = store.read_path(path)
    except AuditLogError:
        return _unavailable_entry(path, issue="malformed evidence")
    except OSError:
        return _unavailable_entry(path, issue="unreadable evidence")
    except ValueError:
        return _unavailable_entry(path, issue="unsafe run file")
    return summarize_workflow(path, events)


def _unavailable_entry(path: Path, *, issue: str) -> WorkflowIndexEntry:
    return WorkflowIndexEntry(
        source_name=path.name,
        lookup_id=_bounded_text(path.stem, width=_RUN_ID_WIDTH) or "unavailable",
        started_at=None,
        objective="unavailable",
        saved_status="unreadable",
        controls="unavailable",
        issues=(issue,),
    )


def _bounded_text(value: str, *, width: int) -> str:
    return truncate(_terminal_text(value), width)


def _terminal_text(value: str) -> str:
    safe = "".join(
        " " if character.isspace() else character if character.isprintable() else "?"
        for character in value
    )
    return " ".join(safe.split())
