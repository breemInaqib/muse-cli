"""Default-deny permission decisions for proposed agent tool calls."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from .contracts import AgentRequest, AgentTool, Capability, PermissionDecision, ToolCall, ToolGrant


@dataclass(frozen=True)
class PermissionPolicy:
    """Explicit grants evaluated before any tool in a proposal executes."""

    grants: tuple[ToolGrant, ...] = ()

    def __init__(self, grants: Iterable[ToolGrant] = ()) -> None:
        normalized = tuple(grants)
        names = [grant.tool_name for grant in normalized]
        if len(names) != len(set(names)):
            raise ValueError("permission grants must have unique tool names")
        object.__setattr__(self, "grants", normalized)

    def decide(
        self,
        tool: AgentTool,
        call: ToolCall,
        request: AgentRequest,
    ) -> PermissionDecision:
        """Return an inspectable, fail-closed decision for one call."""
        try:
            required = frozenset(tool.required_capabilities(call, request))
        except Exception as exc:
            return PermissionDecision(
                call_id=call.call_id,
                tool_name=call.tool_name,
                allowed=False,
                required=frozenset(),
                granted=self._granted_to(call.tool_name),
                reason=f"capability declaration failed: {type(exc).__name__}",
            )

        granted = self._granted_to(call.tool_name)
        if not required:
            return PermissionDecision(
                call_id=call.call_id,
                tool_name=call.tool_name,
                allowed=False,
                required=required,
                granted=granted,
                reason="tool declared no capabilities",
            )
        missing = required - granted
        if missing:
            names = ", ".join(sorted(capability.value for capability in missing))
            return PermissionDecision(
                call_id=call.call_id,
                tool_name=call.tool_name,
                allowed=False,
                required=required,
                granted=granted,
                reason=f"capabilities not granted: {names}",
            )
        return PermissionDecision(
            call_id=call.call_id,
            tool_name=call.tool_name,
            allowed=True,
            required=required,
            granted=granted,
            reason="all required capabilities explicitly granted",
        )

    def describe(self) -> list[dict[str, object]]:
        """Return a stable, JSON-ready representation for run evidence."""
        return [
            {
                "tool_name": grant.tool_name,
                "capabilities": sorted(capability.value for capability in grant.capabilities),
            }
            for grant in sorted(self.grants, key=lambda item: item.tool_name)
        ]

    def _granted_to(self, tool_name: str) -> frozenset[Capability]:
        for grant in self.grants:
            if grant.tool_name == tool_name:
                return grant.capabilities
        return frozenset()
