"""Phase-oriented orchestration for one controlled agent run."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from uuid import uuid4

from .contracts import (
    AgentOutcome,
    AgentRequest,
    AgentTool,
    ChangeStatus,
    ContextItem,
    ContextProvider,
    EvaluationResult,
    ModelInput,
    ModelProposal,
    ModelRunner,
    PermissionDecision,
    RunStatus,
    ToolCall,
    ToolExecution,
    ToolResult,
    TraceStore,
    VerificationResult,
    Verifier,
)
from .evaluation import evaluate_trace
from .permissions import PermissionPolicy


@dataclass(frozen=True)
class _PreflightCall:
    call: ToolCall
    tool: AgentTool | None
    decision: PermissionDecision


class AgentHarness:
    """Coordinate retrieval, proposal, authorization, execution, and verification."""

    def __init__(
        self,
        *,
        runner: ModelRunner,
        context_provider: ContextProvider,
        tools: Iterable[AgentTool],
        permission_policy: PermissionPolicy,
        verifiers: Iterable[Verifier],
        trace_store: TraceStore,
        run_id_factory: Callable[[], str] | None = None,
    ) -> None:
        self.runner = runner
        self.context_provider = context_provider
        self.permission_policy = permission_policy
        self.trace_store = trace_store
        self.run_id_factory = run_id_factory or (lambda: str(uuid4()))
        self.tools = _index_tools(tools)
        self.verifiers = tuple(verifiers)
        if not self.verifiers:
            raise ValueError("at least one verifier is required")

    def run(self, request: AgentRequest) -> AgentOutcome:
        """Execute one bounded run and return only verified success."""
        run_id = self.run_id_factory()
        self.trace_store.record(
            run_id,
            "run_started",
            {
                "objective": request.objective,
                "specification": request.specification,
                "specification_digest": request.specification_digest,
                "workspace": str(request.workspace),
                "runner": self.runner.identity,
                "context_provider": self.context_provider.identity,
                "registered_tools": sorted(self.tools),
                "permission_grants": self.permission_policy.describe(),
                "verifiers": sorted(verifier.name for verifier in self.verifiers),
            },
        )

        try:
            context = tuple(self.context_provider.retrieve(request))
        except Exception as exc:
            return self._early_failure(run_id, stage="context", error=exc)
        self.trace_store.record(
            run_id,
            "context_selected",
            {"items": [_context_evidence(item) for item in context]},
        )

        try:
            proposal = self.runner.run(ModelInput(request=request, context=context))
        except Exception as exc:
            return self._early_failure(run_id, stage="model", error=exc)
        self.trace_store.record(run_id, "proposal_created", _proposal_evidence(proposal))

        preflight = self._preflight(request, proposal)
        for item in preflight:
            self.trace_store.record(
                run_id,
                "permission_decided",
                _permission_evidence(item.decision),
            )
        if any(not item.decision.allowed for item in preflight):
            evaluation = self._evaluate_and_record(run_id)
            return self._complete(
                run_id=run_id,
                status=RunStatus.REJECTED,
                proposal=proposal,
                tool_results=(),
                verification_results=(),
                evaluation=evaluation,
            )

        tool_results = self._execute(run_id, request, preflight)
        verification_results = self._verify(run_id, request, proposal, tool_results)
        status = RunStatus.VERIFIED
        if any(not result.execution.success for result in tool_results) or any(
            not result.passed for result in verification_results
        ):
            status = RunStatus.FAILED

        evaluation = self._evaluate_and_record(run_id)
        if not evaluation.passed:
            status = RunStatus.FAILED
        return self._complete(
            run_id=run_id,
            status=status,
            proposal=proposal,
            tool_results=tool_results,
            verification_results=verification_results,
            evaluation=evaluation,
        )

    def _preflight(
        self,
        request: AgentRequest,
        proposal: ModelProposal,
    ) -> tuple[_PreflightCall, ...]:
        items: list[_PreflightCall] = []
        for call in proposal.tool_calls:
            tool = self.tools.get(call.tool_name)
            if tool is None:
                decision = PermissionDecision(
                    call_id=call.call_id,
                    tool_name=call.tool_name,
                    allowed=False,
                    required=frozenset(),
                    granted=frozenset(),
                    reason="tool is not registered",
                )
            else:
                decision = self.permission_policy.decide(tool, call, request)
            items.append(_PreflightCall(call=call, tool=tool, decision=decision))
        return tuple(items)

    def _execute(
        self,
        run_id: str,
        request: AgentRequest,
        preflight: Sequence[_PreflightCall],
    ) -> tuple[ToolResult, ...]:
        results: list[ToolResult] = []
        failed = False
        for item in preflight:
            if failed:
                self.trace_store.record(
                    run_id,
                    "tool_skipped",
                    {
                        "call_id": item.call.call_id,
                        "tool_name": item.call.tool_name,
                        "reason": "a previous tool failed",
                    },
                )
                continue
            if item.tool is None:
                raise AssertionError("authorized calls must have a registered tool")
            self.trace_store.record(
                run_id,
                "tool_started",
                {
                    "call_id": item.call.call_id,
                    "tool_name": item.call.tool_name,
                    "arguments": dict(item.call.arguments),
                    "reason": item.call.reason,
                },
            )
            try:
                execution = item.tool.execute(item.call, request)
            except Exception as exc:
                execution = ToolExecution(
                    success=False,
                    change=ChangeStatus.UNKNOWN,
                    summary=f"tool raised {type(exc).__name__}",
                )
            result = ToolResult(
                call_id=item.call.call_id,
                tool_name=item.call.tool_name,
                execution=execution,
            )
            results.append(result)
            self.trace_store.record(run_id, "tool_finished", _tool_result_evidence(result))
            failed = not execution.success
        return tuple(results)

    def _verify(
        self,
        run_id: str,
        request: AgentRequest,
        proposal: ModelProposal,
        tool_results: Sequence[ToolResult],
    ) -> tuple[VerificationResult, ...]:
        results: list[VerificationResult] = []
        for verifier in self.verifiers:
            try:
                raw = verifier.verify(request, proposal, tool_results)
                result = VerificationResult(
                    name=verifier.name,
                    passed=raw.passed,
                    summary=raw.summary,
                    evidence=raw.evidence,
                )
            except Exception as exc:
                result = VerificationResult(
                    name=verifier.name,
                    passed=False,
                    summary=f"verifier raised {type(exc).__name__}",
                )
            results.append(result)
            self.trace_store.record(run_id, "verification_finished", _verification_evidence(result))
        return tuple(results)

    def _early_failure(
        self,
        run_id: str,
        *,
        stage: str,
        error: Exception,
    ) -> AgentOutcome:
        self.trace_store.record(
            run_id,
            "run_failed",
            {"stage": stage, "error_type": type(error).__name__},
        )
        evaluation = self._evaluate_and_record(run_id)
        return self._complete(
            run_id=run_id,
            status=RunStatus.FAILED,
            proposal=None,
            tool_results=(),
            verification_results=(),
            evaluation=evaluation,
        )

    def _evaluate_and_record(self, run_id: str) -> EvaluationResult:
        evaluation = evaluate_trace(self.trace_store.read(run_id))
        self.trace_store.record(
            run_id,
            "run_evaluated",
            {
                "passed": evaluation.passed,
                "checks": [
                    {
                        "name": check.name,
                        "passed": check.passed,
                        "detail": check.detail,
                    }
                    for check in evaluation.checks
                ],
            },
        )
        return evaluation

    def _complete(
        self,
        *,
        run_id: str,
        status: RunStatus,
        proposal: ModelProposal | None,
        tool_results: Sequence[ToolResult],
        verification_results: Sequence[VerificationResult],
        evaluation: EvaluationResult,
    ) -> AgentOutcome:
        self.trace_store.record(
            run_id,
            "run_completed",
            {
                "status": status.value,
                "tool_results": len(tool_results),
                "verification_results": len(verification_results),
                "evaluation_passed": evaluation.passed,
            },
        )
        return AgentOutcome(
            run_id=run_id,
            status=status,
            proposal=proposal,
            tool_results=tuple(tool_results),
            verification_results=tuple(verification_results),
            evaluation=evaluation,
        )


def _index_tools(tools: Iterable[AgentTool]) -> Mapping[str, AgentTool]:
    indexed: dict[str, AgentTool] = {}
    for tool in tools:
        if tool.name in indexed:
            raise ValueError(f"duplicate tool name: {tool.name}")
        indexed[tool.name] = tool
    return indexed


def _context_evidence(item: ContextItem) -> dict[str, str]:
    return {
        "reference": item.reference,
        "kind": item.kind,
        "digest": item.digest,
    }


def _proposal_evidence(proposal: ModelProposal) -> dict[str, object]:
    return {
        "summary": proposal.summary,
        "response": proposal.response,
        "tool_calls": [
            {
                "call_id": call.call_id,
                "tool_name": call.tool_name,
                "arguments": dict(call.arguments),
                "reason": call.reason,
            }
            for call in proposal.tool_calls
        ],
    }


def _permission_evidence(decision: PermissionDecision) -> dict[str, object]:
    return {
        "call_id": decision.call_id,
        "tool_name": decision.tool_name,
        "allowed": decision.allowed,
        "required": sorted(capability.value for capability in decision.required),
        "granted": sorted(capability.value for capability in decision.granted),
        "reason": decision.reason,
    }


def _tool_result_evidence(result: ToolResult) -> dict[str, object]:
    return {
        "call_id": result.call_id,
        "tool_name": result.tool_name,
        "success": result.execution.success,
        "change": result.execution.change.value,
        "summary": result.execution.summary,
        "evidence": list(result.execution.evidence),
    }


def _verification_evidence(result: VerificationResult) -> dict[str, object]:
    return {
        "name": result.name,
        "passed": result.passed,
        "summary": result.summary,
        "evidence": list(result.evidence),
    }
