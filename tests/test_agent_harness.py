from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import pytest

from musecli.agent import (
    AgentHarness,
    AgentRequest,
    Capability,
    ChangeStatus,
    ContextItem,
    JsonlTraceStore,
    ModelInput,
    ModelProposal,
    PermissionPolicy,
    RunStatus,
    ToolCall,
    ToolExecution,
    ToolGrant,
    VerificationResult,
)
from musecli.agent.contracts import ToolResult
from musecli.agent.evaluation import evaluate_trace


class StaticContextProvider:
    identity = "static-context-v1"

    def __init__(self, items: Sequence[ContextItem] = ()) -> None:
        self.items = tuple(items)

    def retrieve(self, request: AgentRequest) -> Sequence[ContextItem]:
        return self.items


class StaticRunner:
    identity = "test-runner-v1"

    def __init__(self, proposal: ModelProposal) -> None:
        self.proposal = proposal
        self.inputs: list[ModelInput] = []

    def run(self, model_input: ModelInput) -> ModelProposal:
        self.inputs.append(model_input)
        return self.proposal


class RecordingTool:
    def __init__(
        self,
        name: str,
        *,
        required: frozenset[Capability],
        execution: ToolExecution,
        raises: bool = False,
    ) -> None:
        self.name = name
        self.required = required
        self.execution = execution
        self.raises = raises
        self.calls: list[ToolCall] = []

    def required_capabilities(
        self,
        call: ToolCall,
        request: AgentRequest,
    ) -> frozenset[Capability]:
        return self.required

    def execute(self, call: ToolCall, request: AgentRequest) -> ToolExecution:
        self.calls.append(call)
        if self.raises:
            raise RuntimeError("simulated tool failure")
        return self.execution


class StaticVerifier:
    def __init__(self, name: str = "tests", *, passed: bool = True) -> None:
        self.name = name
        self.passed = passed
        self.calls: list[Sequence[ToolResult]] = []

    def verify(
        self,
        request: AgentRequest,
        proposal: ModelProposal,
        tool_results: Sequence[ToolResult],
    ) -> VerificationResult:
        self.calls.append(tool_results)
        return VerificationResult(
            name=self.name,
            passed=self.passed,
            summary="checks passed" if self.passed else "checks failed",
            evidence=("pytest: 1 passed",),
        )


def _request(workspace: Path) -> AgentRequest:
    return AgentRequest(
        objective="Update one local file",
        specification="The requested file exists and tests pass.",
        workspace=workspace,
    )


def _call(call_id: str = "call-1", tool_name: str = "write_file") -> ToolCall:
    return ToolCall(
        call_id=call_id,
        tool_name=tool_name,
        arguments={"path": "example.txt"},
        reason="Create the file required by the specification.",
    )


def test_tool_call_rejects_non_json_arguments() -> None:
    with pytest.raises(ValueError, match="JSON serializable"):
        ToolCall(
            call_id="call-1",
            tool_name="write_file",
            arguments={"value": object()},
            reason="invalid model output",
        )


def _proposal(*calls: ToolCall) -> ModelProposal:
    return ModelProposal(
        summary="Create the requested file and verify it.",
        response="One bounded local change is proposed.",
        tool_calls=tuple(calls),
    )


def _harness(
    tmp_path: Path,
    *,
    proposal: ModelProposal,
    tools: Sequence[RecordingTool],
    grants: Sequence[ToolGrant],
    verifier: StaticVerifier,
) -> tuple[AgentHarness, JsonlTraceStore]:
    store = JsonlTraceStore(tmp_path / "runs")
    harness = AgentHarness(
        runner=StaticRunner(proposal),
        context_provider=StaticContextProvider(
            (ContextItem(reference="example.txt", kind="file", content="before"),)
        ),
        tools=tools,
        permission_policy=PermissionPolicy(grants),
        verifiers=(verifier,),
        trace_store=store,
        run_id_factory=lambda: "test-run",
    )
    return harness, store


def test_verified_run_records_all_control_boundaries(tmp_path: Path) -> None:
    tool = RecordingTool(
        "write_file",
        required=frozenset({Capability.WORKSPACE_WRITE}),
        execution=ToolExecution(
            success=True,
            change=ChangeStatus.CHANGED,
            summary="created example.txt",
            evidence=("example.txt: sha256:abc",),
        ),
    )
    verifier = StaticVerifier()
    harness, store = _harness(
        tmp_path,
        proposal=_proposal(_call()),
        tools=(tool,),
        grants=(ToolGrant("write_file", frozenset({Capability.WORKSPACE_WRITE})),),
        verifier=verifier,
    )

    outcome = harness.run(_request(tmp_path))

    assert outcome.status is RunStatus.VERIFIED
    assert outcome.evaluation.passed is True
    assert [call.call_id for call in tool.calls] == ["call-1"]
    assert len(verifier.calls) == 1
    events = store.read("test-run")
    assert [event.event_type for event in events] == [
        "run_started",
        "context_selected",
        "proposal_created",
        "permission_decided",
        "tool_started",
        "tool_finished",
        "verification_finished",
        "run_evaluated",
        "run_completed",
    ]
    assert events[0].data["specification"] == "The requested file exists and tests pass."
    assert events[-1].data["status"] == "verified"
    assert "before" not in store.path_for("test-run").read_text(encoding="utf-8")


def test_denied_proposal_executes_no_tools(tmp_path: Path) -> None:
    tool = RecordingTool(
        "write_file",
        required=frozenset({Capability.WORKSPACE_WRITE}),
        execution=ToolExecution(
            success=True,
            change=ChangeStatus.CHANGED,
            summary="should not run",
        ),
    )
    harness, store = _harness(
        tmp_path,
        proposal=_proposal(_call(), _call("call-2", "unregistered")),
        tools=(tool,),
        grants=(ToolGrant("write_file", frozenset({Capability.WORKSPACE_WRITE})),),
        verifier=StaticVerifier(),
    )

    outcome = harness.run(_request(tmp_path))

    assert outcome.status is RunStatus.REJECTED
    assert tool.calls == []
    event_types = [event.event_type for event in store.read("test-run")]
    assert "tool_started" not in event_types
    assert "verification_finished" not in event_types


def test_tool_failure_skips_later_actions_and_still_verifies(tmp_path: Path) -> None:
    failing = RecordingTool(
        "write_file",
        required=frozenset({Capability.WORKSPACE_WRITE}),
        execution=ToolExecution(
            success=True,
            change=ChangeStatus.CHANGED,
            summary="unused",
        ),
        raises=True,
    )
    later = RecordingTool(
        "run_tests",
        required=frozenset({Capability.PROCESS_EXECUTE}),
        execution=ToolExecution(
            success=True,
            change=ChangeStatus.NONE,
            summary="tests passed",
        ),
    )
    verifier = StaticVerifier()
    harness, store = _harness(
        tmp_path,
        proposal=_proposal(_call(), _call("call-2", "run_tests")),
        tools=(failing, later),
        grants=(
            ToolGrant("write_file", frozenset({Capability.WORKSPACE_WRITE})),
            ToolGrant("run_tests", frozenset({Capability.PROCESS_EXECUTE})),
        ),
        verifier=verifier,
    )

    outcome = harness.run(_request(tmp_path))

    assert outcome.status is RunStatus.FAILED
    assert outcome.tool_results[0].execution.change is ChangeStatus.UNKNOWN
    assert later.calls == []
    assert len(verifier.calls) == 1
    assert "tool_skipped" in [event.event_type for event in store.read("test-run")]


def test_failed_verification_prevents_verified_status(tmp_path: Path) -> None:
    harness, _store = _harness(
        tmp_path,
        proposal=_proposal(),
        tools=(),
        grants=(),
        verifier=StaticVerifier(passed=False),
    )

    outcome = harness.run(_request(tmp_path))

    assert outcome.status is RunStatus.FAILED
    assert outcome.verification_results[0].passed is False


def test_trace_evaluation_flags_missing_control_evidence(tmp_path: Path) -> None:
    store = JsonlTraceStore(tmp_path / "runs")
    store.record(
        "incomplete",
        "proposal_created",
        {
            "summary": "unsafe incomplete trace",
            "tool_calls": [
                {
                    "call_id": "call-1",
                    "tool_name": "write_file",
                }
            ],
        },
    )

    evaluation = evaluate_trace(store.read("incomplete"))

    assert evaluation.passed is False
    failed = {check.name for check in evaluation.checks if not check.passed}
    assert failed == {
        "permission_coverage",
        "execution_coverage",
        "verification_boundary",
    }
