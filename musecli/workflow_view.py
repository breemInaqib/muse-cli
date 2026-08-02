"""Deterministic, human-readable rendering of agent workflow evidence."""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from typing import Any

from .agent.contracts import EvaluationResult, TraceEvent
from .agent.evaluation import evaluate_trace

_INDENT = "  "


def render_workflow(run_id: str, events: Iterable[TraceEvent]) -> list[str]:
    """Render known trace phases while leaving the source JSONL unchanged."""
    trace = list(events)
    started = _latest(trace, "run_started")
    context = _latest(trace, "context_selected")
    proposal = _latest(trace, "proposal_created")
    completed = _latest(trace, "run_completed")
    evaluation = evaluate_trace(trace, require_completion=True)
    status = _text(completed.get("status")) if completed else "incomplete"

    lines = ["muse-code", _line(f"run: {run_id}"), _line(f"status: {status}")]
    lines.extend(["", "intent"])
    lines.extend(_render_intent(started))
    lines.extend(["", "context"])
    lines.extend(_render_context(context))
    lines.extend(["", "plan"])
    lines.extend(_render_plan(proposal))
    lines.extend(["", "permissions"])
    lines.extend(_render_permissions(trace))
    lines.extend(["", "actions"])
    lines.extend(_render_actions(trace))
    lines.extend(["", "verification"])
    lines.extend(_render_verification(trace))
    lines.extend(["", "evaluation"])
    lines.extend(_render_evaluation(evaluation))
    trace_state = "pass" if evaluation.passed else "fail"
    lines.extend(["", "result", _line(status), _line(f"trace controls: {trace_state}")])
    return lines


def _render_intent(started: Mapping[str, Any]) -> list[str]:
    if not started:
        return [_line("unavailable")]
    lines = [_line(f"objective: {_one_line(started.get('objective'))}")]
    specification = _one_line(started.get("specification"))
    digest = _text(started.get("specification_digest"))
    if specification:
        lines.append(_line(f"specification: {specification}"))
    else:
        lines.append(_line("specification: unavailable"))
    if digest:
        lines.append(_line(f"specification digest: sha256:{digest}"))
    return lines


def _render_context(context: Mapping[str, Any]) -> list[str]:
    items = context.get("items", []) if context else []
    if not isinstance(items, list) or not items:
        return [_line("none")]
    lines: list[str] = []
    for item in items:
        if not isinstance(item, Mapping):
            continue
        reference = _one_line(item.get("reference")) or "unknown"
        kind = _one_line(item.get("kind")) or "unknown"
        digest = _text(item.get("digest"))
        lines.append(_line(f"- {reference} ({kind})"))
        if digest:
            lines.append(_line(f"digest: sha256:{digest}", depth=2))
    return lines or [_line("none")]


def _render_plan(proposal: Mapping[str, Any]) -> list[str]:
    if not proposal:
        return [_line("unavailable")]
    lines = [_line(f"summary: {_one_line(proposal.get('summary'))}")]
    response = _one_line(proposal.get("response"))
    if response:
        lines.append(_line(f"response: {response}"))
    calls = proposal.get("tool_calls", [])
    if not isinstance(calls, list) or not calls:
        lines.append(_line("calls: none"))
        return lines
    lines.append(_line("calls:"))
    for call in calls:
        if not isinstance(call, Mapping):
            continue
        lines.append(
            _line(
                f"- {_one_line(call.get('tool_name'))} [{_one_line(call.get('call_id'))}]",
                depth=2,
            )
        )
        lines.append(_line(f"why: {_one_line(call.get('reason'))}", depth=3))
        lines.append(
            _line(
                f"arguments: {_json(call.get('arguments', {}))}",
                depth=3,
            )
        )
    return lines


def _render_permissions(events: list[TraceEvent]) -> list[str]:
    decisions = _all(events, "permission_decided")
    if not decisions:
        return [_line("none")]
    lines: list[str] = []
    for decision in decisions:
        allowed = "allowed" if bool(decision.get("allowed")) else "denied"
        lines.append(
            _line(
                f"- {allowed} {_one_line(decision.get('tool_name'))} "
                f"[{_one_line(decision.get('call_id'))}]"
            )
        )
        lines.append(
            _line(
                f"required: {_comma_list(decision.get('required'))}",
                depth=2,
            )
        )
        lines.append(
            _line(
                f"granted: {_comma_list(decision.get('granted'))}",
                depth=2,
            )
        )
        lines.append(_line(f"reason: {_one_line(decision.get('reason'))}", depth=2))
    return lines


def _render_actions(events: list[TraceEvent]) -> list[str]:
    actions = [event for event in events if event.event_type in {"tool_finished", "tool_skipped"}]
    if not actions:
        return [_line("none")]
    lines: list[str] = []
    for event in actions:
        data = event.data
        if event.event_type == "tool_skipped":
            lines.append(
                _line(
                    f"- skipped {_one_line(data.get('tool_name'))} "
                    f"[{_one_line(data.get('call_id'))}]"
                )
            )
            lines.append(_line(f"reason: {_one_line(data.get('reason'))}", depth=2))
            continue
        result = "success" if bool(data.get("success")) else "failed"
        change = _one_line(data.get("change")) or "unknown"
        lines.append(
            _line(
                f"- {result} {change} {_one_line(data.get('tool_name'))} "
                f"[{_one_line(data.get('call_id'))}]"
            )
        )
        lines.append(_line(f"summary: {_one_line(data.get('summary'))}", depth=2))
        evidence = data.get("evidence", [])
        if isinstance(evidence, list):
            for item in evidence:
                lines.append(_line(f"evidence: {_one_line(item)}", depth=2))
    return lines


def _render_verification(events: list[TraceEvent]) -> list[str]:
    checks = _all(events, "verification_finished")
    if not checks:
        return [_line("none")]
    lines: list[str] = []
    for check in checks:
        state = "pass" if bool(check.get("passed")) else "fail"
        lines.append(
            _line(f"- {state} {_one_line(check.get('name'))}: {_one_line(check.get('summary'))}")
        )
        evidence = check.get("evidence", [])
        if isinstance(evidence, list):
            for item in evidence:
                lines.append(_line(f"evidence: {_one_line(item)}", depth=2))
    return lines


def _render_evaluation(evaluation: EvaluationResult) -> list[str]:
    if not evaluation.checks:
        return [_line("none")]
    lines: list[str] = []
    for check in evaluation.checks:
        state = "pass" if check.passed else "fail"
        lines.append(_line(f"- {state} {check.name}: {check.detail}"))
    return lines or [_line("none")]


def _latest(events: list[TraceEvent], event_type: str) -> Mapping[str, Any]:
    matches = _all(events, event_type)
    return matches[-1] if matches else {}


def _all(events: list[TraceEvent], event_type: str) -> list[Mapping[str, Any]]:
    return [event.data for event in events if event.event_type == event_type]


def _line(text: str, *, depth: int = 1) -> str:
    return f"{_INDENT * depth}{text}"


def _one_line(value: object) -> str:
    return " ".join(_text(value).split())


def _text(value: object) -> str:
    return value if isinstance(value, str) else ""


def _comma_list(value: object) -> str:
    if not isinstance(value, list) or not value:
        return "none"
    return ", ".join(sorted(_one_line(item) for item in value))


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=True, separators=(",", ":"), sort_keys=True)
