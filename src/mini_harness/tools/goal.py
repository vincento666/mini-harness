"""目标工具（M13）：`get_goal` 与 `create_goal`。`update_goal` 在后续切片。

工具只读派发上下文里的事实（快照、来源、入口），自己不做日志折叠；唯一的写是把
`goal/updated` 追加进日志——与 `ask_user` 同一形状，因为 CAS 必须「读一次、写一次」。
"""

from __future__ import annotations

import json
import uuid
from typing import Literal, cast

from pydantic import Field, model_validator

from mini_harness.events.writer import LogWriteFailure
from mini_harness.goals import (
    GoalRefusal,
    GoalSnapshot,
    block_goal,
    complete_goal,
    edit_goal,
    pause_goal,
    resume_goal,
)
from mini_harness.tools.fences import DispatchContext
from mini_harness.tools.registry import (
    ToolArgs,
    ToolDefinition,
    ToolOutcome,
    ToolResult,
)


class UpdateGoalArgs(ToolArgs):
    """一次带比较交换的改动：`goal_id` + `revision` 必须与当前快照一致。"""

    goal_id: str = Field(description="目标的 id，取自 get_goal")
    revision: int = Field(ge=1, description="刚才读到的 revision；不一致会被拒")
    action: Literal["edit", "pause", "resume", "complete", "blocked"]
    objective: str | None = Field(default=None, description="edit 时的新目标正文")
    max_rounds: int | None = Field(default=None, ge=0, description="edit 时的轮次上限")
    blocked_reason: str | None = Field(default=None, description="blocked 时的原因原文")

    @model_validator(mode="after")
    def _blocked_needs_a_reason(self) -> UpdateGoalArgs:
        if self.action == "blocked" and not (self.blocked_reason or "").strip():
            raise ValueError("blocked 必须给 blocked_reason")
        return self


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
        # 部署上限是硬顶：模型可以要得更少，不能要得更多（否则预算形同虚设）。
        max_rounds=policy.max_rounds
        if args.max_rounds is None
        else min(args.max_rounds, policy.max_rounds),
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


# 只有这四个动作要「人类开口的段」；complete / blocked 是模型在轮次里自己收尾的口子。
_HUMAN_ONLY_ACTIONS = frozenset({"edit", "pause", "resume"})


async def _update_goal(args: UpdateGoalArgs, context: DispatchContext) -> ToolResult:
    if args.action in _HUMAN_ONLY_ACTIONS:
        if context.entry == "subagent":
            return ToolResult("GOAL_AUTHORITY_REQUIRED", "子会话没有改写目标的权威")
        if not context.human_driven:
            return ToolResult(
                "GOAL_AUTHORITY_REQUIRED",
                "只有人类开口的段才能改写目标；目标轮次里不行",
            )
    current = context.goal
    if current is None or current.id != args.goal_id or current.revision != args.revision:
        expected = "没有目标" if current is None else f"{current.id}@{current.revision}"
        return ToolResult(
            "GOAL_REF_STALE",
            f"目标引用过期：当前是 {expected}，收到 {args.goal_id}@{args.revision}",
        )

    armed = _armed(context)
    if args.action == "edit":
        result: GoalSnapshot | GoalRefusal = edit_goal(
            current,
            objective=args.objective,
            max_rounds=args.max_rounds,
            ceiling=context.goal_policy.max_rounds,
        )
    elif args.action == "pause":
        result = pause_goal(current)
    elif args.action == "complete":
        result = complete_goal(current)
    elif args.action == "resume":
        result = resume_goal(current, armed=armed)
    else:
        result = block_goal(
            current,
            message=args.blocked_reason or "",
            threshold=context.goal_policy.blocked_after_consecutive_rounds,
        )
    if isinstance(result, GoalRefusal):
        return ToolResult(cast(ToolOutcome, result.outcome), result.detail)

    session = context.session
    if session is None:
        return ToolResult("TOOL_IO_FAILED", "没有会话日志，改动没有落盘")
    written = session.log.append("goal/updated", {"goal": result.model_dump(exclude_none=True)})
    if isinstance(written, LogWriteFailure):
        return ToolResult("TOOL_IO_FAILED", "改动写不进日志，本次操作作废")
    if args.action == "resume":
        session.goal_runtime.armed = True
    elif args.action in {"pause", "complete", "blocked"}:
        session.goal_runtime.armed = False
    return ToolResult("OK", _view(context, result))


def goal_tool_definitions() -> list[ToolDefinition]:
    """三个目标工具；都读当前快照再改，因此串行派发。顺序即 `session/start` 里的工具名顺序。"""
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
        ToolDefinition(
            name="update_goal",
            description="按 id+revision 改写目标：edit / pause / resume / complete / blocked。",
            args_model=UpdateGoalArgs,
            mutates=False,
            concurrency="exclusive",
            run=_update_goal,
        ),
    ]
