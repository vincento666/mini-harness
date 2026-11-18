"""goal 工具（M13 切片 3.1）：`get_goal` 与 `create_goal` 的权威与单目标。

判据只看两处：日志里落没落 `goal/updated`，以及结果 JSON 里有什么。
"""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path
from typing import Any, cast

from mini_harness.config import build_registry
from mini_harness.events import EventLog, EventRecord, read_events
from mini_harness.loop import SessionEnv
from mini_harness.loop.settings import SessionSettings
from mini_harness.provider import Provider
from mini_harness.tools import ToolRegistry
from mini_harness.tools.goal import goal_tool_definitions
from tool_harness import dispatch_call


def _env(tmp_path: Path) -> SessionEnv:
    """只要日志与进程内武装位：goal 工具不碰 provider，也不碰工作区。"""
    log = EventLog.create(tmp_path, session_id="s-goal")
    settings = SessionSettings(
        workspace=tmp_path,
        provider_name="mock",
        max_turns=4,
        sandbox="workspace-write",
        approval="auto",
    )
    return SessionEnv(
        provider=cast(Provider, None), log=log, registry=ToolRegistry([]), settings=settings
    )


def _registry() -> ToolRegistry:
    return ToolRegistry(goal_tool_definitions())


def _seeded(phase: str, **overrides: Any) -> list[EventRecord]:
    snapshot: dict[str, Any] = {
        "id": "g-old",
        "revision": 2,
        "objective": "旧目标",
        "phase": phase,
        "max_rounds": 8,
        "rounds_started": 1,
    }
    snapshot.update(overrides)
    return [
        EventRecord(
            schema_version=1,
            type="goal/updated",
            session_id="s-goal",
            seq=0,
            ts="2026-11-18T00:00:00+00:00",
            payload={"goal": snapshot},
        )
    ]


async def _call(
    tmp_path: Path,
    env: SessionEnv,
    name: str,
    arguments: dict[str, Any],
    **kwargs: Any,
) -> Any:
    return await dispatch_call(
        tmp_path,
        name,
        arguments,
        registry=_registry(),
        session=env,
        **kwargs,
    )


async def test_get_goal_without_a_goal_returns_null(tmp_path: Path) -> None:
    env = _env(tmp_path)

    outcome = await _call(tmp_path, env, "get_goal", {})

    assert outcome.result.outcome == "OK"
    assert json.loads(outcome.result.content) == {"goal": None}


async def test_create_goal_logs_one_snapshot_and_arms(tmp_path: Path) -> None:
    env = _env(tmp_path)

    outcome = await _call(tmp_path, env, "create_goal", {"objective": "修好失败的用例"})

    assert outcome.result.outcome == "OK"
    records = read_events(env.log.path)
    assert [record.type for record in records] == ["goal/updated"]
    goal = records[0].payload["goal"]
    assert goal["revision"] == 1
    assert goal["phase"] == "active"
    assert goal["rounds_started"] == 0
    assert goal["max_rounds"] == 32
    assert goal["objective"] == "修好失败的用例"
    assert "armed" not in goal

    view = json.loads(outcome.result.content)
    assert view["goal"]["id"] == goal["id"]
    assert view["armed"] is True
    assert env.goal_runtime.armed is True


async def test_create_goal_honours_the_requested_cap(tmp_path: Path) -> None:
    env = _env(tmp_path)

    outcome = await _call(tmp_path, env, "create_goal", {"objective": "短跑", "max_rounds": 5})

    assert outcome.result.outcome == "OK"
    assert read_events(env.log.path)[0].payload["goal"]["max_rounds"] == 5


async def test_a_non_positive_cap_is_an_argument_error(tmp_path: Path) -> None:
    env = _env(tmp_path)

    outcome = await _call(tmp_path, env, "create_goal", {"objective": "零轮", "max_rounds": 0})

    assert outcome.result.outcome == "TOOL_ARGS_INVALID"
    assert read_events(env.log.path) == []


async def test_create_goal_rejects_a_second_active_goal(tmp_path: Path) -> None:
    env = _env(tmp_path)

    outcome = await _call(
        tmp_path, env, "create_goal", {"objective": "第二个"}, records=_seeded("active")
    )

    assert outcome.result.outcome == "GOAL_ALREADY_ACTIVE"
    assert read_events(env.log.path) == []


async def test_a_completed_goal_may_be_replaced(tmp_path: Path) -> None:
    env = _env(tmp_path)

    outcome = await _call(
        tmp_path, env, "create_goal", {"objective": "新目标"}, records=_seeded("complete")
    )

    assert outcome.result.outcome == "OK"
    goal = read_events(env.log.path)[0].payload["goal"]
    assert goal["id"] != "g-old"
    assert goal["revision"] == 1
    assert goal["rounds_started"] == 0


async def test_a_subagent_has_no_goal_authority(tmp_path: Path) -> None:
    env = _env(tmp_path)

    outcome = await _call(
        tmp_path, env, "create_goal", {"objective": "子会话里开目标"}, entry="subagent"
    )

    assert outcome.result.outcome == "GOAL_AUTHORITY_REQUIRED"
    assert read_events(env.log.path) == []


async def test_a_goal_round_has_no_goal_authority(tmp_path: Path) -> None:
    env = _env(tmp_path)

    outcome = await _call(
        tmp_path, env, "create_goal", {"objective": "轮次里再开一个"}, human_driven=False
    )

    assert outcome.result.outcome == "GOAL_AUTHORITY_REQUIRED"
    assert read_events(env.log.path) == []


async def test_create_goal_without_a_session_cannot_write(tmp_path: Path) -> None:
    outcome = await dispatch_call(
        tmp_path, "create_goal", {"objective": "没有会话"}, registry=_registry()
    )

    assert outcome.result.outcome == "TOOL_IO_FAILED"


async def test_create_goal_reports_a_log_write_failure(tmp_path: Path) -> None:
    env = _env(tmp_path)
    log_path = env.log.path
    os.chmod(log_path, stat.S_IREAD)
    try:
        outcome = await _call(tmp_path, env, "create_goal", {"objective": "写不进日志"})
    finally:
        os.chmod(log_path, stat.S_IREAD | stat.S_IWRITE)

    assert outcome.result.outcome == "TOOL_IO_FAILED"
    assert env.goal_runtime.armed is False


def test_the_default_registry_mounts_the_goal_tools() -> None:
    """生产装配走 build_registry：目标工具不在那里，模型永远调不到 create_goal。"""
    registry = build_registry(None)

    assert isinstance(registry, ToolRegistry)
    names = {tool.name for tool in registry.definitions()}
    assert {"get_goal", "create_goal", "update_goal"} <= names
