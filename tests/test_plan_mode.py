"""seam ④：`plan/mode` 事件与折叠（M14c 切片 1）。"""

from __future__ import annotations

from mini_harness.commands import execute_command
from mini_harness.events.fold import fold_plan_mode
from mini_harness.events.record import EventRecord


def _rec(seq: int, event_type: str, payload: dict[str, object]) -> EventRecord:
    return EventRecord(
        schema_version=1,
        session_id="s-plan",
        seq=seq,
        ts=f"2026-11-16T00:00:{seq:02d}+00:00",
        type=event_type,
        payload=payload,
    )


def test_plan_mode_defaults_to_false() -> None:
    records = [_rec(0, "session/start", {"prompt": "任务"})]

    assert fold_plan_mode(records) is False


def test_plan_mode_takes_the_last_value() -> None:
    records = [
        _rec(1, "plan/mode", {"active": True}),
        _rec(2, "plan/mode", {"active": False}),
        _rec(3, "plan/mode", {"active": True}),
    ]

    assert fold_plan_mode(records) is True


def test_plan_command_enters_and_exits() -> None:
    entered = execute_command("plan", "", [])
    assert entered is not None
    assert entered.ok is True
    assert entered.plan_active is True

    left = execute_command("plan", "off", [])
    assert left is not None
    assert left.ok is True
    assert left.plan_active is False

    invalid = execute_command("plan", "别的参数", [])
    assert invalid is not None
    assert invalid.ok is False
    assert invalid.plan_active is None


async def test_plan_mode_blocks_writes_before_side_effects(tmp_path) -> None:
    from mini_harness.config import build_registry
    from mini_harness.provider.contract import ToolCall
    from mini_harness.tools.dispatch import dispatch_tool_call
    from mini_harness.tools.fences import DispatchContext

    async def never_asked(call, detail):  # 计划拦截在审批之前，不该走到这里
        raise AssertionError("计划模式不应触发审批")

    context = DispatchContext(
        workspace=tmp_path, sandbox="workspace-write", approval="auto", plan_active=True
    )
    registry = build_registry(None)
    calls = [
        ("write", {"file_path": "a.txt", "content": "x"}),
        ("edit", {"file_path": "a.txt", "old_string": "a", "new_string": "b"}),
        ("bash", {"command": "echo hi > a.txt"}),
        ("subagent", {"prompt": "写 a.txt"}),
    ]

    for name, arguments in calls:
        outcome = await dispatch_tool_call(
            ToolCall(id="c1", name=name, arguments=arguments), registry, context, never_asked
        )
        assert outcome.result.outcome == "DENIED_BY_PLAN"
        assert outcome.result.content.startswith("计划模式：")

    assert not (tmp_path / "a.txt").exists()
