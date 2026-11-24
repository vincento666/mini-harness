"""seam ①⑦：段结束后的目标续跑判定、四事件顺序与额度用尽。"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from mini_harness.events import EventRecord, read_events
from mini_harness.events.writer import LogWriteFailure
from mini_harness.goals import GoalPolicy, GoalSnapshot, fold_goal
from mini_harness.loop import ENTRY_RUN, exhaust_goal_rounds, run_session_env
from mini_harness.loop.goal_driver import RoundDecision, next_round
from mini_harness.provider import AssistantTurn, FixtureProvider, ProviderFailure, ToolCall
from mini_harness.tools import ToolRegistry
from mini_harness.tools.assistant import assistant_tool_definitions
from mini_harness.tools.goal import goal_tool_definitions
from tool_harness import build_session_env

OBJECTIVE = "修好失败的用例"


def _registry() -> ToolRegistry:
    return ToolRegistry([*assistant_tool_definitions(), *goal_tool_definitions()])


class _Scripted:
    """按「goal 轮号」回答：第 1 次建目标，之后每一轮先探一下再收尾。

    零工具调用的 goal 轮会被驱动判成停滞（D14），所以这里每轮先发一个只读的
    `get_goal` 探针，再由下一次调用收尾；一个轮次因此是两跳，但轮号只加一次。
    `complete_at` / `abort_at` / `fail_at` 都按 goal 轮号（从 1 起）说话。
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

    def _round(self) -> int:
        assert self.log_path is not None
        goal = fold_goal(read_events(self.log_path))
        assert goal is not None
        # 进入模型时这一轮已经被计入 `rounds_started`，所以当前轮号就是它。
        return goal.rounds_started

    async def generate(
        self, messages: Any, tools: Any, signal: Any, on_delta: Any = None
    ) -> AssistantTurn | ProviderFailure:
        self.calls += 1
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
        if messages[-1].role == "tool":
            # 同一轮的第二跳：工具结果已经回来了，这一轮到此收尾。
            return AssistantTurn(content="这一步做完了", finish_reason="stop")

        round_number = self._round()
        if self.abort_at is not None and round_number == self.abort_at:
            assert self.cancel is not None
            self.cancel.set()
        if self.fail_at is not None and round_number == self.fail_at:
            return ProviderFailure("PROVIDER_HTTP_STATUS", "上游 400")
        if self.complete_at is not None and round_number == self.complete_at:
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
        # 只读探针：让本轮有一个真实的工具调用，避免被停滞熔断（D14）。
        return AssistantTurn(
            content="先读一下目标",
            finish_reason="tool_calls",
            tool_calls=[ToolCall(id=f"g{round_number}", name="get_goal", arguments={})],
        )


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
        tmp_path, "s-goal-rounds", provider, registry=_registry(), max_steps=8
    )
    provider.log_path = log.path
    cancel = asyncio.Event()
    provider.cancel = cancel
    outcome = await run_session_env(prompt="把这件活干完", entry=ENTRY_RUN, env=env, cancel=cancel)
    return read_events(log.path), fold_goal(read_events(log.path)), outcome, env


def _segments(records: list[EventRecord]) -> dict[str, list[EventRecord]]:
    """按 `turn/start` 切段：段外的记录（`session/*`）不算进任何段。"""
    out: dict[str, list[EventRecord]] = {}
    current: str | None = None
    for record in records:
        if record.type == "turn/start":
            current = str(record.payload.get("turn_id"))
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
    assert [record.type for record in records].count("turn/end") == 4

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
        assert types[:6] == [
            "turn/start",
            "user/message",
            "step/start",
            "context/assembled",
            "goal/updated",
            "model/request",
        ]
        snapshot = segment[4].payload["goal"]
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


class _AsksThenStops:
    """第 1 轮问一个人答不了的问题，然后收尾；用来钉住「未决问题不续跑」。"""

    def __init__(self) -> None:
        self.calls = 0

    async def generate(
        self, messages: Any, tools: Any, signal: Any, on_delta: Any = None
    ) -> AssistantTurn | ProviderFailure:
        self.calls += 1
        if self.calls == 1:
            return AssistantTurn(
                content="先立个目标",
                finish_reason="tool_calls",
                tool_calls=[
                    ToolCall(
                        id="c1",
                        name="create_goal",
                        arguments={"objective": OBJECTIVE, "max_rounds": 3},
                    )
                ],
            )
        if self.calls == 2:
            # 人类这一段自己收尾：问题要落在目标轮次里，才测得到驱动。
            return AssistantTurn(content="先看一下", finish_reason="stop")
        if self.calls == 3:
            return AssistantTurn(
                content="我先问一句",
                finish_reason="tool_calls",
                tool_calls=[
                    ToolCall(
                        id="q1",
                        name="ask_user",
                        arguments={"question": "用 A 还是 B", "options": ["A", "B"]},
                    )
                ],
            )
        return AssistantTurn(content="等你回答", finish_reason="stop")


async def test_an_unanswered_question_hands_control_back_without_burning_the_next_round(
    tmp_path: Path,
) -> None:
    """自动轮次里问不到人：不开下一段，但目标保持 active/armed（design D13）。

    一次入口没有人可等，所以这里直接收会话；下一次人类段结束后，驱动会接着开轮次。
    """
    log, env = build_session_env(
        tmp_path, "s-question", _AsksThenStops(), registry=_registry(), max_steps=8
    )
    outcome = await run_session_env(
        prompt="把这件活干完", entry=ENTRY_RUN, env=env, cancel=asyncio.Event()
    )
    records = read_events(log.path)

    assert list(_segments(records)) == ["s1", "s2"]
    assert env.goal_runtime.armed is True
    goal = fold_goal(records)
    assert goal is not None
    assert goal.phase == "active"
    assert goal.rounds_started == 1
    assert outcome.stop_reason == "MODEL_COMPLETED"
    types = [record.type for record in records]
    assert types.count("question/asked") == 1
    assert "question/answered" not in types
    # 问题悬着的时候不开新段：日志里没有第 2 轮的 goal 消息。
    assert [
        payload["source"]["round"]
        for payload in (
            record.payload
            for record in records
            if record.type == "user/message"
            and record.payload.get("source", {}).get("kind") == "goal"
        )
    ] == [1]


async def test_a_completed_goal_no_longer_opens_segments(tmp_path: Path) -> None:
    records, goal, outcome, _ = await _run(tmp_path, max_rounds=3, complete_at=2)

    segments = _segments(records)
    assert list(segments) == ["s1", "s2", "s3"]
    assert goal is not None
    assert goal.phase == "complete"
    assert goal.rounds_started == 2
    assert goal.revision == 2
    assert [record.type for record in records].count("turn/start") == 3
    assert outcome.stop_reason == "MODEL_COMPLETED"


class _TwoTurnRounds:
    """人类段建目标；此后每轮两个回合（先提待办、再收尾），从不标完成。

    单回合的轮次分不出「每轮扣一次」与「每回合扣一次」——这个脚本专门用来
    把计数点钉在段首，而不是每个回合（变异 M5 的专用判据）。
    """

    def __init__(self) -> None:
        self.calls = 0

    async def generate(
        self, messages: Any, tools: Any, signal: Any, on_delta: Any = None
    ) -> AssistantTurn | ProviderFailure:
        self.calls += 1
        if self.calls == 1:
            return AssistantTurn(
                content="先立个目标",
                finish_reason="tool_calls",
                tool_calls=[
                    ToolCall(
                        id="c1",
                        name="create_goal",
                        arguments={"objective": OBJECTIVE, "max_rounds": 2},
                    )
                ],
            )
        if self.calls % 2 == 0:
            return AssistantTurn(
                content="提一条待办",
                finish_reason="tool_calls",
                tool_calls=[
                    ToolCall(
                        id=f"t{self.calls}",
                        name="todo",
                        arguments={
                            "items": [{"id": "t1", "text": "这一步", "status": "in_progress"}]
                        },
                    )
                ],
            )
        return AssistantTurn(content="这一步做完了", finish_reason="stop")


async def test_a_round_with_two_turns_deducts_only_once(tmp_path: Path) -> None:
    """一轮两回合也只扣一次：额度跟段走，不跟回合走。"""
    log, env = build_session_env(
        tmp_path, "s-two-turn-rounds", _TwoTurnRounds(), registry=_registry(), max_steps=8
    )
    outcome = await run_session_env(
        prompt="把这件活干完", entry=ENTRY_RUN, env=env, cancel=asyncio.Event()
    )
    records = read_events(log.path)
    segments = _segments(records)
    assert list(segments) == ["s1", "s2", "s3"]

    for name, round_number in (("s2", 1), ("s3", 2)):
        inside: list[EventRecord] = []
        for record in segments[name]:
            inside.append(record)
            if record.type == "turn/end":
                break
        assert [record.type for record in inside].count("step/start") == 2
        snapshots = [record.payload["goal"] for record in inside if record.type == "goal/updated"]
        # 段内只有一条扣额度的快照；两回合若各扣一次，这里会变成 [1, 2] 与 [3]。
        assert [snapshot["rounds_started"] for snapshot in snapshots] == [round_number]
        assert all(snapshot["phase"] == "active" for snapshot in snapshots)

    goal = fold_goal(records)
    assert goal is not None
    assert goal.rounds_started == 2
    assert goal.phase == "blocked"
    assert goal.blocked_reason is not None
    assert goal.blocked_reason.code == "round-limit"
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
        "MAX_STEPS",
    ):
        assert next_round(goal=active, armed=True, stop_reason=stop_reason).kind == "stop"
    paused = active.model_copy(update={"phase": "paused"})
    assert next_round(goal=paused, armed=True, stop_reason="MODEL_COMPLETED").kind == "stop"

    decision = next_round(goal=active, armed=True, stop_reason="MODEL_COMPLETED")
    assert (decision.kind, decision.round) == ("continue", 2)

    # 未决问题优先于停滞：先告诉人「等你回答」，不再开轮次。
    assert (
        next_round(
            goal=active, armed=True, stop_reason="MODEL_COMPLETED", question_pending=True
        ).kind
        == "awaiting_input"
    )
    # 默认不对齐「零动作就停」：DSH 的 goal 循环不看工具调用（2026-11-20 人裁）。
    assert (
        next_round(goal=active, armed=True, stop_reason="MODEL_COMPLETED", idle_rounds=5).kind
        == "continue"
    )
    # 默认阈值是 2（`[goal] stall_rounds` 的缺省）：连续两轮才停。
    assert (
        next_round(
            goal=active,
            armed=True,
            stop_reason="MODEL_COMPLETED",
            idle_rounds=2,
            stall_rounds=2,
        ).kind
        == "stalled"
    )
    assert (
        next_round(
            goal=active,
            armed=True,
            stop_reason="MODEL_COMPLETED",
            idle_rounds=1,
            stall_rounds=2,
        ).kind
        == "continue"
    )
    assert (
        next_round(
            goal=active,
            armed=True,
            stop_reason="MODEL_COMPLETED",
            idle_rounds=9,
            stall_rounds=2,
            goal_round=False,
        ).kind
        == "continue"
    )
    # 额度用尽比未决问题更硬：最后一轮里问了问题也先落 blocker。
    at_cap = active.model_copy(update={"rounds_started": 3})
    assert (
        next_round(
            goal=at_cap, armed=True, stop_reason="MODEL_COMPLETED", question_pending=True
        ).kind
        == "exhausted"
    )


async def test_a_cancelled_round_pauses_the_goal_and_disarms_it(tmp_path: Path) -> None:
    """取消即按停：ABORTED 之后目标落 paused、武装位归假，人才能决定下一步。"""
    records, goal, outcome, env = await _run(tmp_path, max_rounds=3, abort_at=1)

    assert list(_segments(records)) == ["s1", "s2"]
    assert goal is not None
    assert goal.phase == "paused"
    assert goal.rounds_started == 1
    assert goal.revision == 2
    assert env.goal_runtime.armed is False
    assert outcome.stop_reason == "ABORTED"


async def test_a_provider_error_keeps_the_goal_active_but_disarmed(tmp_path: Path) -> None:
    """上游坏了不是目标的错：`phase` 留在 active，解除武装等人 resume。"""
    records, goal, outcome, env = await _run(tmp_path, max_rounds=3, fail_at=1)

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
    from mini_harness.loop.turn_loop import goal_after

    log = EventLog.create(tmp_path, session_id="s-broken")
    log.path.write_text("{ 这不是 json\n", encoding="utf-8")

    assert isinstance(goal_after(log), LogReadFailure)


def test_a_failed_round_limit_write_is_reported(tmp_path: Path, monkeypatch: Any) -> None:
    """额度用尽写不进日志：段以失败收尾、武装位已经解除。"""
    log, env = build_session_env(
        tmp_path, "s-limit-fail", FixtureProvider(entries=[]), registry=_registry()
    )
    goal = GoalSnapshot(
        id="g1", revision=1, objective=OBJECTIVE, phase="active", max_rounds=2, rounds_started=1
    )
    monkeypatch.setattr(
        env.log, "append", lambda *args, **kwargs: LogWriteFailure(log.path, "只读")
    )

    failed = exhaust_goal_rounds(env=env, decision=RoundDecision("exhausted", goal, 2), steps=2)

    assert failed is not None
    assert failed.failure_code == "LOG_WRITE_FAILED"
    assert env.goal_runtime.armed is False


async def test_two_idle_goal_rounds_in_a_row_trip_the_stall_gate_by_default(
    tmp_path: Path,
) -> None:
    """默认阈值 2：连续两个 goal 轮次零工具调用才停，一轮空转不误杀（D14）。"""
    provider = FixtureProvider(
        entries=[
            {
                "content": "先立个目标",
                "finish_reason": "tool_calls",
                "tool_calls": [
                    {
                        "id": "c1",
                        "name": "create_goal",
                        "arguments": {"objective": OBJECTIVE, "max_rounds": 5},
                    }
                ],
            },
            {"content": "建完目标", "finish_reason": "stop"},
            {"content": "第一轮空转", "finish_reason": "stop"},
            {"content": "第二轮空转", "finish_reason": "stop"},
            {"content": "不应该跑到这一轮", "finish_reason": "stop"},
        ]
    )
    log, env = build_session_env(tmp_path, "s-idle", provider, registry=_registry())
    outcome = await run_session_env(prompt="开始", entry=ENTRY_RUN, env=env, cancel=asyncio.Event())
    records = read_events(log.path)

    # 人类段 s1 + 两轮空转（s2/s3）；第二轮之后停，不再开 s4。
    assert list(_segments(records)) == ["s1", "s2", "s3"]
    assert env.goal_runtime.armed is False
    assert env.goal_runtime.idle_rounds == 0  # 停时清零，resume 后重新给满阈值
    goal = fold_goal(records)
    assert goal is not None
    assert goal.phase == "active"  # 不改相位：完成与否是模型/人的判断
    assert goal.rounds_started == 2
    assert outcome.stop_reason == "MODEL_COMPLETED"
    ends = [record for record in records if record.type == "turn/end"]
    assert [record.payload["tool_calls"] for record in ends] == [1, 0, 0]


async def test_stall_rounds_zero_disables_the_gate_entirely(tmp_path: Path) -> None:
    """`stall_rounds = 0` 完全对齐 DSH：一路跑到上限，空转不是停的理由。"""
    provider = FixtureProvider(
        entries=[
            {
                "content": "先立个目标",
                "finish_reason": "tool_calls",
                "tool_calls": [
                    {
                        "id": "c1",
                        "name": "create_goal",
                        "arguments": {"objective": OBJECTIVE, "max_rounds": 3},
                    }
                ],
            },
            {"content": "建完目标", "finish_reason": "stop"},
            {"content": "没有新内容可写", "finish_reason": "stop"},
            {"content": "还是没有", "finish_reason": "stop"},
            {"content": "第三轮", "finish_reason": "stop"},
        ]
    )
    log, env = build_session_env(
        tmp_path,
        "s-nogate",
        provider,
        registry=_registry(),
        goal=GoalPolicy(stall_rounds=0),
    )
    outcome = await run_session_env(prompt="开始", entry=ENTRY_RUN, env=env, cancel=asyncio.Event())
    records = read_events(log.path)

    assert list(_segments(records)) == ["s1", "s2", "s3", "s4"]
    goal = fold_goal(records)
    assert goal is not None
    assert goal.phase == "blocked"
    assert goal.blocked_reason is not None
    assert goal.blocked_reason.code == "round-limit"
    assert goal.rounds_started == 3
    assert outcome.stop_reason == "MODEL_COMPLETED"
