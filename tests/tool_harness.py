"""seam ③ 的派发 helper：不经回合循环，把一次调用跑完「校验 → 围栏 → 执行」三段。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from mini_harness.loop.settings import ApprovalMode, SandboxLevel, SessionSettings
from mini_harness.provider.contract import ToolCall
from mini_harness.tools.dispatch import DispatchOutcome, dispatch_tool_call
from mini_harness.tools.fences import ApprovalDecision, DispatchContext
from mini_harness.tools.file_tools import file_tool_definitions
from mini_harness.tools.registry import ToolRegistry


class _ApprovingGate:
    """seam ③ 判的是工具契约，approval 在这里不是被测对象。"""

    def request(self, *, tool_name: str, detail: str) -> ApprovalDecision:
        return "APPROVED"


async def dispatch_call(
    workspace: Path,
    name: str,
    arguments: dict[str, Any],
    *,
    sandbox: SandboxLevel = "workspace-write",
    approval: ApprovalMode = "auto",
    read_paths: frozenset[str] = frozenset(),
) -> DispatchOutcome:
    settings = SessionSettings(
        workspace=workspace,
        provider_name="mock",
        max_turns=8,
        sandbox=sandbox,
        approval=approval,
    )
    context = DispatchContext.from_settings(settings, read_paths=read_paths)
    call = ToolCall(id="c1", name=name, arguments=arguments)
    registry = ToolRegistry(file_tool_definitions())
    return await dispatch_tool_call(call, registry, context, _ApprovingGate())
