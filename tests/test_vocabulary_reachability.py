"""词表可达性：四份词表的每个取值都真的被跑出来一次（Active Lesson 1）。

断言的是「跑出来的取值集合 == 词表」：词表加了新取值而没人能跑到它，这条就红。
"""

from __future__ import annotations

import asyncio
import io
from pathlib import Path
from typing import get_args

from mini_harness.events import EventLog, read_events
from mini_harness.loop import STOP_REASONS
from mini_harness.provider import AssistantTurn
from mini_harness.tools import DispatchOutcome, ToolRegistry
from mini_harness.tools.fences import (
    ApprovalDecision,
    DispatchContext,
    FenceCode,
    StdinApprovalGate,
)
from mini_harness.tools.registry import (
    ToolArgs,
    ToolDefinition,
    ToolExecutor,
    ToolOutcome,
    ToolResult,
)
from tool_harness import (
    DONE,
    dispatch_call,
    run_fixture_session,
    run_session_fixture,
    tool_call_entry,
)


class _Gate:
    def __init__(self, decision: ApprovalDecision) -> None:
        self._decision = decision

    def request(self, *, tool_name: str, detail: str) -> ApprovalDecision:
        return self._decision


class _CancelDuringGenerate:
    def __init__(self, cancel: asyncio.Event) -> None:
        self._cancel = cancel

    async def generate(
        self,
        messages: object,
        tools: object,
        signal: asyncio.Event,
    ) -> AssistantTurn:
        self._cancel.set()
        return AssistantTurn(content="部分回复", finish_reason="stop")


class _Tty(io.StringIO):
    """能回答的流：`isatty()` 为真，`readline()` 取构造时给的内容。"""

    def isatty(self) -> bool:
        return True


async def _dispatch_with_gate(
    workspace: Path,
    decision: ApprovalDecision,
    *,
    name: str = "write",
    **arguments: object,
) -> DispatchOutcome:
    return await dispatch_call(
        workspace, name, dict(arguments), approval="ask", approval_gate=_Gate(decision)
    )


def _workspace(tmp_path: Path) -> Path:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    (workspace / "read.md").write_text("alpha\nbeta\nalpha\n", encoding="utf-8")
    (workspace / "stale.md").write_text("目标\n", encoding="utf-8")
    (workspace / "unread.md").write_text("原内容\n", encoding="utf-8")
    (workspace / "bin.dat").write_bytes(b"\xff\xfe\x00\x01")
    (workspace / "sub").mkdir()
    return workspace


def _stop_reasons(log: EventLog) -> set[str]:
    """`turn/end` 与 `session/end` 里出现过的停止原因。"""
    return {
        str(record.payload["stop_reason"])
        for record in read_events(log.path)
        if record.type in {"turn/end", "session/end"}
    }


class _NoArgs(ToolArgs):
    """桩工具没有入参。"""


async def _raise_timeout(args: ToolArgs, context: DispatchContext) -> ToolResult:
    raise TimeoutError("执行段超时")


async def _raise_cancelled(args: ToolArgs, context: DispatchContext) -> ToolResult:
    raise asyncio.CancelledError("执行段被打断")


def _raising_registry(name: str, run: ToolExecutor) -> ToolRegistry:
    """执行段抛异常的桩工具：判「异常塌成结果词、不逃逸出派发段」。"""
    return ToolRegistry(
        [
            ToolDefinition(
                name=name,
                description="执行段抛异常的桩工具",
                args_model=_NoArgs,
                mutates=False,
                run=run,
            )
        ]
    )


async def test_every_tool_outcome_is_reachable(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    log, _ = await run_fixture_session(
        workspace,
        "s-reach",
        [
            tool_call_entry("read", "c1", file_path="read.md"),
            tool_call_entry("read", "c2", file_path="stale.md"),
            DONE,
        ],
    )
    records = read_events(log.path)
    (workspace / "stale.md").write_text("别人改过了\n", encoding="utf-8")

    observed: set[str] = set()

    async def run(name: str, arguments: dict[str, object], **kwargs: object) -> None:
        outcome = await dispatch_call(workspace, name, arguments, **kwargs)
        observed.add(outcome.result.outcome)

    await run("read", {"file_path": "read.md"})
    await run("read", {"file_path": "missing.md"})
    await run("read", {"file_path": "sub"})
    await run("read", {"file_path": "bin.dat"})
    await run("read", {"file_path": 7})
    await run("write", {"file_path": "read.md/child.md", "content": "x\n"})
    await run("glob", {"pattern": "*", "path": "read.md"})
    await run("nosuch_tool", {})
    await run("write", {"file_path": "unread.md", "content": "改写\n"})
    await run(
        "edit",
        {"file_path": "read.md", "old_string": "alpha", "new_string": "x"},
        records=records,
    )
    await run(
        "edit",
        {"file_path": "read.md", "old_string": "不存在", "new_string": "x"},
        records=records,
    )
    await run(
        "edit",
        {"file_path": "stale.md", "old_string": "目标", "new_string": "x"},
        records=records,
    )
    await run("write", {"file_path": "unread.md", "content": "改写\n"}, sandbox="read-only")
    await run("write", {"file_path": "../outside.md", "content": "改写\n"})
    denied = await _dispatch_with_gate(workspace, "DENIED", file_path="new.md", content="x\n")
    observed.add(denied.result.outcome)
    await run("stub", {}, registry=_raising_registry("stub", _raise_timeout))
    await run("stub", {}, registry=_raising_registry("stub", _raise_cancelled))

    assert observed == set(get_args(ToolOutcome)), "有取值没被跑出来，或词表里多了跑不到的取值"


async def test_a_timeout_in_the_execution_segment_is_a_result(tmp_path: Path) -> None:
    """不变量 B：执行段超时塌成 `TOOL_TIMEOUT`，不抛异常打断回合。"""
    outcome = await dispatch_call(
        tmp_path, "stub", {}, registry=_raising_registry("stub", _raise_timeout)
    )
    assert outcome.result.outcome == "TOOL_TIMEOUT"


async def test_an_interrupted_execution_segment_is_a_result(tmp_path: Path) -> None:
    """不变量 B：执行段被打断塌成 `TOOL_CANCELLED`，不抛异常打断回合。"""
    outcome = await dispatch_call(
        tmp_path, "stub", {}, registry=_raising_registry("stub", _raise_cancelled)
    )
    assert outcome.result.outcome == "TOOL_CANCELLED"


async def test_every_fence_code_is_reachable(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    codes: set[str] = set()
    outcomes: set[str] = set()

    async def run(name: str, arguments: dict[str, object], **kwargs: object) -> None:
        outcome = await dispatch_call(workspace, name, arguments, **kwargs)
        outcomes.add(outcome.result.outcome)
        if outcome.fence_code is not None:
            codes.add(outcome.fence_code)

    await run("write", {"file_path": "../outside.md", "content": "x\n"})
    await run("write", {"file_path": "unread.md", "content": "x\n"}, sandbox="read-only")
    for decision in ("DENIED", "UNAVAILABLE"):
        outcome = await _dispatch_with_gate(workspace, decision, file_path="new.md", content="x\n")
        outcomes.add(outcome.result.outcome)
        if outcome.fence_code is not None:
            codes.add(outcome.fence_code)

    assert codes == set(get_args(FenceCode))
    assert outcomes == {"DENIED_BY_FENCE", "DENIED_BY_APPROVAL"}


def test_every_approval_decision_is_reachable() -> None:
    observed: set[str] = set()
    for answer in ("y\n", "n\n"):
        gate = StdinApprovalGate(stream=_Tty(answer), prompt_stream=io.StringIO())
        observed.add(gate.request(tool_name="write", detail="a.md"))
    silent = StdinApprovalGate(stream=io.StringIO("y\n"), prompt_stream=io.StringIO())
    observed.add(silent.request(tool_name="write", detail="a.md"))

    assert observed == set(get_args(ApprovalDecision))


async def test_every_stop_reason_is_reachable(tmp_path: Path) -> None:
    observed: set[str] = set()
    for index, entries in enumerate(
        (
            [DONE],
            [tool_call_entry("read", "c1", file_path="a.md"), DONE],
            [tool_call_entry("read", f"c{index}", file_path="a.md") for index in range(1, 5)],
            [],
        ),
        start=1,
    ):
        directory = tmp_path / f"case{index}"
        directory.mkdir()
        log, _ = await run_fixture_session(directory, f"s-case{index}", entries)
        observed |= _stop_reasons(log)

    cancelled = tmp_path / "cancelled"
    cancelled.mkdir()
    cancel = asyncio.Event()
    log, _ = await run_session_fixture(
        cancelled, "s-cancel", _CancelDuringGenerate(cancel), cancel=cancel, max_turns=8
    )
    observed |= _stop_reasons(log)

    denied = tmp_path / "denied"
    denied.mkdir()
    log, _ = await run_fixture_session(
        denied,
        "s-fence",
        [tool_call_entry("write", "c1", file_path="x.md", content="x\n")],
        approval="ask",
        approval_gate=_Gate("DENIED"),
        max_turns=8,
    )
    observed |= _stop_reasons(log)

    assert observed == set(STOP_REASONS)
