"""seam ⑥：`/goal` 四条命令（M13 task 5.2）——查看不写、暂停/恢复/清除各写一条。"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

from mini_harness.commands import execute_command
from mini_harness.events import EventLog, read_events
from mini_harness.events.writer import LogWriteFailure
from mini_harness.goals import GoalPolicy, GoalRuntime, GoalSnapshot, fold_goal


def _snapshot(**changes: Any) -> GoalSnapshot:
    base: dict[str, Any] = {
        "id": "g1",
        "revision": 1,
        "objective": "修好失败的用例",
        "phase": "active",
        "max_rounds": 3,
        "rounds_started": 0,
    }
    base.update(changes)
    return GoalSnapshot.model_validate(base)


def _env(log: EventLog, *, armed: bool = False) -> Any:
    return SimpleNamespace(
        log=log,
        goal_runtime=GoalRuntime(armed=armed),
        settings=SimpleNamespace(goal=GoalPolicy()),
    )


def _log(tmp_path: Path, snapshot: GoalSnapshot | None = None) -> EventLog:
    log = EventLog.create(tmp_path, session_id="s-goal-cmd")
    if snapshot is not None:
        log.append("goal/updated", {"goal": snapshot.model_dump(exclude_none=True)})
    return log


def _goal_events(log: EventLog) -> list[dict[str, Any]]:
    records = read_events(log.path)
    assert isinstance(records, list)
    return [record.payload for record in records if record.type == "goal/updated"]


def test_goal_view_prints_the_snapshot_without_writing(tmp_path: Path) -> None:
    log = _log(tmp_path, _snapshot(rounds_started=2))
    before = len(_goal_events(log))

    outcome = execute_command("goal", "", [], read_events(log.path), _env(log))

    assert outcome is not None and outcome.ok is True
    assert "修好失败的用例" in outcome.text
    assert "相位 active" in outcome.text
    assert "轮次 2/3" in outcome.text
    assert "未武装" in outcome.text
    assert len(_goal_events(log)) == before


def test_pause_writes_paused_and_disarms(tmp_path: Path) -> None:
    log = _log(tmp_path, _snapshot())
    env = _env(log, armed=True)

    outcome = execute_command("goal", "pause", [], read_events(log.path), env)

    assert outcome is not None and outcome.ok is True
    goal = fold_goal(read_events(log.path))
    assert goal is not None
    assert goal.phase == "paused"
    assert goal.revision == 2
    assert env.goal_runtime.armed is False


def test_resume_brings_paused_back_and_rearms(tmp_path: Path) -> None:
    log = _log(tmp_path, _snapshot(revision=2, phase="paused"))
    env = _env(log, armed=False)

    outcome = execute_command("goal", "resume", [], read_events(log.path), env)

    assert outcome is not None and outcome.ok is True
    goal = fold_goal(read_events(log.path))
    assert goal is not None
    assert goal.phase == "active"
    assert goal.revision == 3
    assert env.goal_runtime.armed is True


def test_resume_on_an_armed_active_goal_changes_nothing(tmp_path: Path) -> None:
    log = _log(tmp_path, _snapshot())
    env = _env(log, armed=True)
    before = len(_goal_events(log))

    outcome = execute_command("goal", "resume", [], read_events(log.path), env)

    assert outcome is not None and outcome.ok is True
    assert "已经在自动推进" in outcome.text
    assert len(_goal_events(log)) == before


def test_resume_at_the_cap_refuses(tmp_path: Path) -> None:
    """轮次用尽时 resume 会立刻再撞上限：先调大上限（照 DSH）。"""
    log = _log(
        tmp_path,
        _snapshot(
            phase="blocked",
            rounds_started=3,
            blocked_reason={"code": "round-limit", "message": "轮次用尽"},
        ),
    )
    env = _env(log)

    outcome = execute_command("goal", "resume", [], read_events(log.path), env)

    assert outcome is not None and outcome.ok is False
    assert "先调大 max_rounds" in outcome.text
    assert fold_goal(read_events(log.path)) is not None
    assert env.goal_runtime.armed is False


def test_clear_writes_null_and_disarms(tmp_path: Path) -> None:
    log = _log(tmp_path, _snapshot())
    env = _env(log, armed=True)

    outcome = execute_command("goal", "clear", [], read_events(log.path), env)

    assert outcome is not None and outcome.ok is True
    assert fold_goal(read_events(log.path)) is None
    assert _goal_events(log)[-1] == {"goal": None}
    assert env.goal_runtime.armed is False


def test_actions_without_a_goal_write_nothing(tmp_path: Path) -> None:
    log = _log(tmp_path)
    before = len(read_events(log.path))

    for action in ("pause", "resume", "clear"):
        outcome = execute_command("goal", action, [], read_events(log.path), _env(log))
        assert outcome is not None and outcome.ok is False
        assert "没有当前目标" in outcome.text

    assert len(read_events(log.path)) == before


def test_view_without_a_goal_is_not_an_error(tmp_path: Path) -> None:
    log = _log(tmp_path)

    outcome = execute_command("goal", "", [], read_events(log.path), _env(log))

    assert outcome is not None and outcome.ok is True
    assert outcome.text == "没有当前目标"


def test_an_unknown_action_is_a_usage_error(tmp_path: Path) -> None:
    log = _log(tmp_path, _snapshot())
    before = len(_goal_events(log))

    outcome = execute_command("goal", "跳一下", [], read_events(log.path), _env(log))

    assert outcome is not None and outcome.ok is False
    assert "用法" in outcome.text
    assert len(_goal_events(log)) == before


def test_viewing_a_blocked_goal_shows_the_reason(tmp_path: Path) -> None:
    log = _log(
        tmp_path,
        _snapshot(
            phase="blocked",
            rounds_started=3,
            blocked_reason={"code": "round-limit", "message": "轮次用尽"},
        ),
    )

    outcome = execute_command("goal", "", [], read_events(log.path), _env(log))

    assert outcome is not None and outcome.ok is True
    assert "相位 blocked" in outcome.text
    assert "阻塞 round-limit：轮次用尽" in outcome.text


def test_acting_without_a_runtime_is_refused(tmp_path: Path) -> None:
    """host 之外的入口（没有 env）不能改目标：写不了日志也翻不了武装位。"""
    log = _log(tmp_path, _snapshot())
    before = len(_goal_events(log))

    outcome = execute_command("goal", "pause", [], read_events(log.path), None)

    assert outcome is not None and outcome.ok is False
    assert "运行期状态" in outcome.text
    assert len(_goal_events(log)) == before


def test_a_pause_write_failure_keeps_the_goal_and_the_arm(tmp_path: Path, monkeypatch: Any) -> None:
    log = _log(tmp_path, _snapshot())
    env = _env(log, armed=True)
    monkeypatch.setattr(
        env.log, "append", lambda *args, **kwargs: LogWriteFailure(log.path, "只读")
    )

    outcome = execute_command("goal", "pause", [], read_events(log.path), env)

    assert outcome is not None and outcome.ok is False
    assert "写不进日志" in outcome.text
    assert env.goal_runtime.armed is True
    goal = fold_goal(read_events(log.path))
    assert goal is not None and goal.phase == "active"


def test_a_clear_write_failure_keeps_the_goal(tmp_path: Path, monkeypatch: Any) -> None:
    log = _log(tmp_path, _snapshot())
    env = _env(log, armed=True)
    monkeypatch.setattr(
        env.log, "append", lambda *args, **kwargs: LogWriteFailure(log.path, "只读")
    )

    outcome = execute_command("goal", "clear", [], read_events(log.path), env)

    assert outcome is not None and outcome.ok is False
    assert "清除写不进日志" in outcome.text
    assert fold_goal(read_events(log.path)) is not None
    assert env.goal_runtime.armed is True


def test_edit_changes_objective_without_touching_phase_or_arm(tmp_path: Path) -> None:
    """edit 只改正文：相位与武装位都不动（照 DSH 的 invariant）。"""
    log = _log(tmp_path, _snapshot(rounds_started=1))
    env = _env(log, armed=False)

    outcome = execute_command("goal", "edit 把测试修到全绿", [], read_events(log.path), env)

    assert outcome is not None and outcome.ok is True
    goal = fold_goal(read_events(log.path))
    assert goal is not None
    assert goal.objective == "把测试修到全绿"
    assert goal.max_rounds == 3
    assert goal.phase == "active"
    assert goal.revision == 2
    assert env.goal_runtime.armed is False


def test_edit_can_raise_the_cap_on_a_blocked_goal(tmp_path: Path) -> None:
    """轮次用尽后先调大上限，再 resume：这是唯一的解锁路径（照 DSH）。"""
    log = _log(
        tmp_path,
        _snapshot(
            phase="blocked",
            rounds_started=3,
            blocked_reason={"code": "round-limit", "message": "轮次用尽"},
        ),
    )
    env = _env(log)

    edited = execute_command("goal", "edit --max-rounds 8", [], read_events(log.path), env)
    assert edited is not None and edited.ok is True
    goal = fold_goal(read_events(log.path))
    assert goal is not None and goal.max_rounds == 8
    assert goal.phase == "blocked"

    resumed = execute_command("goal", "resume", [], read_events(log.path), env)
    assert resumed is not None and resumed.ok is True
    goal = fold_goal(read_events(log.path))
    assert goal is not None and goal.phase == "active"
    assert env.goal_runtime.armed is True


def test_edit_accepts_both_fields_and_rejects_bad_arguments(tmp_path: Path) -> None:
    log = _log(tmp_path, _snapshot())
    env = _env(log, armed=True)

    both = execute_command("goal", "edit --max-rounds 5 写成两节", [], read_events(log.path), env)
    assert both is not None and both.ok is True
    goal = fold_goal(read_events(log.path))
    assert goal is not None
    assert (goal.objective, goal.max_rounds) == ("写成两节", 5)

    before = len(_goal_events(log))
    for bad in ("edit", "edit --max-rounds", "edit --max-rounds 0", "edit --max-rounds x"):
        outcome = execute_command("goal", bad, [], read_events(log.path), env)
        assert outcome is not None and outcome.ok is False
        assert "用法" in outcome.text or "正整数" in outcome.text
    assert len(_goal_events(log)) == before
    assert env.goal_runtime.armed is True


def test_complete_writes_complete_and_disarms(tmp_path: Path) -> None:
    log = _log(tmp_path, _snapshot(rounds_started=2))
    env = _env(log, armed=True)

    outcome = execute_command("goal", "complete", [], read_events(log.path), env)

    assert outcome is not None and outcome.ok is True
    goal = fold_goal(read_events(log.path))
    assert goal is not None
    assert goal.phase == "complete"
    assert goal.revision == 2
    assert env.goal_runtime.armed is False


def test_complete_on_a_completed_goal_refuses(tmp_path: Path) -> None:
    log = _log(tmp_path, _snapshot(phase="complete"))
    env = _env(log)

    outcome = execute_command("goal", "complete", [], read_events(log.path), env)

    assert outcome is not None and outcome.ok is False
    assert "已经完成" in outcome.text


def test_edit_clamps_the_cap_to_the_deployment_ceiling(tmp_path: Path) -> None:
    """人类命令也走部署上限：要真的跑更多轮，改配置，不是敲一个大数字。"""
    log = _log(tmp_path, _snapshot(max_rounds=2))
    env = _env(log)

    outcome = execute_command("goal", "edit --max-rounds 100", [], read_events(log.path), env)

    assert outcome is not None and outcome.ok is True
    goal = fold_goal(read_events(log.path))
    assert goal is not None and goal.max_rounds == 32
