"""目标工具（M13）：`get_goal` 与 `create_goal`。`update_goal` 在后续切片。

工具只读派发上下文里的事实（快照、来源、入口），自己不做日志折叠；唯一的写是把
`goal/updated` 追加进日志——与 `ask_user` 同一形状，因为 CAS 必须「读一次、写一次」。
"""

from __future__ import annotations

import json
import uuid

from pydantic import Field

from mini_harness.events.writer import LogWriteFailure
from mini_harness.goals import GoalSnapshot
from mini_harness.tools.fences import DispatchContext
from mini_harness.tools.registry import ToolArgs, ToolDefinition, ToolResult


class GetGoalArgs(ToolArgs):
    """无参数：读当前目标。"""


class CreateGoalArgs(ToolArgs):
    """创建一个目标；`max_rounds` 省略时用部署默认。"""

    objective: str = Field(description="目标正文，一句话说清要做成什么")
    max_rounds: int | None = Field(
        default=None, gt=0, description="自动续跑的轮次上限；省略用部署默认"
    )


def _armed(context: DispatchContext) -> bool:
    return context.session is not None and context.session.goal_runtime.armed


def _view(context: DispatchContext, goal: GoalSnapshot | None) -> str:
    """工具结果：无目标只有 `{"goal": null}`；有目标再加 `armed`（它不落盘）。"""
    if goal is None:
        return json.dumps({"goal": None}, ensure_ascii=False)
    payload = {"goal": goal.model_dump(exclude_none=True), "armed": _armed(context)}
    return json.dumps(payload, ensure_ascii=False)


async def _get_goal(args: GetGoalArgs, context: DispatchContext) -> ToolResult:
    return ToolResult("OK", _view(context, context.goal))


async def _create_goal(args: CreateGoalArgs, context: DispatchContext) -> ToolResult:
    if context.entry == "subagent":
        return ToolResult("GOAL_AUTHORITY_REQUIRED", "子会话没有创建目标的权威")
    if not context.human_driven:
        return ToolResult("GOAL_AUTHORITY_REQUIRED", "只有人类开口的段才能创建目标；目标轮次里不行")
    current = context.goal
    if current is not None and current.phase != "complete":
        return ToolResult(
            "GOAL_ALREADY_ACTIVE",
            f"已有未完成的目标 {current.id}（{current.phase}）：先完成或清除它",
        )
    policy = context.goal_policy
    snapshot = GoalSnapshot(
        id=f"g{uuid.uuid4().hex[:12]}",
        revision=1,
        objective=args.objective,
        phase="active",
        max_rounds=policy.max_rounds if args.max_rounds is None else args.max_rounds,
        rounds_started=0,
    )
    session = context.session
    if session is None:
        return ToolResult("TOOL_IO_FAILED", "没有会话日志，目标没有落盘")
    log = session.log
    written = log.append("goal/updated", {"goal": snapshot.model_dump(exclude_none=True)})
    if isinstance(written, LogWriteFailure):
        return ToolResult("TOOL_IO_FAILED", "目标写不进日志，本次创建作废")
    # 创建即武装：DSH 的 `create` 就是 `commitSnapshot(..., 'armed')`
    # （packages/goal/goal/src/index.ts:300-321），否则目标永远不动。
    session.goal_runtime.armed = True
    return ToolResult("OK", _view(context, snapshot))


def goal_tool_definitions() -> list[ToolDefinition]:
    """两个目标工具；都会读当前快照再改，因此串行派发。"""
    return [
        ToolDefinition(
            name="get_goal",
            description='读当前目标：无目标时返回 {"goal": null}，否则含快照与 armed。',
            args_model=GetGoalArgs,
            mutates=False,
            concurrency="exclusive",
            run=_get_goal,
        ),
        ToolDefinition(
            name="create_goal",
            description="创建一个目标并开始自动续跑；已有未完成目标时拒绝（单目标）。",
            args_model=CreateGoalArgs,
            mutates=False,
            concurrency="exclusive",
            run=_create_goal,
        ),
    ]
