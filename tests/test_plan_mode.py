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


class _Gate:
    def __init__(self, decision: str) -> None:
        self.decision = decision
        self.asked = 0

    async def request(self, *, tool_call_id, tool_name, detail):
        self.asked += 1
        return self.decision


async def _dispatch_exit(tmp_path, *, active: bool, decision: str):
    from mini_harness.config import build_registry
    from mini_harness.provider.contract import ToolCall
    from mini_harness.tools.dispatch import dispatch_tool_call
    from mini_harness.tools.fences import DispatchContext

    context = DispatchContext(
        workspace=tmp_path, sandbox="workspace-write", approval="ask", plan_active=active
    )
    gate = _Gate(decision)
    asked = []
    outcome = await dispatch_tool_call(
        ToolCall(id="c1", name="exit_plan_mode", arguments={"plan": "第一步：改 a"}),
        build_registry(None),
        context,
        gate,
        on_approval_request=lambda call: asked.append(call.id) or True,
    )
    return outcome, gate, asked


async def test_exit_plan_mode_requires_active_plan(tmp_path) -> None:
    outcome, gate, asked = await _dispatch_exit(tmp_path, active=False, decision="APPROVED")

    assert outcome.result.outcome == "TOOL_ARGS_INVALID"
    assert outcome.plan_exit is False
    assert gate.asked == 0
    assert asked == []


async def test_exit_plan_mode_approved_flips_plan(tmp_path) -> None:
    outcome, _gate, asked = await _dispatch_exit(tmp_path, active=True, decision="APPROVED")

    assert outcome.result.outcome == "OK"
    assert outcome.plan_exit is True
    assert outcome.approval == "APPROVED"
    assert asked == ["c1"]


async def test_exit_plan_mode_denied_keeps_plan(tmp_path) -> None:
    outcome, _, _ = await _dispatch_exit(tmp_path, active=True, decision="DENIED")

    assert outcome.result.outcome == "DENIED_BY_APPROVAL"
    assert outcome.plan_exit is False
    assert outcome.fence_code == "APPROVAL_DENIED"


def test_approval_payload_carries_plan_review() -> None:
    from mini_harness.loop.turn_loop import _approval_request_payload
    from mini_harness.provider.contract import ToolCall

    payload = _approval_request_payload(
        "t1", ToolCall(id="c1", name="exit_plan_mode", arguments={"plan": "第一步"})
    )
    assert payload["purpose"] == "plan-review"
    assert payload["plan"] == "第一步"

    plain = _approval_request_payload(
        "t1", ToolCall(id="c2", name="write", arguments={"file_path": "a"})
    )
    assert "purpose" not in plain


async def test_exit_plan_mode_unavailable_keeps_plan(tmp_path) -> None:
    outcome, _, _ = await _dispatch_exit(tmp_path, active=True, decision="UNAVAILABLE")

    assert outcome.result.outcome == "DENIED_BY_APPROVAL"
    assert outcome.plan_exit is False
    assert outcome.fence_code == "APPROVAL_UNAVAILABLE"
