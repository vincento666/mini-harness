"""seam ②⑥：`[goal]` 三键的读取与 `todo` 并行纪律（M13 task 2.2）。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from mini_harness.config import build_registry
from mini_harness.config.assembly import build_goal_policy
from mini_harness.config.load import ConfigFailure
from mini_harness.goals import GoalPolicy
from mini_harness.provider.contract import ToolCall
from mini_harness.tools.dispatch import dispatch_tool_call
from mini_harness.tools.fences import DispatchContext


def test_defaults_when_the_section_is_absent() -> None:
    policy = build_goal_policy(None)

    assert policy.max_rounds == 32
    assert policy.blocked_after_consecutive_rounds == 3
    assert policy.allow_parallel_in_progress is True


def test_partial_section_keeps_the_other_defaults() -> None:
    policy = build_goal_policy({"max_rounds": 5})

    assert policy.max_rounds == 5
    assert policy.blocked_after_consecutive_rounds == 3
    assert policy.allow_parallel_in_progress is True


def test_zero_max_rounds_is_a_config_failure() -> None:
    failure = build_goal_policy({"max_rounds": 0})

    assert isinstance(failure, ConfigFailure)
    assert failure.code == "CONFIG_INVALID_VALUE"


def test_unknown_key_is_a_config_failure() -> None:
    failure = build_goal_policy({"max_round": 5})

    assert isinstance(failure, ConfigFailure)
    assert failure.code == "CONFIG_UNKNOWN_KEY"


def test_non_bool_parallel_flag_is_a_config_failure() -> None:
    failure = build_goal_policy({"allow_parallel_in_progress": "yes"})

    assert isinstance(failure, ConfigFailure)
    assert failure.code == "CONFIG_INVALID_VALUE"


def test_threshold_above_the_cap_is_rejected() -> None:
    """门槛大于上限会让 GOAL_BLOCK_TOO_EARLY 永远不消失——配置层直接拒。"""
    failure = build_goal_policy({"max_rounds": 2, "blocked_after_consecutive_rounds": 3})

    assert isinstance(failure, ConfigFailure)
    assert failure.code == "CONFIG_INVALID_VALUE"


async def _dispatch_todo(tmp_path: Path, policy: GoalPolicy) -> Any:
    async def never(call: Any, detail: Any) -> None:
        raise AssertionError("todo 不该触发审批")

    return await dispatch_tool_call(
        ToolCall(
            id="c1",
            name="todo",
            arguments={
                "items": [
                    {"id": "t1", "text": "写判据", "status": "in_progress"},
                    {"id": "t2", "text": "改实现", "status": "in_progress"},
                ]
            },
        ),
        build_registry(None),
        DispatchContext(
            workspace=tmp_path,
            sandbox="workspace-write",
            approval="auto",
            goal_policy=policy,
        ),
        never,
    )


async def test_two_in_progress_allowed_by_default(tmp_path: Path) -> None:
    outcome = await _dispatch_todo(tmp_path, GoalPolicy())

    assert outcome.result.outcome == "OK"


async def test_two_in_progress_rejected_when_parallel_is_off(tmp_path: Path) -> None:
    outcome = await _dispatch_todo(tmp_path, GoalPolicy(allow_parallel_in_progress=False))

    assert outcome.result.outcome == "TODO_PARALLEL_DISABLED"
