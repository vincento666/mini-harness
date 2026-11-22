"""CLI 的 `goal` 子命令：带参数的定义编辑住在命令行，不住在提示符（C 方案）。"""

from __future__ import annotations

from pathlib import Path

from mini_harness.cli.main import main
from mini_harness.events import EventLog, read_events
from mini_harness.goals import fold_goal

OBJECTIVE = "修好失败的用例"


def _seed(tmp_path: Path, *, max_rounds: int = 3) -> str:
    log = EventLog.create(tmp_path, session_id="s-goal")
    log.append(
        "goal/updated",
        {
            "goal": {
                "id": "g1",
                "revision": 1,
                "objective": OBJECTIVE,
                "phase": "active",
                "max_rounds": max_rounds,
                "rounds_started": 1,
            }
        },
    )
    return "s-goal"


def _run(tmp_path: Path, *args: str) -> int:
    return main(["goal", "s-goal", "--session-dir", str(tmp_path), *args])


def test_show_prints_the_snapshot(tmp_path: Path, capsys: object) -> None:
    _seed(tmp_path)

    assert _run(tmp_path, "show") == 0
    out = capsys.readouterr().out  # type: ignore[attr-defined]
    assert OBJECTIVE in out
    assert "轮次 1/3" in out


def test_edit_replaces_the_objective_and_the_cap(tmp_path: Path) -> None:
    _seed(tmp_path)

    assert _run(tmp_path, "edit", "--max-rounds", "8", "写成两节") == 0
    goal = fold_goal(read_events(tmp_path / "s-goal.jsonl"))
    assert goal is not None
    assert (goal.objective, goal.max_rounds) == ("写成两节", 8)
    assert goal.phase == "active"
    assert goal.revision == 2


def test_edit_clamps_the_cap_to_the_deployment_ceiling(tmp_path: Path) -> None:
    """离线命令也走部署上限：要跑更多轮就改配置，不是敲一个大数字。"""
    _seed(tmp_path, max_rounds=2)

    assert _run(tmp_path, "edit", "--max-rounds", "100") == 0
    goal = fold_goal(read_events(tmp_path / "s-goal.jsonl"))
    assert goal is not None and goal.max_rounds == 32


def test_edit_without_a_field_is_a_usage_error(tmp_path: Path) -> None:
    _seed(tmp_path)
    before = len(read_events(tmp_path / "s-goal.jsonl"))

    assert _run(tmp_path, "edit") == 2
    assert len(read_events(tmp_path / "s-goal.jsonl")) == before


def test_clear_writes_null(tmp_path: Path) -> None:
    _seed(tmp_path)

    assert _run(tmp_path, "clear") == 0
    assert fold_goal(read_events(tmp_path / "s-goal.jsonl")) is None


def test_a_missing_session_is_reported(tmp_path: Path) -> None:
    assert _run(tmp_path, "show") == 1
