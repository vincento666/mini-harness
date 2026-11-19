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
            {"content": "第一轮做了一点", "finish_reason": "stop"},
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


def test_a_question_asked_in_a_round_pauses_instead_of_burning_the_next(
    tmp_path: Path,
) -> None:
    """自动轮次里问不到人：回到提示符、目标暂停，不再白烧下一轮（design D9）。"""
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

    result = _chat(tmp_path, fixture, "开始\n")

    assert result.returncode == 0
    records = _records(tmp_path)
    assert [record.type for record in records].count("segment/start") == 2
    goal = fold_goal(records)
    assert goal is not None
    assert goal.phase == "paused"
    assert goal.rounds_started == 1
    types = [record.type for record in records]
    assert types.count("question/asked") == 1
    assert "question/answered" not in types
    assert "等你回答" in result.stdout
    assert "不应该跑到这一轮" not in result.stdout
    assert "[轮] 1/3" in result.stderr
    assert "[轮] 2/3" not in result.stderr
    assert "目标已暂停" in result.stderr


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

    fixture = _fixture(tmp_path, [{"content": "第二轮做完了", "finish_reason": "stop"}])
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

    assert _resume_round(env, "/goal pause") is None
    assert _resume_round(env, "/goal resume") is None  # 还没武装
    env.goal_runtime.armed = True
    assert _resume_round(env, "/goal") is None
    assert _resume_round(env, "/goal resume extra") is None

    decision = _resume_round(env, "/goal resume")
    assert decision is not None
    assert decision.round == 2
    assert decision.goal is not None

    paused = active.model_copy(update={"phase": "paused", "revision": 2})
    log.append("goal/updated", {"goal": paused.model_dump(exclude_none=True)})
    assert _resume_round(env, "/goal resume") is None

    at_cap = active.model_copy(update={"rounds_started": 3, "revision": 3})
    log.append("goal/updated", {"goal": at_cap.model_dump(exclude_none=True)})
    assert _resume_round(env, "/goal resume") is None

    log.append("goal/updated", {"goal": None})
    assert _resume_round(env, "/goal resume") is None
