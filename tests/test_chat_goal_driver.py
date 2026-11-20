"""seam ⑥⑦：chat 的段后驱动（M13 5.4）与恢复后的武装位（5.3）。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from cli_blackbox import _cli
from mini_harness.config import build_registry
from mini_harness.events import EventRecord, read_events
from mini_harness.goals import GoalSnapshot, fold_goal
from mini_harness.loop import ENTRY_CHAT, start_session
from mini_harness.provider import FixtureProvider
from tool_harness import build_session_env


def _fixture(cwd: Path, entries: list[dict[str, Any]]) -> str:
    path = cwd / "turns.json"
    path.write_text(json.dumps(entries, ensure_ascii=False), encoding="utf-8")
    return str(path)


def _chat(cwd: Path, fixture: str, stdin_text: str, *extra: str) -> Any:
    return _cli(
        "chat",
        "--provider",
        "mock",
        "--fixture",
        fixture,
        *extra,
        cwd=cwd,
        stdin_text=stdin_text,
    )


def _records(cwd: Path) -> list[EventRecord]:
    logs = sorted((cwd / "sessions").glob("*.jsonl"))
    assert len(logs) == 1, f"应当恰有一份日志，实际 {len(logs)} 份"
    records = read_events(logs[0])
    assert isinstance(records, list)
    return records


def _goal_messages(records: list[EventRecord]) -> list[dict[str, Any]]:
    return [
        record.payload
        for record in records
        if record.type == "user/message" and record.payload.get("source", {}).get("kind") == "goal"
    ]


_CREATE_GOAL = {
    "content": "先立个目标",
    "finish_reason": "tool_calls",
    "tool_calls": [
        {
            "id": "c1",
            "name": "create_goal",
            "arguments": {"objective": "修好失败的用例", "max_rounds": 2},
        }
    ],
}


def test_chat_keeps_running_rounds_without_another_line(tmp_path: Path) -> None:
    """一行输入之后，目标轮次自己跑完：不在轮次之间读输入、不打印提示符。"""
    fixture = _fixture(
        tmp_path,
        [
            _CREATE_GOAL,
            # 人类这一段自己的第二个回合：建完目标就收尾，轮次从下一段开始。
            {"content": "先看一下", "finish_reason": "stop"},
            {
                "content": "先读一下目标",
                "finish_reason": "tool_calls",
                "tool_calls": [{"id": "g1", "name": "get_goal", "arguments": {}}],
            },
            {"content": "第一轮做了一点", "finish_reason": "stop"},
            {
                "content": "先读一下目标",
                "finish_reason": "tool_calls",
                "tool_calls": [{"id": "g2", "name": "get_goal", "arguments": {}}],
            },
            {"content": "第二轮做完了", "finish_reason": "stop"},
        ],
    )

    result = _chat(tmp_path, fixture, "开始\n")

    assert result.returncode == 0
    records = _records(tmp_path)
    assert [record.type for record in records].count("segment/start") == 3
    assert [payload["source"]["round"] for payload in _goal_messages(records)] == [1, 2]
    goal = fold_goal(records)
    assert goal is not None
    assert goal.phase == "blocked"
    assert goal.blocked_reason is not None
    assert goal.blocked_reason.code == "round-limit"
    # 两轮的回复都打出来了：驱动期间输出接着走，不是攒到提示符才印。
    assert "第一轮做了一点" in result.stdout
    assert "第二轮做完了" in result.stdout
    # 自动轮次有边界标记：人手里没有提示符，靠这两行知道这是第几轮、为什么停了。
    assert "[轮] 1/2" in result.stderr
    assert "[轮] 2/2" in result.stderr
    assert "已用尽 2/2" in result.stderr


def test_a_question_asked_in_a_round_returns_to_the_prompt_without_burning_the_next(
    tmp_path: Path,
) -> None:
    """自动轮次里问不到人：回到提示符，目标保持 active/armed（design D13）。"""
    fixture = _fixture(
        tmp_path,
        [
            {
                "content": "先立个目标",
                "finish_reason": "tool_calls",
                "tool_calls": [
                    {
                        "id": "c1",
                        "name": "create_goal",
                        "arguments": {"objective": "修好失败的用例", "max_rounds": 3},
                    }
                ],
            },
            {"content": "先看一下", "finish_reason": "stop"},
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
            {"content": "不应该跑到这一轮", "finish_reason": "stop"},
        ],
    )

    # 问题未决时目标仍是 active/armed；习惯性敲 `/goal resume` 不能再起一轮。
    result = _chat(tmp_path, fixture, "开始\n/goal resume\n")

    assert result.returncode == 0
    records = _records(tmp_path)
    assert [record.type for record in records].count("segment/start") == 2
    goal = fold_goal(records)
    assert goal is not None
    assert goal.phase == "active"
    assert goal.rounds_started == 1
    types = [record.type for record in records]
    assert types.count("question/asked") == 1
    assert "question/answered" not in types
    assert "等你回答" in result.stdout
    assert "不应该跑到这一轮" not in result.stdout
    assert "[轮] 1/3" in result.stderr
    assert "[轮] 2/3" not in result.stderr
    assert "目标保持 active" in result.stderr
    assert "无需 resume" in result.stdout


def test_an_answer_is_a_human_segment_and_the_goal_resumes_after_it(
    tmp_path: Path,
) -> None:
    """回答不是 goal 轮：它开人类段，段结束后驱动再开下一 goal 轮（D13）。"""
    fixture = _fixture(
        tmp_path,
        [
            {
                "content": "先立个目标",
                "finish_reason": "tool_calls",
                "tool_calls": [
                    {
                        "id": "c1",
                        "name": "create_goal",
                        "arguments": {"objective": "修好失败的用例", "max_rounds": 2},
                    }
                ],
            },
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
            {
                "content": "先读一下目标",
                "finish_reason": "tool_calls",
                "tool_calls": [{"id": "g2", "name": "get_goal", "arguments": {}}],
            },
            {"content": "第二轮做完了", "finish_reason": "stop"},
        ],
    )

    # 第二行就是人对问题的回答；它不写成 goal 来源。
    result = _chat(tmp_path, fixture, "开始\n用 A\n")

    assert result.returncode == 0
    records = _records(tmp_path)
    assert [record.type for record in records].count("segment/start") == 4
    messages = [record.payload for record in records if record.type == "user/message"]
    assert [message["source"]["kind"] for message in messages] == [
        "user",
        "goal",
        "user",
        "goal",
    ]
    assert [
        message["source"]["round"] for message in messages if message["source"]["kind"] == "goal"
    ] == [1, 2]
    goal = fold_goal(records)
    assert goal is not None
    assert goal.rounds_started == 2
    assert goal.phase == "blocked"
    assert goal.blocked_reason is not None
    assert goal.blocked_reason.code == "round-limit"
    assert "收到答案：用 A" in result.stdout
    assert "第二轮做完了" in result.stdout
    assert "目标保持 active" in result.stderr
    assert "[轮] 2/2" in result.stderr


def test_resume_does_not_continue_an_active_goal(tmp_path: Path) -> None:
    """`--resume` 之后武装位是假：新段结束不再起轮次（5.1/5.3）。"""
    sessions = tmp_path / "sessions"
    sessions.mkdir()
    log, env = build_session_env(
        tmp_path,
        "s-resume-goal",
        FixtureProvider(entries=[]),
        registry=build_registry(None),
        session_dir=sessions,
    )
    assert start_session(prompt="", entry=ENTRY_CHAT, env=env) is None
    active = GoalSnapshot(
        id="g1",
        revision=3,
        objective="修好失败的用例",
        phase="active",
        max_rounds=5,
        rounds_started=1,
    )
    log.append("goal/updated", {"goal": active.model_dump(exclude_none=True)})
    # 不写 session/end：模拟进程在轮次之间消失，恢复的正是这种日志。

    fixture = _fixture(tmp_path, [{"content": "只回应这一句", "finish_reason": "stop"}])
    result = _chat(tmp_path, fixture, "继续\n", "--resume", "s-resume-goal")

    assert result.returncode == 0
    records = _records(tmp_path)
    assert _goal_messages(records) == []
    goal = fold_goal(records)
    assert goal is not None
    assert goal.phase == "active"
    assert goal.rounds_started == 1


def test_goal_resume_in_chat_starts_the_next_round_without_another_line(
    tmp_path: Path,
) -> None:
    """`/goal resume` 之后立刻起下一轮：不必再敲一行（design D12）。"""
    sessions = tmp_path / "sessions"
    sessions.mkdir()
    log, env = build_session_env(
        tmp_path,
        "s-resume-paused",
        FixtureProvider(entries=[]),
        registry=build_registry(None),
        session_dir=sessions,
    )
    assert start_session(prompt="", entry=ENTRY_CHAT, env=env) is None
    paused = GoalSnapshot(
        id="g1",
        revision=3,
        objective="修好失败的用例",
        phase="paused",
        max_rounds=2,
        rounds_started=1,
    )
    log.append("goal/updated", {"goal": paused.model_dump(exclude_none=True)})

    fixture = _fixture(
        tmp_path,
        [
            {
                "content": "先读一下目标",
                "finish_reason": "tool_calls",
                "tool_calls": [{"id": "g2", "name": "get_goal", "arguments": {}}],
            },
            {"content": "第二轮做完了", "finish_reason": "stop"},
        ],
    )
    # 只给命令、不给后续输入：轮次仍然要跑起来。
    result = _chat(tmp_path, fixture, "/goal resume\n", "--resume", "s-resume-paused")

    assert result.returncode == 0
    assert "已恢复目标" in result.stdout
    assert "第二轮做完了" in result.stdout
    # 这一轮是自动轮次：终端有轮次标记，且没有多出一个供人输入的空段。
    assert "[轮] 2/2" in result.stderr
    assert "[轮] 已用尽 2/2" in result.stderr
    records = _records(tmp_path)
    assert [payload["source"]["round"] for payload in _goal_messages(records)] == [2]
    goal = fold_goal(records)
    assert goal is not None
    assert goal.phase == "blocked"
    assert goal.blocked_reason is not None
    assert goal.blocked_reason.code == "round-limit"


def test_resume_round_only_drives_on_a_successful_resume(tmp_path: Path) -> None:
    """`_resume_round` 的每一档：只认 resume + 已武装 + active + 还有额度（D12）。"""
    from mini_harness.cli.main import _resume_round

    sessions = tmp_path / "sessions"
    sessions.mkdir()
    log, env = build_session_env(
        tmp_path,
        "s-resume-helper",
        FixtureProvider(entries=[]),
        registry=build_registry(None),
        session_dir=sessions,
    )
    assert start_session(prompt="", entry=ENTRY_CHAT, env=env) is None
    active = GoalSnapshot(
        id="g-helper",
        revision=1,
        objective="修好失败的用例",
        phase="active",
        max_rounds=3,
        rounds_started=1,
    )
    log.append("goal/updated", {"goal": active.model_dump(exclude_none=True)})

    assert _resume_round(env, "/goal pause", was_armed=False) is None
    assert _resume_round(env, "/goal resume", was_armed=False) is None  # 还没武装
    env.goal_runtime.armed = True
    assert _resume_round(env, "/goal", was_armed=False) is None
    assert _resume_round(env, "/goal resume extra", was_armed=False) is None
    # 命令执行前就已武装：`/goal resume` 只是「无需 resume」，不能再起一轮。
    assert _resume_round(env, "/goal resume", was_armed=True) is None

    decision = _resume_round(env, "/goal resume", was_armed=False)
    assert decision is not None
    assert decision.round == 2
    assert decision.goal is not None

    env.goal_runtime.armed = False
    paused = active.model_copy(update={"phase": "paused", "revision": 2})
    log.append("goal/updated", {"goal": paused.model_dump(exclude_none=True)})
    assert _resume_round(env, "/goal resume", was_armed=False) is None

    at_cap = active.model_copy(update={"rounds_started": 3, "revision": 3})
    log.append("goal/updated", {"goal": at_cap.model_dump(exclude_none=True)})
    assert _resume_round(env, "/goal resume", was_armed=False) is None

    log.append("goal/updated", {"goal": None})
    assert _resume_round(env, "/goal resume", was_armed=False) is None
