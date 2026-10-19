"""工具派发管线：校验 → 围栏与 approval → 执行。任一段的失败都是结果。"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from pydantic import ValidationError

from mini_harness.provider.contract import ToolCall
from mini_harness.tools.fences import (
    ApprovalDecision,
    ApprovalGate,
    DispatchContext,
    FenceCode,
    judge_fence,
)
from mini_harness.tools.registry import ToolRegistry, ToolResult


@dataclass(frozen=True)
class DispatchOutcome:
    """一次派发的全部结论：给 `tool/result` 的结果，加上要不要写 `approval/*` 与 `error/fence`。"""

    result: ToolResult
    approval: ApprovalDecision | None = None
    fence_code: FenceCode | None = None


async def dispatch_tool_call(
    call: ToolCall,
    registry: ToolRegistry,
    context: DispatchContext,
    approval_gate: ApprovalGate,
) -> DispatchOutcome:
    """按固定顺序判定。校验失败不做围栏判定，围栏拒绝不执行。"""
    definition = registry.lookup(call.name)
    if definition is None:
        return DispatchOutcome(
            ToolResult(outcome="UNKNOWN_TOOL", content=f"未注册的工具：{call.name}")
        )

    try:
        args = definition.args_model.model_validate(call.arguments)
    except ValidationError as exc:
        return DispatchOutcome(
            ToolResult(outcome="TOOL_ARGS_INVALID", content=f"工具 {call.name} 的入参不合法：{exc}")
        )

    decision = judge_fence(context, raw_path=args.target_path() or "", mutates=definition.mutates)
    if decision.outcome == "DENIED":
        return DispatchOutcome(
            ToolResult(outcome="DENIED_BY_FENCE", content=decision.detail),
            fence_code=decision.code,
        )

    approval: ApprovalDecision | None = None
    if decision.outcome == "NEEDS_APPROVAL":
        approval = approval_gate.request(tool_name=definition.name, detail=decision.detail)
        if approval != "APPROVED":
            return DispatchOutcome(
                ToolResult(
                    outcome="DENIED_BY_APPROVAL",
                    content=f"没有获得批准：{decision.detail}",
                ),
                approval=approval,
                fence_code=_approval_denial_code(approval),
            )

    try:
        result = await definition.run(args, context)
    except TimeoutError as exc:
        # `TimeoutError` 是 `OSError` 的子类：这一条 MUST 排在 `OSError` 之前。
        return DispatchOutcome(
            ToolResult(outcome="TOOL_TIMEOUT", content=f"工具 {call.name} 执行超时：{exc}"),
            approval=approval,
        )
    except asyncio.CancelledError:
        # ADR-0007：取消打断正在执行的调用，它也是结果；回合循环随后写 `tool/cancelled` 并收尾。
        return DispatchOutcome(
            ToolResult(outcome="TOOL_CANCELLED", content=f"工具 {call.name} 的执行被打断"),
            approval=approval,
        )
    except OSError as exc:
        # 不变量 B：执行段的 I/O 失败也是结果，不抛异常打断回合。
        return DispatchOutcome(
            ToolResult(outcome="TOOL_IO_FAILED", content=f"工具 {call.name} 读写文件失败：{exc}"),
            approval=approval,
        )

    return DispatchOutcome(result, approval=approval)


def _approval_denial_code(approval: ApprovalDecision) -> FenceCode:
    """「人拒了」与「问不到人」共用结果词 `DENIED_BY_APPROVAL`，但 `error/fence.code` 要分开。"""
    return "APPROVAL_DENIED" if approval == "DENIED" else "APPROVAL_UNAVAILABLE"
