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


MessageSource = dict[str, Any]


def message_source_of(payload: Mapping[str, Any]) -> MessageSource:
    """`user/message` 的来源；缺字段或认不出的 kind 一律按人类来源读（旧日志兼容）。"""
    source = payload.get("source")
    if isinstance(source, Mapping) and source.get("kind") == "goal":
        return dict(source)
    return {"kind": "user"}
