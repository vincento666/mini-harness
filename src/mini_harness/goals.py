"""目标域（M13）：持久快照、折叠与生命周期的纯函数。

事实只落在 `goal/updated` 事件里；本模块不做 IO，也不持有进程内状态。
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, field_validator, model_validator

from mini_harness.events.record import EventRecord

GoalPhase = Literal["active", "paused", "blocked", "complete"]

# 部署策略：缺省 32 轮（同时是模型可请求的硬顶）、门槛 3 轮、允许并行任务（2026-11-17 人裁）。
DEFAULT_MAX_ROUNDS = 32
DEFAULT_BLOCKED_AFTER = 3
# 停滞闸门默认开、阈值 2（2026-11-20 三裁）：连续两个 goal 轮次零工具调用才停。
# 一轮可能只是「想清楚再答」，两轮连续空转更像死循环；阈值取 1 会误杀研究型轮次
# （读文件后判断没新内容），取 3 以上则白烧额度。`0` 表示关闭（完全对齐 DSH）。
DEFAULT_STALL_ROUNDS = 2


@dataclass(frozen=True)
class GoalPolicy:
    """`[goal]` 节的四键。工具与驱动都读这一份，不各自解释配置。"""

    max_rounds: int = DEFAULT_MAX_ROUNDS
    blocked_after_consecutive_rounds: int = DEFAULT_BLOCKED_AFTER
    allow_parallel_in_progress: bool = True
    stall_rounds: int = DEFAULT_STALL_ROUNDS


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
    """进程内状态：武装位与「连续空转轮数」。永不落盘（design D5）。"""

    armed: bool = False
    # 连续多少个 goal 轮次零工具调用；有任何动作或人类轮插入都清零，
    # 由 `settle_segment` 维护。只有 `stall_rounds > 0` 时才有意义。
    idle_rounds: int = 0


@dataclass(frozen=True)
class GoalRefusal:
    """一次被拒的改动：结果词 + 给人看的原因。不落事件。"""

    outcome: str
    detail: str


@dataclass(frozen=True)
class GoalRound:
    """一轮续跑的输入：快照加轮号。正文与来源都由这一对派生，避免两处写歪。"""

    goal: GoalSnapshot
    round: int


def render_goal_round(goal: GoalSnapshot, round_number: int) -> str:
    """goal 来源消息的正文（spec：`<goal_round>` 块，至少 `Objective` 与 `Round` 两行）。

    末行是终局约束（D14）：本轮必须留下一个可观察的动作，不能只用文字宣告完成。
    模型仍可能不照做，所以驱动侧另有「连续零工具调用」的停滞闸门；提示词只是第一道。
    """
    return (
        "<goal_round>\n"
        f"Objective: {json.dumps(goal.objective, ensure_ascii=False)}\n"
        f"Round: {round_number}/{goal.max_rounds}\n"
        "以工作区、工具结果与持久状态为准：完成前取证。\n"
        "本轮结束前必须三选一：完成则调用 update_goal 标 complete；已达阻塞门槛则调用 "
        "update_goal 标 blocked；否则现在就执行下一步的具体动作。只复述计划、不调用任何"
        "工具会被记为停滞；连续两轮如此将停止自动推进。\n"
        "</goal_round>"
    )


def advance_round(current: GoalSnapshot, round_number: int) -> GoalSnapshot:
    """轮次推进：只写 `rounds_started`，`revision` 不动。

    照 DSH：`roundsStarted` 是 `GoalView` 的派生值，轮次不是一次 goal 变更。改 `revision`
    会让模型在轮内拿到的引用立刻过期。
    """
    merged = {**current.model_dump(), "rounds_started": round_number}
    return GoalSnapshot.model_validate(merged)


def abort_goal(current: GoalSnapshot) -> GoalSnapshot:
    """人取消：`active` → `paused`。调用方已判过相位，所以这里不设拒绝分支。"""
    return _next(current, phase="paused")


def exhaust_goal(current: GoalSnapshot) -> GoalSnapshot:
    """额度用尽：系统写 `blocked{round-limit}`，`revision + 1`（控制面动作）。"""
    return _next(
        current,
        phase="blocked",
        blocked_reason=GoalBlockReason(
            code="round-limit",
            message=f"轮次已用尽（{current.rounds_started}/{current.max_rounds}）",
        ),
    )


def _next(current: GoalSnapshot, **changes: Any) -> GoalSnapshot:
    """复制 + 改字段 + `revision + 1`（控制面动作才递增，轮次推进不走这里）。

    用 `model_validate` 而不是 `model_copy`：快照的形状约束（blocked 必带原因、
    非 blocked 不许带）要在每次改动上重新过一遍。
    """
    merged = {**current.model_dump(), **changes, "revision": current.revision + 1}
    return GoalSnapshot.model_validate(merged)


def edit_goal(
    current: GoalSnapshot,
    *,
    objective: str | None,
    max_rounds: int | None,
    ceiling: int | None = None,
) -> GoalSnapshot | GoalRefusal:
    """部分替换：空串与 0 视为省略；一个有效字段都没有就是参数错误。

    `ceiling` 是部署上限：请求值超过它时按它落，避免模型用一个大数字绕开预算。
    人类命令同样走这条上限——要真正跑更多轮，改部署配置。
    """
    changes: dict[str, Any] = {}
    if objective:
        changes["objective"] = objective
    if max_rounds:
        changes["max_rounds"] = max_rounds if ceiling is None else min(max_rounds, ceiling)
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


def resume_goal(
    current: GoalSnapshot, *, armed: bool, human: bool = False
) -> GoalSnapshot | GoalRefusal:
    """把目标放回 active 并（由调用方）武装。

    `paused` 留给人：工具面拒绝（`GOAL_RESUME_BY_TOOL_DENIED`），`/goal resume`
    （`human=True`）才放行。轮次用尽时都拒——照 DSH 的 `resume`，先调大
    `maxGoalRounds` 再来。
    """
    if current.phase == "paused" and not human:
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


def goal_round_defect(events: Sequence[EventRecord]) -> str | None:
    """检查 goal 轮次的自洽，返回第一条缺陷的说明；`None` 表示自洽。

    规则来自 spec 的「轮次是 goal 来源的用户消息」：轮号为正、同一目标内不跳号、不超上限、
    `revision` 与当前快照一致、目标已停就不再出现轮次消息。另加一条覆盖「改了
    `rounds_started`」的读数：每条快照的 `rounds_started` 必须等于此前已出现的轮次条数。
    """
    seen: dict[str, int] = {}
    current: GoalSnapshot | None = None
    for event in events:
        if event.type == "goal/updated":
            payload: Any = event.payload.get("goal")
            current = None if payload is None else GoalSnapshot.model_validate(payload)
            if current is not None and current.rounds_started != seen.get(current.id, 0):
                return (
                    f"seq={event.seq} 的 goal/updated 写 rounds_started="
                    f"{current.rounds_started}，此前只有 {seen.get(current.id, 0)} 条轮次消息"
                )
            continue
        if event.type != "user/message":
            continue
        source = message_source_of(event.payload)
        if source["kind"] != "goal":
            continue
        goal_id = source.get("goal_id")
        round_number = source.get("round")
        revision = source.get("revision")
        if not isinstance(goal_id, str) or not isinstance(round_number, int):
            return f"seq={event.seq} 的 goal 消息来源字段不完整"
        if not isinstance(revision, int):
            return f"seq={event.seq} 的 goal 消息缺 revision"
        if round_number < 1:
            return f"seq={event.seq} 的 goal 消息轮号为 {round_number}，必须为正"
        if current is None or current.id != goal_id:
            return f"seq={event.seq} 的 goal 消息指向 {goal_id}，当前没有这个目标"
        if current.phase != "active":
            return f"seq={event.seq} 的 goal 消息落在 {current.phase} 之后"
        if revision != current.revision:
            return f"seq={event.seq} 的 goal 消息 revision={revision}，当前是 {current.revision}"
        expected = seen.get(goal_id, 0) + 1
        if round_number != expected:
            return f"seq={event.seq} 的 goal 消息轮号 {round_number}，按前序应为 {expected}"
        if round_number > current.max_rounds:
            return f"seq={event.seq} 的 goal 消息轮号 {round_number} 超过上限 {current.max_rounds}"
        seen[goal_id] = round_number
    return None


def entry_of(events: Sequence[EventRecord]) -> str:
    """会话入口：`session/start` 里写的那一个。缺省按人类入口读（旧日志兼容）。"""
    for event in events:
        if event.type == "session/start":
            entry = event.payload.get("entry")
            return entry if isinstance(entry, str) else "chat"
    return "chat"


def opened_by_human(events: Sequence[EventRecord]) -> bool:
    """当前轮是否由人类来源开启：看最后一条 `turn/start` 之后的第一条 `user/message`。

    没有轮首或其后没有驱动消息（`run` 的 prompt 住在 `session/start`）都按人类读，
    与 `message_source_of` 的旧日志回落同一规则。
    """
    start = -1
    for index, event in enumerate(events):
        if event.type == "turn/start":
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
