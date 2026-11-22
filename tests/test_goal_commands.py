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


def test_edit_without_a_flag_replaces_the_objective(tmp_path: Path) -> None:
    """`/goal edit <正文>` 与 DSH 同形：正文靠自然语言，flag 不住在提示符上。"""
    log = _log(tmp_path, _snapshot())
    env = _env(log)

    outcome = execute_command("goal", "edit 把测试修到全绿", [], read_events(log.path), env)

    assert outcome is not None and outcome.ok is True
    goal = fold_goal(read_events(log.path))
    assert goal is not None and goal.objective == "把测试修到全绿"


def test_edit_without_text_is_a_usage_error(tmp_path: Path) -> None:
    log = _log(tmp_path, _snapshot())
    before = len(_goal_events(log))

    outcome = execute_command("goal", "edit", [], read_events(log.path), _env(log))

    assert outcome is not None and outcome.ok is False
    assert "用法" in outcome.text
    assert len(_goal_events(log)) == before


def test_a_bare_text_replaces_the_objective(tmp_path: Path) -> None:
    """`/goal <新正文>` 是最主流的形状；不是已知动词就整段当正文。"""
    log = _log(tmp_path, _snapshot())
    env = _env(log)

    outcome = execute_command("goal", "跳一下", [], read_events(log.path), env)

    assert outcome is not None and outcome.ok is True
    goal = fold_goal(read_events(log.path))
    assert goal is not None and goal.objective == "跳一下"
    assert goal.revision == 2


def test_a_bare_text_without_a_goal_is_refused_and_writes_nothing(tmp_path: Path) -> None:
    log = _log(tmp_path)
    before = len(_goal_events(log))

    outcome = execute_command("goal", "跳一下", [], read_events(log.path), _env(log))

    assert outcome is not None and outcome.ok is False
    assert "没有当前目标" in outcome.text
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


def test_replacing_the_objective_does_not_touch_phase_or_arm(tmp_path: Path) -> None:
    """替换正文只改定义：相位与武装位都不动（照 DSH 的 invariant）。"""
    log = _log(tmp_path, _snapshot(rounds_started=1))
    env = _env(log, armed=False)

    outcome = execute_command("goal", "把测试修到全绿", [], read_events(log.path), env)

    assert outcome is not None and outcome.ok is True
    goal = fold_goal(read_events(log.path))
    assert goal is not None
    assert goal.objective == "把测试修到全绿"
    assert goal.max_rounds == 3
    assert goal.phase == "active"
    assert goal.revision == 2
    assert env.goal_runtime.armed is False


def test_a_verb_does_not_take_arguments(tmp_path: Path) -> None:
    """`/goal pause 现在` 是打错了：不猜，直接报用法。"""
    log = _log(tmp_path, _snapshot())
    env = _env(log, armed=True)
    before = len(_goal_events(log))

    outcome = execute_command("goal", "pause 现在", [], read_events(log.path), env)

    assert outcome is not None and outcome.ok is False
    assert "不接受参数" in outcome.text
    assert len(_goal_events(log)) == before
    assert env.goal_runtime.armed is True


def test_an_empty_objective_is_refused(tmp_path: Path) -> None:
    log = _log(tmp_path, _snapshot())
    before = len(_goal_events(log))

    outcome = execute_command("goal", "   ", [], read_events(log.path), _env(log))

    assert outcome is not None and outcome.ok is True  # 空参数 = 查看
    assert len(_goal_events(log)) == before


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
