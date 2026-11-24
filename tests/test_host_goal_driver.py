"""seam ⑥⑦：host 也要跑目标轮次，队列人话优先（2026-11-20 人裁）。

这些用例不起子进程：直接建 `HostSession`、投消息、等段链跑完，再读同一份日志。
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import replace
from pathlib import Path
from typing import Any

from mini_harness.events import read_events
from mini_harness.goals import GoalSnapshot, fold_goal
from mini_harness.session.assembly import AssemblyRequest
from mini_harness.session.host import (
    HostQuestionGate,
    HostSession,
    HostState,
    create_session,
    run_command,
    submit_message,
)


def _handle(
    tmp_path: Path,
    entries: list[dict[str, Any]],
    *,
    question_timeout: float | None = None,
) -> HostSession:
    fixture = tmp_path / "turns.json"
    fixture.write_text(json.dumps(entries, ensure_ascii=False), encoding="utf-8")
    state = HostState(
        defaults=AssemblyRequest(
            workspace=str(tmp_path / "workspace"),
            provider="mock",
            fixture=str(fixture),
            session_dir=str(tmp_path / "sessions"),
            approval="auto",
        ),
        allow_auto_approval=True,
    )
    handle = create_session(state, state.defaults, {})
    assert isinstance(handle, HostSession)
    if question_timeout is not None:
        handle.env = replace(
            handle.env, question_gate=HostQuestionGate(handle, timeout=question_timeout)
        )
    return handle


async def _drain(handle: HostSession, timeout: float = 10.0) -> None:
    """等段链自己走完：每段收尾会起下一段的 task，所以要循环等到 idle/ended。"""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while handle.status == "running":
        task = handle.task
        if task is None:
            await asyncio.sleep(0.01)
            continue
        await asyncio.wait_for(asyncio.shield(task), timeout=deadline - loop.time())


def _messages(handle: HostSession) -> list[dict[str, Any]]:
    records = read_events(handle.log.path)
    assert isinstance(records, list)
    return [record.payload for record in records if record.type == "user/message"]


def _turns(handle: HostSession) -> list[str]:
    records = read_events(handle.log.path)
    assert isinstance(records, list)
    return [str(record.payload["turn_id"]) for record in records if record.type == "turn/start"]


def _create_goal(max_rounds: int) -> dict[str, Any]:
    return {
        "content": "先立个目标",
        "finish_reason": "tool_calls",
        "tool_calls": [
            {
                "id": "c1",
                "name": "create_goal",
                "arguments": {"objective": "把 notes.md 写完", "max_rounds": max_rounds},
            }
        ],
    }


def _probe(tag: str) -> dict[str, Any]:
    return {
        "content": "先读一下目标",
        "finish_reason": "tool_calls",
        "tool_calls": [{"id": tag, "name": "get_goal", "arguments": {}}],
    }


async def test_host_runs_goal_rounds_to_the_cap(tmp_path: Path) -> None:
    """host 不再只有命令面：人类段结束后目标轮次自己跑，直到 round-limit。"""
    (tmp_path / "workspace").mkdir()
    handle = _handle(
        tmp_path,
        [
            _create_goal(2),
            {"content": "建完", "finish_reason": "stop"},
            _probe("g1"),
            {"content": "第一轮", "finish_reason": "stop"},
            _probe("g2"),
            {"content": "第二轮", "finish_reason": "stop"},
        ],
    )

    accepted = submit_message(handle, "开始")
    assert accepted is not None and accepted.queued is False
    await _drain(handle)

    assert handle.status == "idle"
    assert _turns(handle) == ["s1", "s2", "s3"]
    messages = _messages(handle)
    assert [message["source"]["kind"] for message in messages] == ["user", "goal", "goal"]
    assert [message["source"]["round"] for message in messages[1:]] == [1, 2]
    goal = fold_goal(read_events(handle.log.path))
    assert goal is not None
    assert goal.phase == "blocked"
    assert goal.blocked_reason is not None
    assert goal.blocked_reason.code == "round-limit"


async def test_a_queued_human_message_runs_before_the_next_goal_round(tmp_path: Path) -> None:
    """人话优先：段进行中投进来的消息先跑，之后才轮到自动轮次（对齐 competingQueued）。"""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "slow.py").write_text("import time\n\ntime.sleep(0.4)\n", encoding="utf-8")
    handle = _handle(
        tmp_path,
        [
            _create_goal(2),
            {"content": "建完", "finish_reason": "stop"},
            {
                "content": "跑一条慢命令",
                "finish_reason": "tool_calls",
                "tool_calls": [
                    {"id": "b1", "name": "bash", "arguments": {"command": "python slow.py"}}
                ],
            },
            {"content": "第一轮", "finish_reason": "stop"},
            _probe("g2"),
            {"content": "第二轮", "finish_reason": "stop"},
        ],
    )

    submit_message(handle, "开始")
    # 等 goal 轮次真的开始跑慢命令，再投人话；否则它会在段尾直接起人类段（不是排队）。
    loop = asyncio.get_running_loop()
    deadline = loop.time() + 10.0
    while loop.time() < deadline:
        records = read_events(handle.log.path)
        assert isinstance(records, list)
        if any(
            record.type == "tool/call" and record.payload.get("name") == "bash"
            for record in records
        ):
            break
        await asyncio.sleep(0.01)
    else:
        raise AssertionError("goal 轮次没有开始跑慢命令")

    queued = submit_message(handle, "插一句")
    assert queued is not None and queued.queued is True
    await _drain(handle)

    messages = _messages(handle)
    assert [message["source"]["kind"] for message in messages] == [
        "user",
        "goal",
        "user",
        "goal",
    ]
    assert [message["content"] for message in messages if message["source"]["kind"] == "user"] == [
        "开始",
        "插一句",
    ]
    # 人类段夹在两轮之间，但轮号不因它推进。
    assert [
        message["source"]["round"] for message in messages if message["source"]["kind"] == "goal"
    ] == [1, 2]
    assert _turns(handle) == ["s1", "s2", "s3", "s4"]


async def test_a_question_answer_is_a_human_turn_then_the_goal_continues(
    tmp_path: Path,
) -> None:
    """问题未决 → host 回 idle；人回答开人类段，段结束后自动续下一 goal 轮（D13）。"""
    (tmp_path / "workspace").mkdir()
    handle = _handle(
        tmp_path,
        [
            _create_goal(2),
            {"content": "建完", "finish_reason": "stop"},
            {
                "content": "我先问一句",
                "finish_reason": "tool_calls",
                "tool_calls": [
                    {
                        "id": "q1",
                        "name": "ask_user",
                        "arguments": {"question": "用 A 还是 B", "options": ["A", "B"]},
                    }
                ],
            },
            {"content": "等你回答", "finish_reason": "stop"},
            {"content": "收到答案：用 A", "finish_reason": "stop"},
            _probe("g2"),
            {"content": "第二轮", "finish_reason": "stop"},
        ],
        question_timeout=0.05,
    )

    submit_message(handle, "开始")
    await _drain(handle)

    # 问题悬着：host 回 idle，目标仍是 active，轮次还是 1。
    assert handle.status == "idle"
    goal = fold_goal(read_events(handle.log.path))
    assert goal is not None
    assert goal.phase == "active"
    assert goal.rounds_started == 1
    assert _turns(handle) == ["s1", "s2"]

    answered = submit_message(handle, "用 A")
    assert answered is not None and answered.queued is False
    await _drain(handle)

    messages = _messages(handle)
    assert [message["source"]["kind"] for message in messages] == [
        "user",
        "goal",
        "user",
        "goal",
    ]
    assert [
        message["source"]["round"] for message in messages if message["source"]["kind"] == "goal"
    ] == [1, 2]
    goal = fold_goal(read_events(handle.log.path))
    assert goal is not None
    assert goal.rounds_started == 2
    assert goal.phase == "blocked"
    assert goal.blocked_reason is not None
    assert goal.blocked_reason.code == "round-limit"


async def test_goal_resume_command_starts_the_next_round_immediately(tmp_path: Path) -> None:
    """与 chat 的 D12 对齐：`/goal resume` 之后立刻开段，不等客户端再 POST 一条。"""
    (tmp_path / "workspace").mkdir()
    handle = _handle(
        tmp_path,
        [
            _probe("g2"),
            {"content": "第二轮", "finish_reason": "stop"},
        ],
    )
    paused = GoalSnapshot(
        id="g1",
        revision=2,
        objective="把 notes.md 写完",
        phase="paused",
        max_rounds=2,
        rounds_started=1,
    )
    handle.log.append("goal/updated", {"goal": paused.model_dump(exclude_none=True)})

    response = run_command(handle, "goal", "resume")

    assert not hasattr(response, "code"), response
    assert response.ok is True
    assert handle.status == "running"
    await _drain(handle)

    assert _turns(handle) == ["s1"]
    messages = _messages(handle)
    assert [message["source"]["kind"] for message in messages] == ["goal"]
    assert messages[0]["source"]["round"] == 2
    goal = fold_goal(read_events(handle.log.path))
    assert goal is not None
    assert goal.phase == "blocked"
    assert goal.blocked_reason is not None
    assert goal.blocked_reason.code == "round-limit"
