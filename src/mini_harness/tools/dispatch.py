"""工具派发管线：查表 → 执行或未命中 → 结果。失败也是结果。"""

from __future__ import annotations

from dataclasses import dataclass

from mini_harness.provider.contract import ToolCall
from mini_harness.tools.registry import ToolRegistry


@dataclass(frozen=True)
class ToolResult:
    """一次工具派发的结果。`outcome` 是成功或失败词；M1 里已注册工具的结果是 `NOT_IMPLEMENTED`。"""

    outcome: str
    content: str


async def dispatch_tool_call(call: ToolCall, registry: ToolRegistry) -> ToolResult:
    definition = registry.lookup(call.name)
    if definition is None:
        return ToolResult(outcome="UNKNOWN_TOOL", content=f"未注册的工具：{call.name}")
    return ToolResult(
        outcome="NOT_IMPLEMENTED",
        content=f"工具 {call.name} 在 M1 只有定义没有实现：{definition.description}",
    )
