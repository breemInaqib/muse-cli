"""Typed contracts shared by the agent harness and its adapters."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from hashlib import sha256
from pathlib import Path
from typing import Any, Protocol


class Capability(str, Enum):
    """Permission categories that concrete tools must declare."""

    WORKSPACE_READ = "workspace.read"
    WORKSPACE_WRITE = "workspace.write"
    PROCESS_EXECUTE = "process.execute"
    NETWORK_ACCESS = "network.access"


class ChangeStatus(str, Enum):
    """Whether a tool changed local state."""

    NONE = "none"
    CHANGED = "changed"
    UNKNOWN = "unknown"


class RunStatus(str, Enum):
    """Terminal state of one harness run."""

    VERIFIED = "verified"
    REJECTED = "rejected"
    FAILED = "failed"


@dataclass(frozen=True)
class AgentRequest:
    """Explicit objective and acceptance specification for one local run."""

    objective: str
    specification: str
    workspace: Path

    def __post_init__(self) -> None:
        object.__setattr__(self, "objective", _required_text(self.objective, "objective"))
        object.__setattr__(
            self,
            "specification",
            _required_text(self.specification, "specification"),
        )
        object.__setattr__(self, "workspace", self.workspace.expanduser().resolve())

    @property
    def specification_digest(self) -> str:
        """Return a stable identifier for the exact acceptance specification."""
        return sha256(self.specification.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ContextItem:
    """One retrieved context item with stable provenance."""

    reference: str
    kind: str
    content: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "reference", _required_text(self.reference, "reference"))
        object.__setattr__(self, "kind", _required_text(self.kind, "kind"))

    @property
    def digest(self) -> str:
        """Return a stable digest without requiring raw content in the audit log."""
        return sha256(self.content.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ModelInput:
    """Structured input passed to a model-runner adapter."""

    request: AgentRequest
    context: tuple[ContextItem, ...] = ()


@dataclass(frozen=True)
class ToolCall:
    """A model-proposed tool call; it is not authorization to execute."""

    call_id: str
    tool_name: str
    arguments: Mapping[str, Any]
    reason: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "call_id", _required_text(self.call_id, "call_id"))
        object.__setattr__(self, "tool_name", _required_text(self.tool_name, "tool_name"))
        object.__setattr__(self, "reason", _required_text(self.reason, "reason"))
        arguments = dict(self.arguments)
        try:
            json.dumps(arguments, allow_nan=False)
        except (TypeError, ValueError) as exc:
            raise ValueError("tool arguments must be JSON serializable") from exc
        object.__setattr__(self, "arguments", arguments)


@dataclass(frozen=True)
class ModelProposal:
    """A structured runner response that separates explanation from actions."""

    summary: str
    response: str
    tool_calls: tuple[ToolCall, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "summary", _required_text(self.summary, "summary"))
        object.__setattr__(self, "tool_calls", tuple(self.tool_calls))
        call_ids = [call.call_id for call in self.tool_calls]
        if len(call_ids) != len(set(call_ids)):
            raise ValueError("tool call ids must be unique")


@dataclass(frozen=True)
class ToolExecution:
    """Result returned by a concrete tool implementation."""

    success: bool
    change: ChangeStatus
    summary: str
    evidence: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "summary", _required_text(self.summary, "summary"))
        object.__setattr__(self, "evidence", tuple(self.evidence))


@dataclass(frozen=True)
class ToolResult:
    """Tool execution associated with the proposal call that caused it."""

    call_id: str
    tool_name: str
    execution: ToolExecution


@dataclass(frozen=True)
class VerificationResult:
    """One deterministic check over the resulting local state."""

    name: str
    passed: bool
    summary: str
    evidence: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", _required_text(self.name, "name"))
        object.__setattr__(self, "summary", _required_text(self.summary, "summary"))
        object.__setattr__(self, "evidence", tuple(self.evidence))


@dataclass(frozen=True)
class ToolGrant:
    """Capabilities explicitly granted to one named tool."""

    tool_name: str
    capabilities: frozenset[Capability]

    def __post_init__(self) -> None:
        object.__setattr__(self, "tool_name", _required_text(self.tool_name, "tool_name"))
        object.__setattr__(self, "capabilities", frozenset(self.capabilities))


@dataclass(frozen=True)
class PermissionDecision:
    """Inspectable policy decision for one proposed tool call."""

    call_id: str
    tool_name: str
    allowed: bool
    required: frozenset[Capability]
    granted: frozenset[Capability]
    reason: str


@dataclass(frozen=True)
class TraceEvent:
    """One ordered audit event."""

    schema_version: int
    run_id: str
    sequence: int
    timestamp: datetime
    event_type: str
    data: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class EvaluationCheck:
    """One deterministic invariant checked against a run trace."""

    name: str
    passed: bool
    detail: str


@dataclass(frozen=True)
class EvaluationResult:
    """Aggregate evaluation of observable harness behaviour."""

    passed: bool
    checks: tuple[EvaluationCheck, ...]


@dataclass(frozen=True)
class AgentOutcome:
    """Terminal result returned to a future CLI composition layer."""

    run_id: str
    status: RunStatus
    proposal: ModelProposal | None
    tool_results: tuple[ToolResult, ...]
    verification_results: tuple[VerificationResult, ...]
    evaluation: EvaluationResult


class ModelRunner(Protocol):
    """Adapter boundary for local or remote model execution."""

    @property
    def identity(self) -> str:
        """Return a stable runner/model identifier for audit records."""
        ...

    def run(self, model_input: ModelInput) -> ModelProposal:
        """Return one structured proposal without executing it."""
        ...


class ContextProvider(Protocol):
    """Boundary for deterministic context and retrieval implementations."""

    @property
    def identity(self) -> str:
        """Return a stable provider identifier for audit records."""
        ...

    def retrieve(self, request: AgentRequest) -> Sequence[ContextItem]:
        """Return context with provenance for one request."""
        ...


class AgentTool(Protocol):
    """Controlled capability that can execute one authorized call."""

    @property
    def name(self) -> str:
        """Return the exact name used by proposals and grants."""
        ...

    def required_capabilities(
        self,
        call: ToolCall,
        request: AgentRequest,
    ) -> frozenset[Capability]:
        """Declare the capabilities required for this exact call."""
        ...

    def execute(self, call: ToolCall, request: AgentRequest) -> ToolExecution:
        """Execute one previously authorized call."""
        ...


class Verifier(Protocol):
    """Deterministic verification boundary for resulting local state."""

    @property
    def name(self) -> str:
        """Return the check name used in evidence."""
        ...

    def verify(
        self,
        request: AgentRequest,
        proposal: ModelProposal,
        tool_results: Sequence[ToolResult],
    ) -> VerificationResult:
        """Inspect resulting state and return evidence."""
        ...


class TraceStore(Protocol):
    """Append-only workflow history and audit boundary."""

    def record(self, run_id: str, event_type: str, data: Mapping[str, Any]) -> TraceEvent:
        """Append one event and return its assigned sequence."""
        ...

    def read(self, run_id: str) -> list[TraceEvent]:
        """Read one complete ordered run trace."""
        ...


def _required_text(value: str, label: str) -> str:
    text = value.strip()
    if not text:
        raise ValueError(f"{label} is required")
    return text
