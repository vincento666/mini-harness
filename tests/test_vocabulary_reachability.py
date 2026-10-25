"""词表可达性：五份词表的每个取值都真的被跑出来一次（Active Lesson 1）。

断言的是「跑出来的取值集合 == 词表」：词表加了新取值而没人能跑到它，这条就红。
"""

from __future__ import annotations

import asyncio
import io
from pathlib import Path
from typing import get_args

import httpx

from mini_harness.events import EventLog, read_events
from mini_harness.events.fold import Message, fold
from mini_harness.loop import STOP_REASONS
from mini_harness.provider import AssistantTurn, ProviderFailure, load_fixture_provider
from mini_harness.provider.openai_compat import (
    CONTEXT_OVERFLOW_PHRASES,
    ContextOverflowPhrase,
    OpenAICompatProvider,
)
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
from paths import COMPACTION_SCENARIO
from tool_harness import (
    DONE,
    dispatch_call,
    file_registry,
    result_outcomes,
    run_fixture_session,
    run_session_fixture,
    tool_call_entry,
)


class _Gate:
    def __init__(self, decision: ApprovalDecision) -> None:
        self._decision = decision

    async def request(self, *, tool_name: str, detail: str) -> ApprovalDecision:
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

    # seam ①：取消在派发之前置位，声明了的调用没开始——那个取值只在回合循环里产出。
    cancel = asyncio.Event()
    cancel.set()
    cancelled, _ = await run_fixture_session(
        tmp_path,
        "s-reach-cancel",
        [tool_call_entry("write", "r1", file_path="one.md", content="一\n"), DONE],
        cancel=cancel,
    )
    cancelled_records = read_events(cancelled.path)
    assert isinstance(cancelled_records, list)
    observed.update(outcome for _, outcome in result_outcomes(cancelled_records))

    # seam ④：把上面那份日志里唯一一条结果抹掉，闭合由折叠派生——那个取值只在这里产出。
    last_result = max(
        index for index, record in enumerate(cancelled_records) if record.type == "tool/result"
    )
    half = [*cancelled_records[:last_result], *cancelled_records[last_result + 1 :]]
    vocabulary = set(get_args(ToolOutcome))
    observed.update(
        message.content
        for message in fold(half).messages
        if message.role == "tool" and message.content in vocabulary
    )

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


async def test_every_approval_decision_is_reachable() -> None:
    observed: set[str] = set()
    for answer in ("y\n", "n\n"):
        gate = StdinApprovalGate(stream=_Tty(answer), prompt_stream=io.StringIO())
        observed.add(await gate.request(tool_name="write", detail="a.md"))
    silent = StdinApprovalGate(stream=io.StringIO("y\n"), prompt_stream=io.StringIO())
    observed.add(await silent.request(tool_name="write", detail="a.md"))

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

    overflow = tmp_path / "overflow"
    overflow.mkdir()
    log, _ = await run_fixture_session(
        overflow,
        "s-overflow",
        [],
        prompt="x" * 100000,
        registry=ToolRegistry(),
        window=70000,
        reserve=100,
        max_turns=1,
    )
    observed |= _stop_reasons(log)

    assert observed == set(STOP_REASONS)


async def test_the_new_event_types_are_reached_by_a_real_run(tmp_path: Path) -> None:
    """M5 加进词表的两个事件类型各被跑出来一次：`compaction/summary` 与 `error/context`。

    同一份 fixture 场景、两个窗口：窗口 70000（触发线 4364、保留预算 11200）时装得下但需要压缩，
    窗口 4000（触发线 0）时装不下且无可遮蔽。
    """
    compacted = tmp_path / "compacted"
    compacted.mkdir()
    (compacted / "long.md").write_text("长" * 50000, encoding="utf-8")
    compacted_log, _ = await run_session_fixture(
        compacted,
        "s-compaction",
        load_fixture_provider(COMPACTION_SCENARIO),
        registry=file_registry(),
        window=70000,
        reserve=100,
        max_turns=4,
    )

    overflow = tmp_path / "overflow"
    overflow.mkdir()
    overflow_log, _ = await run_session_fixture(
        overflow,
        "s-overflow",
        load_fixture_provider(COMPACTION_SCENARIO),
        registry=file_registry(),
        window=4000,
        reserve=500,
        max_turns=4,
    )

    assert "compaction/summary" in {r.type for r in read_events(compacted_log.path)}
    assert "error/context" in {r.type for r in read_events(overflow_log.path)}


def _overflow_provider(message: str) -> OpenAICompatProvider:
    """400 加一句没有 `error.code` 的 `message`：真端点报超限的那种形状。"""
    return OpenAICompatProvider(
        base_url="http://127.0.0.1:9/v1",
        model="test-model",
        api_key=None,
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                400, json={"error": {"type": "invalid_request_error", "message": message}}
            )
        ),
    )


async def test_every_context_overflow_phrase_is_reachable() -> None:
    """短语表四条各被跑到一次，且是大写形式——大小写不敏感这条也一起判掉。"""
    reached: set[str] = set()
    for phrase in get_args(ContextOverflowPhrase):
        outcome = await _overflow_provider(f"Your request failed: {phrase.upper()}").generate(
            [Message(role="user", content="任务")], [], asyncio.Event()
        )
        if isinstance(outcome, ProviderFailure) and outcome.code == "PROVIDER_CONTEXT_OVERFLOW":
            reached.add(phrase)

    assert reached == CONTEXT_OVERFLOW_PHRASES, "有短语没被跑到，或词表里多了跑不到的短语"
