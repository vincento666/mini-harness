"""seam ④：`plan/mode` 事件与折叠（M14c 切片 1）。"""

from __future__ import annotations

from mini_harness.commands import execute_command
from mini_harness.events.fold import fold_plan_mode, fold_questions
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


def test_todo_projection_clears_on_human_message() -> None:
    """M13 改了清空条件：段首单独不清，人类来源的驱动消息才清（goal 轮次保留）。"""
    from mini_harness.events.projection import project

    records = [
        _rec(0, "segment/start", {"segment_id": "s1"}),
        _rec(
            0, "user/message", {"segment_id": "s1", "content": "开工", "source": {"kind": "user"}}
        ),
        _rec(1, "todo/updated", {"items": [{"id": "t1", "text": "写判据", "status": "pending"}]}),
        _rec(2, "todo/updated", {"items": [{"id": "t1", "text": "写判据", "status": "completed"}]}),
        _rec(3, "segment/end", {}),
    ]

    value = project(records, "todos")["value"]
    assert value == [{"id": "t1", "text": "写判据", "status": "completed"}]

    cleared = project(
        [
            *records,
            _rec(4, "segment/start", {"segment_id": "s2"}),
            _rec(
                4,
                "user/message",
                {"segment_id": "s2", "content": "下一件事", "source": {"kind": "user"}},
            ),
        ],
        "todos",
    )["value"]
    assert cleared == []


async def test_todo_tool_reports_counts(tmp_path) -> None:
    from mini_harness.config import build_registry
    from mini_harness.provider.contract import ToolCall
    from mini_harness.tools.dispatch import dispatch_tool_call
    from mini_harness.tools.fences import DispatchContext

    async def never(call, detail):
        raise AssertionError("todo 不该触发审批")

    outcome = await dispatch_tool_call(
        ToolCall(
            id="c1",
            name="todo",
            arguments={
                "items": [
                    {"id": "t1", "text": "写判据", "status": "completed"},
                    {"id": "t2", "text": "实现", "status": "in_progress"},
                ]
            },
        ),
        build_registry(None),
        DispatchContext(workspace=tmp_path, sandbox="workspace-write", approval="auto"),
        never,
    )

    assert outcome.result.outcome == "OK"
    assert "0 待办" in outcome.result.content
    assert "1 进行中" in outcome.result.content
    assert "1 完成" in outcome.result.content


def test_todo_event_payload_only_for_successful_todo() -> None:
    from mini_harness.loop.turn_loop import _todo_event_payload
    from mini_harness.provider.contract import ToolCall

    call = ToolCall(id="c1", name="todo", arguments={"items": [{"id": "t1", "text": "x"}]})
    assert _todo_event_payload(call, "OK") == {
        "items": [{"id": "t1", "text": "x", "status": "pending"}]
    }
    assert _todo_event_payload(call, "TOOL_ARGS_INVALID") is None
    assert (
        _todo_event_payload(ToolCall(id="c2", name="write", arguments={"items": []}), "OK") is None
    )


def test_todo_command_prints_the_latest_table() -> None:
    records = [
        _rec(0, "segment/start", {"segment_id": "s1"}),
        _rec(
            1,
            "todo/updated",
            {"items": [{"id": "t1", "text": "写判据", "status": "completed"}]},
        ),
    ]

    outcome = execute_command("todo", "", [], records)

    assert outcome is not None
    assert outcome.ok is True
    assert "[completed] t1 写判据" in outcome.text
    assert execute_command("todo", "多余参数", [], records).ok is False


def test_todo_command_is_empty_without_events() -> None:
    outcome = execute_command("todo", "", [])

    assert outcome is not None
    assert outcome.text == "（没有待办）"


def test_question_pairs_fold() -> None:
    records = [
        _rec(
            0,
            "question/asked",
            {"question_id": "q1", "question": "用 A 还是 B", "options": ["A", "B"]},
        ),
        _rec(1, "question/asked", {"question_id": "q2", "question": "继续吗", "options": []}),
        _rec(2, "question/answered", {"question_id": "q1", "answer": "A"}),
    ]

    folded = fold_questions(records)
    assert folded[0]["answer"] == "A"
    assert folded[1]["answer"] is None


class _QGate:
    def __init__(self, answer: str | None) -> None:
        self.answer = answer

    async def request(self, *, question_id, question, options):
        return self.answer


async def _dispatch_ask(tmp_path, gate):
    from types import SimpleNamespace

    from mini_harness.config import build_registry
    from mini_harness.events import EventLog, read_events
    from mini_harness.provider.contract import ToolCall
    from mini_harness.tools.dispatch import dispatch_tool_call
    from mini_harness.tools.fences import DispatchContext

    log = EventLog.create(tmp_path, session_id="s-ask")
    context = DispatchContext(
        workspace=tmp_path,
        sandbox="workspace-write",
        approval="auto",
        session=SimpleNamespace(log=log),
    )
    if gate is not None:
        object.__setattr__(context, "question_gate", gate)
    outcome = await dispatch_tool_call(
        ToolCall(
            id="c1",
            name="ask_user",
            arguments={"question": "用 A 还是 B", "options": ["A", "B"]},
        ),
        build_registry(None),
        context,
        _QGate(None),
    )
    return outcome, read_events(log.path)


async def test_ask_user_records_pair(tmp_path) -> None:
    outcome, records = await _dispatch_ask(tmp_path, _QGate("A"))

    assert outcome.result.outcome == "OK"
    assert outcome.result.content == "A"
    assert [r.type for r in records] == ["question/asked", "question/answered"]
    assert fold_questions(records)[0]["answer"] == "A"


async def test_ask_user_unavailable_leaves_question_open(tmp_path) -> None:
    outcome, records = await _dispatch_ask(tmp_path, None)

    assert outcome.result.outcome == "QUESTION_UNAVAILABLE"
    assert [r.type for r in records] == ["question/asked"]
    assert fold_questions(records)[0]["answer"] is None


def test_stdin_question_gate_returns_none_off_tty() -> None:
    import asyncio
    import io

    from mini_harness.tools.fences import StdinQuestionGate

    gate = StdinQuestionGate(stream=io.StringIO("A\n"))
    answer = asyncio.run(gate.request(question_id="q1", question="用 A 吗", options=["A"]))
    assert answer is None


def test_stdin_question_gate_reads_answer_on_tty() -> None:
    import asyncio
    import io

    from mini_harness.tools.fences import StdinQuestionGate

    class _Tty(io.StringIO):
        def isatty(self) -> bool:
            return True

    gate = StdinQuestionGate(stream=_Tty("A\n"), prompt_stream=io.StringIO())
    answer = asyncio.run(gate.request(question_id="q1", question="用 A 吗", options=["A"]))
    assert answer == "A"


async def test_host_question_gate_resolves() -> None:
    import asyncio

    from mini_harness.session.host import HostQuestionGate, resolve_question

    class _Handle:
        def __init__(self) -> None:
            self.questions = {}
            self.stopping = False

    handle = _Handle()
    gate = HostQuestionGate(handle, timeout=1.0)  # type: ignore[arg-type]
    task = asyncio.create_task(gate.request(question_id="q1", question="用 A 吗", options=["A"]))
    await asyncio.sleep(0)
    assert resolve_question(handle, "q1", answer="A") is True  # type: ignore[arg-type]
    assert await task == "A"


async def test_host_question_gate_times_out() -> None:
    from mini_harness.session.host import HostQuestionGate

    class _Handle:
        def __init__(self) -> None:
            self.questions = {}
            self.stopping = False

    gate = HostQuestionGate(_Handle(), timeout=0.01)  # type: ignore[arg-type]
    assert await gate.request(question_id="q1", question="用 A 吗", options=[]) is None


async def _dispatch_present(tmp_path, path: str, title: str = "报告"):
    from mini_harness.config import build_registry
    from mini_harness.provider.contract import ToolCall
    from mini_harness.tools.dispatch import dispatch_tool_call
    from mini_harness.tools.fences import DispatchContext

    async def never(call, detail):
        raise AssertionError("present 不该触发审批")

    return await dispatch_tool_call(
        ToolCall(id="c1", name="present", arguments={"path": path, "title": title}),
        build_registry(None),
        DispatchContext(workspace=tmp_path, sandbox="workspace-write", approval="auto"),
        never,
    )


async def test_present_accepts_workspace_file(tmp_path) -> None:
    (tmp_path / "report.md").write_text("x", encoding="utf-8")

    outcome = await _dispatch_present(tmp_path, "report.md")

    assert outcome.result.outcome == "OK"
    assert outcome.result.content == "产物：report.md"
    from mini_harness.loop.turn_loop import _present_payload
    from mini_harness.provider.contract import ToolCall

    payload = _present_payload(
        ToolCall(id="c1", name="present", arguments={"path": "report.md", "title": "报告"}),
        outcome.result,
    )
    assert payload == {"path": "report.md", "title": "报告"}


async def test_present_rejects_outside_or_missing(tmp_path) -> None:
    outside = await _dispatch_present(tmp_path, "../escape.txt")
    assert outside.result.outcome == "PRESENT_INVALID_PATH"

    missing = await _dispatch_present(tmp_path, "nope.md")
    assert missing.result.outcome == "PRESENT_INVALID_PATH"


def test_command_usage_errors_cover_edges() -> None:
    assert execute_command("skills", "多余", []).ok is False
    assert execute_command("skill", "", []).ok is False
    assert execute_command("skill", "不存在", []).ok is False


async def test_present_rejects_existing_file_outside(tmp_path) -> None:
    outside = tmp_path.parent / "escape-present.md"
    outside.write_text("x", encoding="utf-8")

    outcome = await _dispatch_present(tmp_path, "../escape-present.md")

    assert outcome.result.outcome == "PRESENT_INVALID_PATH"


async def test_write_is_allowed_when_plan_is_inactive(tmp_path) -> None:
    from mini_harness.config import build_registry
    from mini_harness.provider.contract import ToolCall
    from mini_harness.tools.dispatch import dispatch_tool_call
    from mini_harness.tools.fences import DispatchContext

    async def never(call, detail):
        raise AssertionError("写新文件不该触发审批")

    outcome = await dispatch_tool_call(
        ToolCall(id="c1", name="write", arguments={"file_path": "a.txt", "content": "x"}),
        build_registry(None),
        DispatchContext(workspace=tmp_path, sandbox="workspace-write", approval="auto"),
        never,
    )

    assert outcome.result.outcome == "OK"
    assert (tmp_path / "a.txt").read_text(encoding="utf-8") == "x"


def test_cli_plan_command_writes_event(tmp_path) -> None:
    from types import SimpleNamespace

    from mini_harness.cli.main import _run_chat_command
    from mini_harness.events import EventLog, read_events

    log = EventLog.create(tmp_path, session_id="s-cli-plan")
    prepared = SimpleNamespace(log=log, skills_registry=None, settings=SimpleNamespace(skills={}))
    _run_chat_command(prepared, "/plan")
    assert fold_plan_mode(read_events(log.path)) is True

    _run_chat_command(prepared, "/plan off")
    assert fold_plan_mode(read_events(log.path)) is False


async def test_dispatch_batch_reads_plan_state_from_log(tmp_path) -> None:
    import asyncio

    from mini_harness.config import build_registry
    from mini_harness.events import EventLog, read_events
    from mini_harness.loop.settings import SessionSettings
    from mini_harness.loop.turn_loop import _dispatch_batch
    from mini_harness.provider.contract import ToolCall

    log = EventLog.create(tmp_path, session_id="s-batch")
    log.append("plan/mode", {"active": True})
    settings = SessionSettings(
        workspace=tmp_path,
        provider_name="mock",
        max_turns=8,
        sandbox="workspace-write",
        approval="auto",
    )
    gate = _Gate("APPROVED")
    call = ToolCall(id="c1", name="write", arguments={"file_path": "a.txt", "content": "x"})

    first = await _dispatch_batch(
        log=log,
        turn_id="t1",
        calls=[call],
        registry=build_registry(None),
        settings=settings,
        approval_gate=gate,
        cancel=asyncio.Event(),
    )
    assert first.failure is None
    results = [r.payload for r in read_events(log.path) if r.type == "tool/result"]
    assert results[-1]["outcome"] == "DENIED_BY_PLAN"
    assert not (tmp_path / "a.txt").exists()

    log.append("plan/mode", {"active": False})
    second = await _dispatch_batch(
        log=log,
        turn_id="t2",
        calls=[ToolCall(id="c2", name="write", arguments={"file_path": "a.txt", "content": "x"})],
        registry=build_registry(None),
        settings=settings,
        approval_gate=gate,
        cancel=asyncio.Event(),
    )
    assert second.failure is None
    assert (tmp_path / "a.txt").read_text(encoding="utf-8") == "x"
