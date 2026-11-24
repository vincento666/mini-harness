"""goal 工具的写入面（M13 切片 3.2 - 3.4）：CAS、相位翻转、门槛与武装。

一条判据只钉一件事：结果词、日志里有没有新 `goal/updated`、快照怎么变。
"""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path
from typing import Any, cast

from mini_harness.events import EventLog, EventRecord, read_events
from mini_harness.goals import GoalPolicy
from mini_harness.loop import SessionEnv
from mini_harness.loop.settings import SessionSettings
from mini_harness.provider import Provider
from mini_harness.tools import ToolRegistry
from mini_harness.tools.goal import goal_tool_definitions
from tool_harness import dispatch_call


def _env(tmp_path: Path, *, armed: bool = False) -> SessionEnv:
    log = EventLog.create(tmp_path, session_id="s-goal")
    settings = SessionSettings(
        workspace=tmp_path,
        provider_name="mock",
        max_steps=4,
        sandbox="workspace-write",
        approval="auto",
        goal=GoalPolicy(max_rounds=8, blocked_after_consecutive_rounds=3),
    )
    env = SessionEnv(
        provider=cast(Provider, None), log=log, registry=ToolRegistry([]), settings=settings
    )
    env.goal_runtime.armed = armed
    return env


def _current(phase: str = "active", **overrides: Any) -> EventRecord:
    snapshot: dict[str, Any] = {
        "id": "g1",
        "revision": 2,
        "objective": "修好失败的用例",
        "phase": phase,
        "max_rounds": 8,
        "rounds_started": 1,
    }
    if phase == "blocked":
        snapshot["blocked_reason"] = {"code": "round-limit", "message": "轮次用尽"}
    snapshot.update(overrides)
    return EventRecord(
        schema_version=1,
        type="goal/updated",
        session_id="s-goal",
        seq=0,
        ts="2026-11-18T00:00:00+00:00",
        payload={"goal": snapshot},
    )


def _registry() -> ToolRegistry:
    return ToolRegistry(goal_tool_definitions())


async def _update(
    tmp_path: Path,
    env: SessionEnv,
    *,
    current: EventRecord | None = None,
    **arguments: Any,
) -> Any:
    passed = {key: arguments.pop(key) for key in ("entry", "human_driven") if key in arguments}
    body: dict[str, Any] = {"goal_id": "g1", "revision": 2}
    body.update(arguments)
    return await dispatch_call(
        tmp_path,
        "update_goal",
        body,
        registry=_registry(),
        session=env,
        records=[] if current is None else [current],
        **passed,
    )


def _new_snapshot(env: SessionEnv) -> dict[str, Any] | None:
    records = read_events(env.log.path)
    return None if not records else records[-1].payload["goal"]


async def test_edit_replaces_only_the_given_field(tmp_path: Path) -> None:
    env = _env(tmp_path)

    outcome = await _update(tmp_path, env, current=_current(), action="edit", max_rounds=5)

    assert outcome.result.outcome == "OK"
    goal = _new_snapshot(env)
    assert goal is not None
    assert goal["objective"] == "修好失败的用例"
    assert goal["max_rounds"] == 5
    assert goal["phase"] == "active"
    assert goal["revision"] == 3


async def test_edit_with_nothing_effective_is_rejected(tmp_path: Path) -> None:
    env = _env(tmp_path)

    outcome = await _update(
        tmp_path, env, current=_current(), action="edit", objective="", max_rounds=0
    )

    assert outcome.result.outcome == "TOOL_ARGS_INVALID"
    assert read_events(env.log.path) == []


async def test_a_stale_revision_is_rejected(tmp_path: Path) -> None:
    env = _env(tmp_path)

    outcome = await _update(tmp_path, env, current=_current(revision=3), action="pause", revision=2)

    assert outcome.result.outcome == "GOAL_REF_STALE"
    assert read_events(env.log.path) == []


async def test_a_stale_goal_id_is_rejected(tmp_path: Path) -> None:
    env = _env(tmp_path)

    outcome = await _update(
        tmp_path, env, current=_current(id="g-other"), action="pause", goal_id="g1"
    )

    assert outcome.result.outcome == "GOAL_REF_STALE"
    assert read_events(env.log.path) == []


async def test_update_without_a_goal_is_stale(tmp_path: Path) -> None:
    env = _env(tmp_path)

    outcome = await _update(tmp_path, env, action="pause")

    assert outcome.result.outcome == "GOAL_REF_STALE"
    assert read_events(env.log.path) == []


async def test_pause_moves_active_to_paused_and_disarms(tmp_path: Path) -> None:
    env = _env(tmp_path, armed=True)

    outcome = await _update(tmp_path, env, current=_current(), action="pause")

    assert outcome.result.outcome == "OK"
    goal = _new_snapshot(env)
    assert goal is not None
    assert goal["phase"] == "paused"
    assert goal["revision"] == 3
    assert env.goal_runtime.armed is False
    assert json.loads(outcome.result.content)["armed"] is False


async def test_pause_from_blocked_is_an_invalid_transition(tmp_path: Path) -> None:
    env = _env(tmp_path)

    outcome = await _update(tmp_path, env, current=_current("blocked"), action="pause")

    assert outcome.result.outcome == "GOAL_INVALID_TRANSITION"
    assert read_events(env.log.path) == []


async def test_complete_finishes_a_paused_goal(tmp_path: Path) -> None:
    env = _env(tmp_path, armed=True)

    outcome = await _update(tmp_path, env, current=_current("paused"), action="complete")

    assert outcome.result.outcome == "OK"
    goal = _new_snapshot(env)
    assert goal is not None
    assert goal["phase"] == "complete"
    assert env.goal_runtime.armed is False


async def test_complete_on_a_completed_goal_is_invalid(tmp_path: Path) -> None:
    env = _env(tmp_path)

    outcome = await _update(tmp_path, env, current=_current("complete"), action="complete")

    assert outcome.result.outcome == "GOAL_INVALID_TRANSITION"
    assert read_events(env.log.path) == []


async def test_resume_rearms_a_disarmed_active_goal(tmp_path: Path) -> None:
    env = _env(tmp_path)

    outcome = await _update(tmp_path, env, current=_current(), action="resume")

    assert outcome.result.outcome == "OK"
    goal = _new_snapshot(env)
    assert goal is not None
    assert goal["phase"] == "active"
    assert env.goal_runtime.armed is True


async def test_resume_on_a_paused_goal_is_denied_to_tools(tmp_path: Path) -> None:
    env = _env(tmp_path)

    outcome = await _update(tmp_path, env, current=_current("paused"), action="resume")

    assert outcome.result.outcome == "GOAL_RESUME_BY_TOOL_DENIED"
    assert read_events(env.log.path) == []


async def test_resume_from_blocked_clears_the_reason(tmp_path: Path) -> None:
    env = _env(tmp_path)

    outcome = await _update(tmp_path, env, current=_current("blocked"), action="resume")

    assert outcome.result.outcome == "OK"
    goal = _new_snapshot(env)
    assert goal is not None
    assert goal["phase"] == "active"
    assert "blocked_reason" not in goal
    assert env.goal_runtime.armed is True


async def test_resume_with_an_exhausted_cap_is_invalid(tmp_path: Path) -> None:
    env = _env(tmp_path)

    outcome = await _update(
        tmp_path,
        env,
        current=_current("blocked", rounds_started=8, max_rounds=8),
        action="resume",
    )

    assert outcome.result.outcome == "GOAL_INVALID_TRANSITION"
    assert read_events(env.log.path) == []


async def test_block_before_the_threshold_is_too_early(tmp_path: Path) -> None:
    env = _env(tmp_path)

    outcome = await _update(
        tmp_path,
        env,
        current=_current(rounds_started=2),
        action="blocked",
        blocked_reason="依赖的接口一直 502",
    )

    assert outcome.result.outcome == "GOAL_BLOCK_TOO_EARLY"
    assert read_events(env.log.path) == []


async def test_block_after_the_threshold_is_accepted(tmp_path: Path) -> None:
    env = _env(tmp_path, armed=True)

    outcome = await _update(
        tmp_path,
        env,
        current=_current(rounds_started=3),
        action="blocked",
        blocked_reason="依赖的接口一直 502",
    )

    assert outcome.result.outcome == "OK"
    goal = _new_snapshot(env)
    assert goal is not None
    assert goal["phase"] == "blocked"
    assert goal["blocked_reason"] == {
        "code": "model-reported",
        "message": "依赖的接口一直 502",
    }
    assert env.goal_runtime.armed is False


async def test_block_without_a_reason_is_an_argument_error(tmp_path: Path) -> None:
    env = _env(tmp_path)

    outcome = await _update(
        tmp_path, env, current=_current(rounds_started=3), action="blocked", blocked_reason="  "
    )

    assert outcome.result.outcome == "TOOL_ARGS_INVALID"
    assert read_events(env.log.path) == []


async def test_editing_from_a_subagent_has_no_authority(tmp_path: Path) -> None:
    env = _env(tmp_path)

    outcome = await _update(
        tmp_path, env, current=_current(), action="edit", objective="改掉", entry="subagent"
    )

    assert outcome.result.outcome == "GOAL_AUTHORITY_REQUIRED"
    assert read_events(env.log.path) == []


async def test_edit_can_replace_the_objective(tmp_path: Path) -> None:
    env = _env(tmp_path)

    outcome = await _update(
        tmp_path, env, current=_current(), action="edit", objective="改成另一件事"
    )

    assert outcome.result.outcome == "OK"
    goal = _new_snapshot(env)
    assert goal is not None
    assert goal["objective"] == "改成另一件事"
    assert goal["max_rounds"] == 8


async def test_resume_on_a_completed_goal_is_invalid(tmp_path: Path) -> None:
    env = _env(tmp_path)

    outcome = await _update(tmp_path, env, current=_current("complete"), action="resume")

    assert outcome.result.outcome == "GOAL_INVALID_TRANSITION"
    assert read_events(env.log.path) == []


async def test_resume_on_an_armed_active_goal_is_invalid(tmp_path: Path) -> None:
    env = _env(tmp_path, armed=True)

    outcome = await _update(tmp_path, env, current=_current(), action="resume")

    assert outcome.result.outcome == "GOAL_INVALID_TRANSITION"
    assert read_events(env.log.path) == []


async def test_block_from_a_non_active_phase_is_invalid(tmp_path: Path) -> None:
    env = _env(tmp_path)

    outcome = await _update(
        tmp_path,
        env,
        current=_current("paused", rounds_started=5),
        action="blocked",
        blocked_reason="已经暂停了还想报阻塞",
    )

    assert outcome.result.outcome == "GOAL_INVALID_TRANSITION"
    assert read_events(env.log.path) == []


async def test_update_in_a_goal_round_has_no_authority(tmp_path: Path) -> None:
    env = _env(tmp_path)

    outcome = await _update(tmp_path, env, current=_current(), action="pause", human_driven=False)

    assert outcome.result.outcome == "GOAL_AUTHORITY_REQUIRED"
    assert read_events(env.log.path) == []


async def test_update_without_a_session_cannot_write(tmp_path: Path) -> None:
    outcome = await dispatch_call(
        tmp_path,
        "update_goal",
        {"goal_id": "g1", "revision": 2, "action": "pause"},
        registry=_registry(),
        records=[_current()],
        session=None,
    )

    assert outcome.result.outcome == "TOOL_IO_FAILED"


async def test_update_reports_a_log_write_failure(tmp_path: Path) -> None:
    env = _env(tmp_path, armed=True)
    log_path = env.log.path
    os.chmod(log_path, stat.S_IREAD)
    try:
        outcome = await _update(tmp_path, env, current=_current(), action="pause")
    finally:
        os.chmod(log_path, stat.S_IREAD | stat.S_IWRITE)

    assert outcome.result.outcome == "TOOL_IO_FAILED"
    assert env.goal_runtime.armed is True


async def test_raising_the_cap_then_resuming_brings_a_blocked_goal_back(tmp_path: Path) -> None:
    """撞上限落 blocked 之后，人把上限改大再 resume——目标回到 active 且可再跑。"""
    env = _env(tmp_path)
    blocked = _current("blocked", rounds_started=8, max_rounds=8)

    edited = await _update(tmp_path, env, current=blocked, action="edit", max_rounds=16)
    assert edited.result.outcome == "OK"

    # 模型下一步读到的是刚写进去的那份快照（revision 3），不是它改之前的那份。
    raised = read_events(env.log.path)[-1]
    resumed = await _update(
        tmp_path,
        env,
        current=raised,
        revision=raised.payload["goal"]["revision"],
        action="resume",
    )

    assert resumed.result.outcome == "OK"
    goal = _new_snapshot(env)
    assert goal is not None
    assert goal["phase"] == "active"
    assert goal["max_rounds"] == 16
    assert goal["rounds_started"] == 8
    assert "blocked_reason" not in goal
    assert env.goal_runtime.armed is True
