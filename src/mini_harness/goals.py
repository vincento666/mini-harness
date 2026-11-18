"""目标域（M13）：持久快照、折叠与生命周期的纯函数。

事实只落在 `goal/updated` 事件里；本模块不做 IO，也不持有进程内状态。
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, field_validator, model_validator

from mini_harness.events.record import EventRecord

GoalPhase = Literal["active", "paused", "blocked", "complete"]

# 部署策略：缺省 32 轮、门槛 3 轮、允许并行任务（2026-11-17 人裁）。
DEFAULT_MAX_ROUNDS = 32
DEFAULT_BLOCKED_AFTER = 3


@dataclass(frozen=True)
class GoalPolicy:
    """`[goal]` 段的三键。工具与驱动都读这一份，不各自解释配置。"""

    max_rounds: int = DEFAULT_MAX_ROUNDS
    blocked_after_consecutive_rounds: int = DEFAULT_BLOCKED_AFTER
    allow_parallel_in_progress: bool = True


class GoalBlockReason(BaseModel):
    """阻塞的分类码与给人看的解释；两者都不许为空。"""

    code: str
    message: str

    @field_validator("code", "message")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("阻塞原因不能为空")
        return value


class GoalSnapshot(BaseModel):
    """一条 `goal/updated` 里的完整快照。"""

    id: str
    revision: int
    objective: str
    phase: GoalPhase
    max_rounds: int
    rounds_started: int
    blocked_reason: GoalBlockReason | None = None

    @field_validator("id", "objective")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("字段不能为空")
        return value

    @field_validator("revision", "max_rounds")
    @classmethod
    def _positive(cls, value: int) -> int:
        if value < 1:
            raise ValueError("必须是正整数")
        return value

    @field_validator("rounds_started")
    @classmethod
    def _non_negative(cls, value: int) -> int:
        if value < 0:
            raise ValueError("不能为负")
        return value

    @model_validator(mode="after")
    def _reason_matches_phase(self) -> GoalSnapshot:
        if self.phase == "blocked" and self.blocked_reason is None:
            raise ValueError("blocked 必须带 blocked_reason")
        if self.phase != "blocked" and self.blocked_reason is not None:
            raise ValueError("只有 blocked 才能带 blocked_reason")
        return self


def fold_goal(events: Sequence[EventRecord]) -> GoalSnapshot | None:
    """取最后一条 `goal/updated` 的载荷；`null` 表示清除，缺省表示没有目标。"""
    current: GoalSnapshot | None = None
    for event in events:
        if event.type != "goal/updated":
            continue
        payload: Any = event.payload.get("goal")
        current = None if payload is None else GoalSnapshot.model_validate(payload)
    return current


@dataclass
class GoalRuntime:
    """进程内的武装位：永不落盘（design D5）。会话启动与 `--resume` 之后一律为假。"""

    armed: bool = False


@dataclass(frozen=True)
class GoalRefusal:
    """一次被拒的改动：结果词 + 给人看的原因。不落事件。"""

    outcome: str
    detail: str


def _next(current: GoalSnapshot, **changes: Any) -> GoalSnapshot:
    """复制 + 改字段 + `revision + 1`（控制面动作才递增，轮次推进不走这里）。

    用 `model_validate` 而不是 `model_copy`：快照的形状约束（blocked 必带原因、
    非 blocked 不许带）要在每次改动上重新过一遍。
    """
    merged = {**current.model_dump(), **changes, "revision": current.revision + 1}
    return GoalSnapshot.model_validate(merged)


def edit_goal(
    current: GoalSnapshot, *, objective: str | None, max_rounds: int | None
) -> GoalSnapshot | GoalRefusal:
    """部分替换：空串与 0 视为省略；一个有效字段都没有就是参数错误。"""
    changes: dict[str, Any] = {}
    if objective:
        changes["objective"] = objective
    if max_rounds:
        changes["max_rounds"] = max_rounds
    if not changes:
        return GoalRefusal(
            "TOOL_ARGS_INVALID", "edit 至少要给一个有效字段（objective 或 max_rounds）"
        )
    return _next(current, **changes)


def pause_goal(current: GoalSnapshot) -> GoalSnapshot | GoalRefusal:
    if current.phase != "active":
        return GoalRefusal(
            "GOAL_INVALID_TRANSITION", f"不能从 {current.phase} 暂停；只有 active 可以"
        )
    return _next(current, phase="paused")


def complete_goal(current: GoalSnapshot) -> GoalSnapshot | GoalRefusal:
    if current.phase == "complete":
        return GoalRefusal("GOAL_INVALID_TRANSITION", "目标已经完成")
    return _next(current, phase="complete")


def resume_goal(current: GoalSnapshot, *, armed: bool) -> GoalSnapshot | GoalRefusal:
    """把目标放回 active 并（由调用方）武装。

    `paused` 留给人：工具面拒绝，`/goal resume` 才放行。轮次用尽时也拒——
    照 DSH 的 `resume`，先调大 `maxGoalRounds` 再来。
    """
    if current.phase == "paused":
        return GoalRefusal("GOAL_RESUME_BY_TOOL_DENIED", "暂停的目标只能由人的 /goal resume 恢复")
    if current.phase == "complete":
        return GoalRefusal("GOAL_INVALID_TRANSITION", "已完成的目标不能恢复")
    if current.phase == "active" and armed:
        return GoalRefusal("GOAL_INVALID_TRANSITION", "目标已经是 active 且已武装")
    if current.rounds_started >= current.max_rounds:
        return GoalRefusal(
            "GOAL_INVALID_TRANSITION",
            f"轮次已用尽（{current.rounds_started}/{current.max_rounds}）："
            "先调大 max_rounds 再 resume",
        )
    return _next(current, phase="active", blocked_reason=None)


def block_goal(
    current: GoalSnapshot, *, message: str, threshold: int
) -> GoalSnapshot | GoalRefusal:
    """模型自报阻塞：相位必须是 active，且必须已经跑满门槛轮数。"""
    if current.phase != "active":
        return GoalRefusal(
            "GOAL_INVALID_TRANSITION", f"不能从 {current.phase} 报阻塞；只有 active 可以"
        )
    if current.rounds_started < threshold:
        return GoalRefusal(
            "GOAL_BLOCK_TOO_EARLY",
            f"至少要跑满 {threshold} 轮才能报阻塞（当前 {current.rounds_started} 轮）",
        )
    return _next(
        current,
        phase="blocked",
        blocked_reason=GoalBlockReason(code="model-reported", message=message),
    )


MessageSource = dict[str, Any]


def entry_of(events: Sequence[EventRecord]) -> str:
    """会话入口：`session/start` 里写的那一个。缺省按人类入口读（旧日志兼容）。"""
    for event in events:
        if event.type == "session/start":
            entry = event.payload.get("entry")
            return entry if isinstance(entry, str) else "chat"
    return "chat"


def opened_by_human(events: Sequence[EventRecord]) -> bool:
    """当前段是否由人类来源开启：看最后一条 `segment/start` 之后的第一条 `user/message`。

    没有段首或其后没有驱动消息（`run` 的 prompt 住在 `session/start`）都按人类读，
    与 `message_source_of` 的旧日志回落同一规则。
    """
    start = -1
    for index, event in enumerate(events):
        if event.type == "segment/start":
            start = index
    for event in events[start + 1 :]:
        if event.type == "user/message":
            return str(message_source_of(event.payload)["kind"]) != "goal"
    return True


def message_source_of(payload: Mapping[str, Any]) -> MessageSource:
    """`user/message` 的来源；缺字段或认不出的 kind 一律按人类来源读（旧日志兼容）。"""
    source = payload.get("source")
    if isinstance(source, Mapping) and source.get("kind") == "goal":
        return dict(source)
    return {"kind": "user"}
