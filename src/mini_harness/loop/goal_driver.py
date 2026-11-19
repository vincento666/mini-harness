"""目标轮次驱动（M13）：一个段结束后要不要再开一段，以及开段要带什么。

判定只看三样：当前快照、进程内的武装位、本段的 `stop_reason`。不看时间、不看队列——
mini 没有 inbox，段结束就是唯一可能的驱动时机（design D3）。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from mini_harness.goals import GoalSnapshot

# 这些收尾不再开新段：三个是中止/失败，两个是「本段已经撞到自己的上限」。
# 它们与 `turn/end.stop_reason` 的词表同源，只是驱动只关心「还能不能继续往前推」。
NO_CONTINUE_REASONS: frozenset[str] = frozenset(
    {
        "ABORTED",
        "FENCE_DENIED",
        "PROVIDER_ERROR",
        "CONTEXT_WINDOW_EXCEEDED",
        "MAX_TURNS",
    }
)

RoundDecisionKind = Literal["stop", "continue", "exhausted", "awaiting_input"]


@dataclass(frozen=True)
class RoundDecision:
    """段之后的四选一：停、续下一轮、额度用尽（落 blocker）、等人回答问题。"""

    kind: RoundDecisionKind
    goal: GoalSnapshot | None = None
    round: int = 0


def next_round(
    *,
    goal: GoalSnapshot | None,
    armed: bool,
    stop_reason: str,
    question_pending: bool = False,
) -> RoundDecision:
    """`phase == active` + 已武装 + 该收尾允许继续，才开新段；到上限则落 blocker。

    `question_pending` 是本段末尾仍未回答的问题：自动轮次里没人能回答，继续开段只会
    白烧额度，所以先停、由入口把目标置 `paused`。额度用尽优先（那是更硬的事实）。
    """
    if goal is None or goal.phase != "active" or not armed:
        return RoundDecision("stop", goal)
    if stop_reason in NO_CONTINUE_REASONS:
        return RoundDecision("stop", goal)
    if goal.rounds_started >= goal.max_rounds:
        return RoundDecision("exhausted", goal, goal.rounds_started + 1)
    if question_pending:
        return RoundDecision("awaiting_input", goal, goal.rounds_started + 1)
    return RoundDecision("continue", goal, goal.rounds_started + 1)
