"""0.1 的 v1 金样本：改名与 schema 上迁之前冻结的事实。

它的作用不是「多一条断言」，而是**在 v1 消失之前留一份不可变的输入**：
`align-turn-step-naming` 的每一步改名都要让它继续通过——过了，说明旧日志还能读；
不过，说明兼容层破了。
"""

from __future__ import annotations

from pathlib import Path

from mini_harness.events import read_events
from mini_harness.events.fold import fold
from mini_harness.goals import fold_goal

FIXTURE = Path(__file__).parent / "fixtures" / "logs" / "v1-goal-tools.jsonl"


def test_the_v1_sample_parses_and_covers_the_naming_surface() -> None:
    records = read_events(FIXTURE)

    assert isinstance(records, list)
    types = {record.type for record in records}
    # 这份样本要同时覆盖：段边界、回合边界、goal 快照、工具调用与结果。
    assert {
        "session/start",
        "turn/start",
        "turn/end",
        "step/start",
        "step/end",
        "context/assembled",
        "goal/updated",
        "user/message",
        "tool/call",
        "tool/result",
        "session/end",
    } <= types


def test_the_v1_sample_still_folds_into_a_context_and_a_goal() -> None:
    records = read_events(FIXTURE)
    assert isinstance(records, list)

    context = fold(records)
    assert context.messages
    goal = fold_goal(records)
    assert goal is not None
    assert goal.phase == "blocked"
    assert goal.blocked_reason is not None
    assert goal.blocked_reason.code == "round-limit"
    assert goal.rounds_started == 2
