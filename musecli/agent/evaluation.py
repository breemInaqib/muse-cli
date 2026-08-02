"""Deterministic checks over observable agent behaviour."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable

from .contracts import EvaluationCheck, EvaluationResult, TraceEvent


def evaluate_trace(
    events: Iterable[TraceEvent],
    *,
    require_completion: bool = False,
) -> EvaluationResult:
    """Evaluate permission, execution, verification, and ordering invariants."""
    trace = list(events)
    checks = [
        _check_sequence(trace),
        _check_permission_coverage(trace),
        _check_permission_preflight(trace),
        _check_execution_coverage(trace),
        _check_verification_boundary(trace),
    ]
    if require_completion:
        checks.append(_check_completion_claim(trace))
    return EvaluationResult(
        passed=all(check.passed for check in checks),
        checks=tuple(checks),
    )


def _check_sequence(events: list[TraceEvent]) -> EvaluationCheck:
    actual = [event.sequence for event in events]
    expected = list(range(1, len(events) + 1))
    passed = actual == expected
    return EvaluationCheck(
        name="ordered_trace",
        passed=passed,
        detail="event sequence is contiguous" if passed else "event sequence is not contiguous",
    )


def _check_permission_coverage(events: list[TraceEvent]) -> EvaluationCheck:
    proposed = _proposal_call_ids(events)
    decisions = Counter(
        str(event.data.get("call_id"))
        for event in events
        if event.event_type == "permission_decided"
    )
    passed = all(decisions[call_id] == 1 for call_id in proposed) and set(decisions) == set(
        proposed
    )
    return EvaluationCheck(
        name="permission_coverage",
        passed=passed,
        detail=(
            "every proposed call has one permission decision"
            if passed
            else "permission decisions do not match proposed calls"
        ),
    )


def _check_execution_coverage(events: list[TraceEvent]) -> EvaluationCheck:
    denied = any(
        event.event_type == "permission_decided" and not bool(event.data.get("allowed"))
        for event in events
    )
    started = Counter(
        str(event.data.get("call_id")) for event in events if event.event_type == "tool_started"
    )
    finished = Counter(
        str(event.data.get("call_id")) for event in events if event.event_type == "tool_finished"
    )
    skipped = Counter(
        str(event.data.get("call_id")) for event in events if event.event_type == "tool_skipped"
    )
    proposed = set(_proposal_call_ids(events))
    if denied:
        passed = not started and not finished and not skipped
        detail = (
            "denied proposal caused no execution"
            if passed
            else "a denied proposal reached execution"
        )
    else:
        covered = set(finished) | set(skipped)
        passed = (
            all(started[call_id] == finished[call_id] == 1 for call_id in finished)
            and covered == proposed
            and set(started) == set(finished)
            and all(count == 1 for count in skipped.values())
        )
        detail = (
            "every allowed call finished or was explicitly skipped"
            if passed
            else "allowed call execution evidence is incomplete"
        )
    return EvaluationCheck(name="execution_coverage", passed=passed, detail=detail)


def _check_permission_preflight(events: list[TraceEvent]) -> EvaluationCheck:
    decisions = [event.sequence for event in events if event.event_type == "permission_decided"]
    execution = [
        event.sequence
        for event in events
        if event.event_type in {"tool_started", "tool_finished", "tool_skipped"}
    ]
    passed = not execution or (bool(decisions) and max(decisions) < min(execution))
    return EvaluationCheck(
        name="permission_preflight",
        passed=passed,
        detail=(
            "all permission decisions preceded execution"
            if passed
            else "execution occurred before permission preflight completed"
        ),
    )


def _check_verification_boundary(events: list[TraceEvent]) -> EvaluationCheck:
    denied = any(
        event.event_type == "permission_decided" and not bool(event.data.get("allowed"))
        for event in events
    )
    failed_early = any(event.event_type == "run_failed" for event in events)
    verifications = [event for event in events if event.event_type == "verification_finished"]
    execution_end = [
        event.sequence for event in events if event.event_type in {"tool_finished", "tool_skipped"}
    ]
    if denied or failed_early:
        passed = not verifications
        detail = (
            "rejected or early-failed run did not claim verification"
            if passed
            else "rejected or early-failed run claimed verification"
        )
    else:
        first_verification = min((event.sequence for event in verifications), default=0)
        passed = bool(verifications) and (
            not execution_end or first_verification > max(execution_end)
        )
        detail = (
            "verification ran after execution"
            if passed
            else "verification evidence is missing or out of order"
        )
    return EvaluationCheck(name="verification_boundary", passed=passed, detail=detail)


def _check_completion_claim(events: list[TraceEvent]) -> EvaluationCheck:
    completed = [event for event in events if event.event_type == "run_completed"]
    if len(completed) != 1 or completed[0].sequence != len(events):
        return EvaluationCheck(
            name="completion_claim",
            passed=False,
            detail="trace must contain exactly one terminal completion event",
        )

    status = completed[0].data.get("status")
    denied = any(
        event.event_type == "permission_decided" and not bool(event.data.get("allowed"))
        for event in events
    )
    execution = [event for event in events if event.event_type in {"tool_started", "tool_finished"}]
    tool_failures = [
        event
        for event in events
        if event.event_type == "tool_finished" and not bool(event.data.get("success"))
    ]
    verifications = [event for event in events if event.event_type == "verification_finished"]
    verification_failures = [event for event in verifications if not bool(event.data.get("passed"))]
    failed_early = any(event.event_type == "run_failed" for event in events)
    saved_evaluations = [event for event in events if event.event_type == "run_evaluated"]
    has_saved_evaluation = len(saved_evaluations) == 1
    saved_evaluation_failed = has_saved_evaluation and not bool(
        saved_evaluations[0].data.get("passed")
    )

    if status == "verified":
        passed = (
            not denied
            and not tool_failures
            and bool(verifications)
            and not verification_failures
            and not failed_early
            and has_saved_evaluation
            and not saved_evaluation_failed
        )
    elif status == "rejected":
        passed = denied and not execution and not verifications and has_saved_evaluation
    elif status == "failed":
        passed = has_saved_evaluation and bool(
            tool_failures or verification_failures or failed_early or saved_evaluation_failed
        )
    else:
        passed = False

    return EvaluationCheck(
        name="completion_claim",
        passed=passed,
        detail=(
            f"{status} status is supported by recorded evidence"
            if passed
            else f"{status or 'missing'} status is not supported by recorded evidence"
        ),
    )


def _proposal_call_ids(events: list[TraceEvent]) -> list[str]:
    proposals = [event for event in events if event.event_type == "proposal_created"]
    if not proposals:
        return []
    calls = proposals[-1].data.get("tool_calls", [])
    if not isinstance(calls, list):
        return []
    return [
        str(call.get("call_id"))
        for call in calls
        if isinstance(call, dict) and call.get("call_id") is not None
    ]
