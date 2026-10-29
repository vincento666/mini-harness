"""工具派发管线：校验 → 围栏与 approval → 执行。任一段的失败都是结果。"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from pydantic import ValidationError

from mini_harness.provider.contract import ToolCall
from mini_harness.tools.command_runner import SandboxUnavailable
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
    """一次派发的全部结论：给 `tool/result` 的结果，加上要不要写 `approval/*` 与 `error/fence`。

    `path` 与 `raw_path` 是围栏拒绝时写进 `error/fence` 的两个路径字段。
    """

    result: ToolResult
    approval: ApprovalDecision | None = None
    fence_code: FenceCode | None = None
    path: str | None = None
    raw_path: str | None = None


# 「要问人」的落盘钩子：提问之前先写 `approval/request`，写不进去就不问人（ADR-0002 第 9 条）。
ApprovalAsked = Callable[[ToolCall], bool]


async def dispatch_tool_call(
    call: ToolCall,
    registry: ToolRegistry,
    context: DispatchContext,
    approval_gate: ApprovalGate,
    on_approval_request: ApprovalAsked | None = None,
    on_stage: Callable[[str], None] | None = None,
) -> DispatchOutcome:
    """按六段固定顺序判定。校验失败不做围栏判定，围栏拒绝不执行。"""
    stages = on_stage if on_stage is not None else (lambda _name: None)

    def finished(outcome: DispatchOutcome) -> DispatchOutcome:
        stages("result")
        return outcome

    stages("pre-execute")
    definition = registry.lookup(call.name)
    if definition is None:
        return finished(
            DispatchOutcome(
                ToolResult(outcome="UNKNOWN_TOOL", content=f"未注册的工具：{call.name}")
            )
        )

    try:
        args = definition.args_model.model_validate(call.arguments)
    except ValidationError as exc:
        return finished(
            DispatchOutcome(
                ToolResult(
                    outcome="TOOL_ARGS_INVALID", content=f"工具 {call.name} 的入参不合法：{exc}"
                )
            )
        )

    stages("guard")
    decision = judge_fence(context, raw_path=args.target_path(), mutates=definition.mutates)
    if decision.outcome == "DENIED":
        return finished(
            DispatchOutcome(
                ToolResult(outcome="DENIED_BY_FENCE", content=decision.detail),
                fence_code=decision.code,
                path=decision.path,
                raw_path=decision.raw_path,
            )
        )

    approval: ApprovalDecision | None = None
    if decision.outcome == "NEEDS_APPROVAL":
        question = decision.detail or args.approval_detail()
        if on_approval_request is not None and not on_approval_request(call):
            return finished(
                DispatchOutcome(
                    ToolResult(
                        outcome="TOOL_IO_FAILED",
                        content=f"工具 {call.name} 的 approval 记录写不进日志",
                    )
                )
            )
        approval = await approval_gate.request(
            tool_call_id=call.id, tool_name=definition.name, detail=question
        )
        if approval != "APPROVED":
            return finished(
                DispatchOutcome(
                    ToolResult(
                        outcome="DENIED_BY_APPROVAL",
                        content=f"没有获得批准：{question}",
                    ),
                    approval=approval,
                    fence_code=_approval_denial_code(approval),
                    path=decision.path,
                    raw_path=decision.raw_path,
                )
            )

    stages("execute")
    try:
        result = await definition.run(args, context)
    except TimeoutError as exc:
        # `TimeoutError` 是 `OSError` 的子类：这一条 MUST 排在 `OSError` 之前。
        return finished(
            DispatchOutcome(
                ToolResult(outcome="TOOL_TIMEOUT", content=f"工具 {call.name} 执行超时：{exc}"),
                approval=approval,
            )
        )
    except asyncio.CancelledError:
        # ADR-0007：取消打断正在执行的调用，它也是结果；回合循环随后写 `tool/cancelled` 并收尾。
        return finished(
            DispatchOutcome(
                ToolResult(outcome="TOOL_CANCELLED", content=f"工具 {call.name} 的执行被打断"),
                approval=approval,
            )
        )
    except OSError as exc:
        # 不变量 B：执行段的 I/O 失败也是结果，不抛异常打断回合。
        return finished(
            DispatchOutcome(
                ToolResult(
                    outcome="TOOL_IO_FAILED", content=f"工具 {call.name} 读写文件失败：{exc}"
                ),
                approval=approval,
            )
        )
    except SandboxUnavailable as exc:
        # fail closed：没有受限 runner 就拒绝，绝不回退到未隔离执行。
        return finished(
            DispatchOutcome(
                ToolResult(
                    outcome="DENIED_BY_FENCE",
                    content=f"没有可用的受限命令执行器：{exc}",
                ),
                approval=approval,
                fence_code="SANDBOX_UNAVAILABLE",
            )
        )

    if result.outcome != "OK":
        return finished(DispatchOutcome(result, approval=approval))
    stages("post-execute")
    result = _post_execute(result)
    stages("finalizeContent")
    result = _finalize_content(result, definition.name, context.workspace)
    return finished(DispatchOutcome(result, approval=approval))


def _post_execute(result: ToolResult) -> ToolResult:
    """执行后的归一化；本切片保持原结果，预算/替换策略后续只在这里加。"""
    return result


def _finalize_content(result: ToolResult, tool_name: str, workspace: Path) -> ToolResult:
    """最终内容收尾：bash 的 16 KiB 尾部 + spill 只在这里做。"""
    if tool_name == "bash" and result.outcome == "OK":
        from mini_harness.tools.bash_tools import bound_bash_content

        return ToolResult(
            outcome=result.outcome,
            content=bound_bash_content(result.content, workspace),
        )
    return result


def _approval_denial_code(approval: ApprovalDecision) -> FenceCode:
    """「人拒了」与「问不到人」共用结果词 `DENIED_BY_APPROVAL`，但 `error/fence.code` 要分开。"""
    return "APPROVAL_DENIED" if approval == "DENIED" else "APPROVAL_UNAVAILABLE"
