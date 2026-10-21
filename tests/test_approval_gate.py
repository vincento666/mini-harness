"""seam ②④：approval 门——只有会改动的工具问人，问与答都落到日志。

这里的工具是测试本地的桩：组 5 判的是「谁问人、问答怎么记账」，不是 `write` 本身。
"""

from __future__ import annotations

import asyncio
import threading
from pathlib import Path
from typing import get_args

import pytest

from mini_harness.events import EventLog, read_events
from mini_harness.loop import RunOutcome
from mini_harness.loop.settings import ApprovalMode
from mini_harness.tools import ToolArgs, ToolRegistry, ToolResult
from mini_harness.tools.fences import ApprovalDecision, DispatchContext, StdinApprovalGate
from mini_harness.tools.registry import ToolDefinition
from tool_harness import DONE, call_ids, result_outcomes, run_fixture_session, tool_call, turn_entry


class _WriteArgs(ToolArgs):
    file_path: str
    content: str

    def target_path(self) -> str | None:
        return self.file_path


class _Gate:
    """假 approval 门：记录被问过谁，返回固定结论。"""

    def __init__(self, decision: ApprovalDecision) -> None:
        self.decision = decision
        self.asked: list[str] = []

    async def request(self, *, tool_name: str, detail: str) -> ApprovalDecision:
        self.asked.append(tool_name)
        return self.decision


async def _stub_write(args: _WriteArgs, context: DispatchContext) -> ToolResult:
    (context.workspace / args.file_path).write_text(args.content, encoding="utf-8")
    return ToolResult(outcome="OK", content=f"写了 {args.file_path}")


async def _stub_read(args: _WriteArgs, context: DispatchContext) -> ToolResult:
    return ToolResult(outcome="OK", content="读到了")


def _registry_and_entries(
    *, mutates: bool, files: tuple[str, ...] = ("a.md", "b.md")
) -> tuple[ToolRegistry, list[dict[str, object]]]:
    name = "write" if mutates else "read"
    registry = ToolRegistry(
        [
            ToolDefinition(
                name=name,
                description="测试桩工具",
                args_model=_WriteArgs,
                mutates=mutates,
                run=_stub_write if mutates else _stub_read,
            )
        ]
    )
    entries = [
        {
            "content": "动两个文件",
            "finish_reason": "tool_calls",
            "tool_calls": [
                {
                    "id": f"c{index}",
                    "name": name,
                    "arguments": {"file_path": path, "content": "A\n"},
                }
                for index, path in enumerate(files, start=1)
            ],
        },
        DONE,
    ]
    return registry, entries


async def _run(
    tmp_path: Path,
    session_id: str,
    registry: ToolRegistry,
    entries: list[dict[str, object]],
    gate: _Gate,
    *,
    approval: ApprovalMode = "ask",
) -> tuple[EventLog, RunOutcome]:
    return await run_fixture_session(
        tmp_path,
        session_id,
        entries,
        approval=approval,
        max_turns=4,
        registry=registry,
        approval_gate=gate,
    )


async def test_each_approved_write_asks_once_and_then_succeeds(tmp_path: Path) -> None:
    gate = _Gate("APPROVED")
    registry, entries = _registry_and_entries(mutates=True)

    log, _ = await _run(tmp_path, "s-approve", registry, entries, gate)

    records = read_events(log.path)
    requests = [record for record in records if record.type == "approval/request"]
    responses = [record for record in records if record.type == "approval/response"]
    assert len(requests) == 2
    assert len(responses) == 2
    assert [record.payload["decision"] for record in responses] == ["APPROVED", "APPROVED"]
    assert [record.payload["tool_call_id"] for record in requests] == ["c1", "c2"]
    assert [record.payload["tool_call_id"] for record in responses] == ["c1", "c2"]
    assert {record.payload["turn_id"] for record in requests} == {"t1"}
    assert [record.payload["outcome"] for record in records if record.type == "tool/result"] == [
        "OK",
        "OK",
    ]
    assert gate.asked == ["write", "write"]
    assert (tmp_path / "a.md").read_text(encoding="utf-8") == "A\n"


async def test_an_approved_call_keeps_its_relative_order_when_the_batch_interleaves(
    tmp_path: Path,
) -> None:
    """规格 scenario「一次带审批的写的事件序列」：保证的是同一个 `tool_call_id` 的相对顺序。

    并发批次里不同调用的记录可以交错——`c1` 的 `tool/call` 落在 `c2` 的 `approval/request` 之前，
    `c1` 的 `tool/result` 又落在 `c2` 的 `approval/response` 之前：`c2` 的那一组被 `c1` 的结果切开。
    「这四条连续」不是并发派发下成立的东西，它是串行执行的副产品（证明见 `design.md`）。
    """
    registry = ToolRegistry(
        [
            ToolDefinition(
                name="read",
                description="测试桩读",
                args_model=_WriteArgs,
                mutates=False,
                run=_stub_read,
            ),
            ToolDefinition(
                name="write",
                description="测试桩写",
                args_model=_WriteArgs,
                mutates=True,
                run=_stub_write,
            ),
        ]
    )
    entries = [
        turn_entry(
            tool_call("read", "c1", file_path="a.md", content=""),
            tool_call("write", "c2", file_path="b.md", content="B\n"),
        ),
        DONE,
    ]
    gate = _Gate("APPROVED")

    log, _ = await _run(tmp_path, "s-interleave", registry, entries, gate)

    records = read_events(log.path)
    at = {
        (record.type, record.payload.get("tool_call_id")): index
        for index, record in enumerate(records)
    }
    assert (
        at["tool/call", "c2"]
        < at["approval/request", "c2"]
        < at["approval/response", "c2"]
        < at["tool/result", "c2"]
    )
    assert at["tool/call", "c1"] < at["approval/request", "c2"]
    assert at["tool/result", "c1"] < at["approval/response", "c2"]
    assert call_ids(records, "tool/result") == ["c1", "c2"]
    assert gate.asked == ["write"]


async def test_a_denied_write_is_a_result_and_an_error_fence(tmp_path: Path) -> None:
    gate = _Gate("DENIED")
    registry, entries = _registry_and_entries(mutates=True, files=("a.md",))

    log, _ = await _run(tmp_path, "s-deny", registry, entries, gate)

    records = read_events(log.path)
    fences = [record for record in records if record.type == "error/fence"]
    assert len(fences) == 1
    assert fences[0].payload["turn_id"] == "t1"
    assert fences[0].payload["tool_call_id"] == "c1"
    assert fences[0].payload["code"] == "APPROVAL_DENIED"
    assert "a.md" in fences[0].payload["detail"]
    assert [record.payload["outcome"] for record in records if record.type == "tool/result"] == [
        "DENIED_BY_APPROVAL"
    ]
    assert [
        record.payload["decision"] for record in records if record.type == "approval/response"
    ] == ["DENIED"]
    assert not (tmp_path / "a.md").exists()


async def test_read_like_tools_never_ask_a_human(tmp_path: Path) -> None:
    gate = _Gate("APPROVED")
    registry, entries = _registry_and_entries(mutates=False)

    log, _ = await _run(tmp_path, "s-noask", registry, entries, gate)

    records = read_events(log.path)
    assert [record for record in records if record.type.startswith("approval/")] == []
    assert gate.asked == []
    assert [record.payload["outcome"] for record in records if record.type == "tool/result"] == [
        "OK",
        "OK",
    ]


async def test_auto_approval_writes_no_approval_records(tmp_path: Path) -> None:
    gate = _Gate("DENIED")
    registry, entries = _registry_and_entries(mutates=True)

    log, _ = await _run(tmp_path, "s-auto", registry, entries, gate, approval="auto")

    records = read_events(log.path)
    assert [record for record in records if record.type.startswith("approval/")] == []
    assert gate.asked == []
    assert [record.payload["outcome"] for record in records if record.type == "tool/result"] == [
        "OK",
        "OK",
    ]
    assert (tmp_path / "a.md").read_text(encoding="utf-8") == "A\n"


class _LogWatchingGate:
    """提问的那一刻回看日志：那一刻 `approval/request` 在不在盘上，是 5.6 的判据。"""

    def __init__(self, log_path: Path) -> None:
        self._log_path = log_path
        self.requested: list[bool] = []

    async def request(self, *, tool_name: str, detail: str) -> ApprovalDecision:
        self.requested.append(
            any(record.type == "approval/request" for record in read_events(self._log_path))
        )
        return "APPROVED"


async def test_the_request_is_on_disk_before_the_human_is_asked(tmp_path: Path) -> None:
    """规格：`approval/request` 在提问之前落盘。判据是门自己在提问那一刻回看日志。

    半对（有 `approval/request` 没有 `approval/response`）只允许出现在以 `error/abort`
    收尾的 session 里；这条 run 正常收尾，所以配对必须完整。
    """
    registry, entries = _registry_and_entries(mutates=True, files=("a.md",))
    gate = _LogWatchingGate(tmp_path / "s-early.jsonl")

    log, _ = await _run(tmp_path, "s-early", registry, entries, gate)

    assert gate.requested == [True]
    records = read_events(log.path)
    types = [record.type for record in records]
    assert types[types.index("tool/call") : types.index("tool/result")] == [
        "tool/call",
        "approval/request",
        "approval/response",
    ]
    requests = [r.payload["tool_call_id"] for r in records if r.type == "approval/request"]
    responses = [r.payload["tool_call_id"] for r in records if r.type == "approval/response"]
    assert requests == responses


class _Stream:
    """假 stdin：tty 可控、答案固定、写了什么看得见。"""

    def __init__(self, *, tty: bool, answer: str = "") -> None:
        self._tty = tty
        self._answer = answer
        self.written: list[str] = []

    def isatty(self) -> bool:
        return self._tty

    def write(self, text: str) -> int:
        self.written.append(text)
        return len(text)

    def flush(self) -> None:
        return None

    def readline(self) -> str:
        return self._answer


async def _ask(tty: bool, answer: str) -> ApprovalDecision:
    return await StdinApprovalGate(stream=_Stream(tty=tty, answer=answer)).request(
        tool_name="write", detail="a.md"
    )


async def test_the_three_approval_decisions_are_each_reachable_through_the_real_gate() -> None:
    assert set(get_args(ApprovalDecision)) == {"APPROVED", "DENIED", "UNAVAILABLE"}

    assert await _ask(tty=True, answer="y\n") == "APPROVED"
    assert await _ask(tty=True, answer="YES\n") == "APPROVED"
    assert await _ask(tty=True, answer="n\n") == "DENIED"
    assert await _ask(tty=True, answer="\n") == "DENIED"
    assert await _ask(tty=True, answer="也许\n") == "DENIED"
    assert await _ask(tty=False, answer="y\n") == "UNAVAILABLE"
    # Windows 上 NUL 设备也算 tty；读到 EOF 是「没有人在回答」，不是「人说了不」。
    assert await _ask(tty=True, answer="") == "UNAVAILABLE"

    stream = _Stream(tty=True, answer="y\n")
    prompt = _Stream(tty=True)
    await StdinApprovalGate(stream=stream, prompt_stream=prompt).request(
        tool_name="write", detail="C:\\ws\\a.md"
    )
    assert "write" in prompt.written[0]
    assert "a.md" in prompt.written[0]
    assert stream.written == []


async def test_the_default_gate_asks_on_stderr_and_leaves_stdout_empty(
    capsys: pytest.CaptureFixture[str],
) -> None:
    gate = StdinApprovalGate(stream=_Stream(tty=True, answer="y\n"))

    assert await gate.request(tool_name="write", detail="notes/plan.md") == "APPROVED"

    captured = capsys.readouterr()
    assert "write" in captured.err
    assert "notes/plan.md" in captured.err
    assert captured.out == ""


class _BrokenStream:
    """回答那条流坏了：`readline()` 抛 `OSError`，读起来是「没有人在回答」。"""

    def isatty(self) -> bool:
        return True

    def readline(self) -> str:
        raise OSError("流被关掉")


async def test_a_broken_answer_stream_reads_as_no_one_is_answering() -> None:
    """挂在 daemon 线程里的 `readline()` 抛异常时不能把等待者钉住：结论是 `UNAVAILABLE`。"""
    gate = StdinApprovalGate(stream=_BrokenStream(), prompt_stream=_Stream(tty=True))

    assert await gate.request(tool_name="write", detail="a.md") == "UNAVAILABLE"


class _BlockingStream:
    """tty，但回答永远不来：`readline()` 挂在人跟前，直到测试放行。"""

    def __init__(self) -> None:
        self.released = threading.Event()

    def isatty(self) -> bool:
        return True

    def readline(self) -> str:
        self.released.wait(timeout=10)
        return ""


async def _cancel_after(cancel: asyncio.Event, seconds: float) -> None:
    await asyncio.sleep(seconds)
    cancel.set()


async def test_a_cancel_interrupts_a_question_the_human_has_not_answered(tmp_path: Path) -> None:
    """真实门的 `readline()` 挂在人跟前时取消插得进来：事件循环没被一行回答钉住。

    这条判据要的是「run 已经以 `ABORTED` 收尾」这件事发生在回答之前——所以 `readline()`
    还挂着时整个 session 就该结束。半对（有 `approval/request`、没有 `approval/response`）
    在这里是合法的，因为 session 以 `error/abort` 收尾。
    """
    stream = _BlockingStream()
    gate = StdinApprovalGate(stream=stream, prompt_stream=_Stream(tty=True))
    cancel = asyncio.Event()
    watcher = asyncio.create_task(_cancel_after(cancel, 0.3))
    registry, entries = _registry_and_entries(mutates=True, files=("a.md",))

    log, outcome = await run_fixture_session(
        tmp_path,
        "s-ask-cancelled",
        entries,
        approval="ask",
        max_turns=4,
        registry=registry,
        approval_gate=gate,
        cancel=cancel,
    )
    await watcher

    records = read_events(log.path)
    assert isinstance(records, list)
    assert call_ids(records, "approval/request") == ["c1"]
    assert call_ids(records, "approval/response") == []
    assert result_outcomes(records) == [("c1", "TOOL_CANCELLED")]
    assert [record.type for record in records][-4:] == [
        "error/abort",
        "turn/end",
        "segment/end",
        "session/end",
    ]
    assert outcome.stop_reason == "ABORTED"
    assert not (tmp_path / "a.md").exists()

    stream.released.set()
