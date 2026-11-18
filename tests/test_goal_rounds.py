"""seam ①⑦：段结束后的目标续跑判定、四事件顺序与额度用尽。"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from mini_harness.events import EventRecord, read_events
from mini_harness.goals import GoalSnapshot, fold_goal
from mini_harness.loop import ENTRY_RUN, run_session_env
from mini_harness.loop.goal_driver import next_round
from mini_harness.provider import AssistantTurn, ProviderFailure, ToolCall
from mini_harness.tools import ToolRegistry
from mini_harness.tools.assistant import assistant_tool_definitions
from mini_harness.tools.goal import goal_tool_definitions
from tool_harness import build_session_env

OBJECTIVE = "修好失败的用例"


def _registry() -> ToolRegistry:
    return ToolRegistry([*assistant_tool_definitions(), *goal_tool_definitions()])


class _Scripted:
    """按调用序号回答：第 1 次建目标，`complete_at` 那次标完成，其余收尾。

    目标 id 由工具生成，所以「标完成」必须在运行时读日志取 id 与 revision——
    这同时把 CAS 走了一遍：轮次不改 `revision`，模型读到的值下一轮仍然有效。
    """

    def __init__(
        self,
        *,
        max_rounds: int,
        complete_at: int | None = None,
        abort_at: int | None = None,
        fail_at: int | None = None,
    ) -> None:
        self.max_rounds = max_rounds
        self.complete_at = complete_at
        self.abort_at = abort_at
        self.fail_at = fail_at
        self.cancel: asyncio.Event | None = None
        self.log_path: Path | None = None
        self.calls = 0

    async def generate(
        self, messages: Any, tools: Any, signal: Any, on_delta: Any = None
    ) -> AssistantTurn | ProviderFailure:
        self.calls += 1
        if self.abort_at is not None and self.calls == self.abort_at:
            assert self.cancel is not None
            self.cancel.set()
        if self.fail_at is not None and self.calls == self.fail_at:
            return ProviderFailure("PROVIDER_HTTP_STATUS", "上游 400")
        if self.calls == 1:
            return AssistantTurn(
                content="先立个目标",
                finish_reason="tool_calls",
                tool_calls=[
                    ToolCall(
                        id="c1",
                        name="create_goal",
                        arguments={"objective": OBJECTIVE, "max_rounds": self.max_rounds},
                    )
                ],
            )
        if self.complete_at is not None and self.calls == self.complete_at:
            assert self.log_path is not None
            goal = fold_goal(read_events(self.log_path))
            assert goal is not None
            return AssistantTurn(
                content="做完了",
                finish_reason="tool_calls",
                tool_calls=[
                    ToolCall(
                        id="c2",
                        name="update_goal",
                        arguments={
                            "goal_id": goal.id,
                            "revision": goal.revision,
                            "action": "complete",
                        },
                    )
                ],
            )
        return AssistantTurn(content="这一步做完了", finish_reason="stop")


async def _run(
    tmp_path: Path,
    *,
    max_rounds: int,
    complete_at: int | None = None,
    abort_at: int | None = None,
    fail_at: int | None = None,
) -> tuple[list[EventRecord], GoalSnapshot | None, Any, Any]:
    provider = _Scripted(
        max_rounds=max_rounds, complete_at=complete_at, abort_at=abort_at, fail_at=fail_at
    )
    log, env = build_session_env(
        tmp_path, "s-goal-rounds", provider, registry=_registry(), max_turns=8
    )
    provider.log_path = log.path
    cancel = asyncio.Event()
    provider.cancel = cancel
    outcome = await run_session_env(prompt="把这件活干完", entry=ENTRY_RUN, env=env, cancel=cancel)
    return read_events(log.path), fold_goal(read_events(log.path)), outcome, env


def _segments(records: list[EventRecord]) -> dict[str, list[EventRecord]]:
    """按 `segment/start` 切段：段外的记录（`session/*`）不算进任何段。"""
    out: dict[str, list[EventRecord]] = {}
    current: str | None = None
    for record in records:
        if record.type == "segment/start":
            current = str(record.payload.get("segment_id"))
            out[current] = []
        elif record.type in {"session/start", "session/end"}:
            continue
        if current is not None:
            out[current].append(record)
    return out


def _goal_updates(records: list[EventRecord]) -> list[dict[str, Any]]:
    return [record.payload["goal"] for record in records if record.type == "goal/updated"]


async def test_three_rounds_run_in_order_and_stop_at_the_cap(tmp_path: Path) -> None:
    records, goal, outcome, env = await _run(tmp_path, max_rounds=3)

    segments = _segments(records)
    assert list(segments) == ["s1", "s2", "s3", "s4"]
    assert [record.type for record in records].count("segment/end") == 4

    goal_messages = [
        record
        for record in records
        if record.type == "user/message" and record.payload.get("source", {}).get("kind") == "goal"
    ]
    assert [message.payload["source"]["round"] for message in goal_messages] == [1, 2, 3]
    assert [message.payload["source"]["revision"] for message in goal_messages] == [1, 1, 1]
    assert len({message.payload["source"]["goal_id"] for message in goal_messages}) == 1
    assert goal is not None

    for round_number in (1, 2, 3):
        segment = segments[f"s{round_number + 1}"]
        types = [record.type for record in segment]
        assert types[:5] == [
            "segment/start",
            "user/message",
            "turn/start",
            "goal/updated",
            "context/assembled",
        ]
        assert "model/request" in types
        snapshot = segment[3].payload["goal"]
        assert snapshot["rounds_started"] == round_number
        assert snapshot["revision"] == 1
        assert snapshot["phase"] == "active"

    second = segments["s3"][1].payload
    assert f'Objective: "{OBJECTIVE}"' in second["content"]
    assert "Round: 2/3" in second["content"]

    # 正文真的进了模型：该轮第一个装配点里的最后一条 user 消息就是它。
    assembled = next(
        record for record in segments["s3"] if record.type == "context/assembled"
    ).payload
    user_messages = [item for item in assembled["messages"] if item["role"] == "user"]
    assert user_messages[-1]["content"] == second["content"]

    assert goal.phase == "blocked"
    assert goal.blocked_reason is not None
    assert goal.blocked_reason.code == "round-limit"
    assert goal.rounds_started == 3
    assert goal.revision == 2
    assert env.goal_runtime.armed is False
    assert outcome.stop_reason == "MODEL_COMPLETED"


async def test_a_completed_goal_no_longer_opens_segments(tmp_path: Path) -> None:
    records, goal, outcome, _ = await _run(tmp_path, max_rounds=3, complete_at=4)

    segments = _segments(records)
    assert list(segments) == ["s1", "s2", "s3"]
    assert goal is not None
    assert goal.phase == "complete"
    assert goal.rounds_started == 2
    assert goal.revision == 2
    assert [record.type for record in records].count("segment/start") == 3
    assert outcome.stop_reason == "MODEL_COMPLETED"


def test_the_round_decision_only_looks_at_the_snapshot_the_arm_and_the_stop_reason() -> None:
    active = GoalSnapshot(
        id="g1", revision=1, objective=OBJECTIVE, phase="active", max_rounds=3, rounds_started=1
    )

    assert next_round(goal=None, armed=True, stop_reason="MODEL_COMPLETED").kind == "stop"
    assert next_round(goal=active, armed=False, stop_reason="MODEL_COMPLETED").kind == "stop"
    for stop_reason in (
        "ABORTED",
        "FENCE_DENIED",
        "PROVIDER_ERROR",
        "CONTEXT_WINDOW_EXCEEDED",
        "MAX_TURNS",
    ):
        assert next_round(goal=active, armed=True, stop_reason=stop_reason).kind == "stop"
    paused = active.model_copy(update={"phase": "paused"})
    assert next_round(goal=paused, armed=True, stop_reason="MODEL_COMPLETED").kind == "stop"

    decision = next_round(goal=active, armed=True, stop_reason="MODEL_COMPLETED")
    assert (decision.kind, decision.round) == ("continue", 2)

    at_cap = active.model_copy(update={"rounds_started": 3})
    assert next_round(goal=at_cap, armed=True, stop_reason="MODEL_COMPLETED").kind == "exhausted"


async def test_a_cancelled_round_pauses_the_goal_and_disarms_it(tmp_path: Path) -> None:
    """取消即按停：ABORTED 之后目标落 paused、武装位归假，人才能决定下一步。"""
    records, goal, outcome, env = await _run(tmp_path, max_rounds=3, abort_at=3)

    assert list(_segments(records)) == ["s1", "s2"]
    assert goal is not None
    assert goal.phase == "paused"
    assert goal.rounds_started == 1
    assert goal.revision == 2
    assert env.goal_runtime.armed is False
    assert outcome.stop_reason == "ABORTED"


async def test_a_provider_error_keeps_the_goal_active_but_disarmed(tmp_path: Path) -> None:
    """上游坏了不是目标的错：`phase` 留在 active，解除武装等人 resume。"""
    records, goal, outcome, env = await _run(tmp_path, max_rounds=3, fail_at=3)

    assert list(_segments(records)) == ["s1", "s2"]
    assert goal is not None
    assert goal.phase == "active"
    assert goal.rounds_started == 1
    assert goal.revision == 1
    assert env.goal_runtime.armed is False
    assert outcome.stop_reason == "PROVIDER_ERROR"


def test_a_broken_log_is_reported_instead_of_guessed(tmp_path: Path) -> None:
    """段结束时读不动日志：驱动把失败往上报，不按「没有目标」处理。"""
    from mini_harness.events import EventLog, LogReadFailure
    from mini_harness.loop.turn_loop import _goal_after

    log = EventLog.create(tmp_path, session_id="s-broken")
    log.path.write_text("{ 这不是 json\n", encoding="utf-8")

    assert isinstance(_goal_after(log), LogReadFailure)
