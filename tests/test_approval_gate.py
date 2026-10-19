"""seam ②④：approval 门——只有会改动的工具问人，问与答都落到日志。

这里的工具是测试本地的桩：组 5 判的是「谁问人、问答怎么记账」，不是 `write` 本身。
"""

from __future__ import annotations

from pathlib import Path
from typing import get_args

import pytest

from mini_harness.events import EventLog, read_events
from mini_harness.loop import RunOutcome
from mini_harness.loop.settings import ApprovalMode
from mini_harness.tools import ToolArgs, ToolRegistry, ToolResult
from mini_harness.tools.fences import ApprovalDecision, DispatchContext, StdinApprovalGate
from mini_harness.tools.registry import ToolDefinition
from tool_harness import run_fixture_session


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

    def request(self, *, tool_name: str, detail: str) -> ApprovalDecision:
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
        _DONE,
    ]
    return registry, entries


_DONE = {"content": "算了", "finish_reason": "stop"}


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


def _ask(tty: bool, answer: str) -> ApprovalDecision:
    return StdinApprovalGate(stream=_Stream(tty=tty, answer=answer)).request(
        tool_name="write", detail="a.md"
    )


def test_the_three_approval_decisions_are_each_reachable_through_the_real_gate() -> None:
    assert set(get_args(ApprovalDecision)) == {"APPROVED", "DENIED", "UNAVAILABLE"}

    assert _ask(tty=True, answer="y\n") == "APPROVED"
    assert _ask(tty=True, answer="YES\n") == "APPROVED"
    assert _ask(tty=True, answer="n\n") == "DENIED"
    assert _ask(tty=True, answer="\n") == "DENIED"
    assert _ask(tty=True, answer="也许\n") == "DENIED"
    assert _ask(tty=False, answer="y\n") == "UNAVAILABLE"
    # Windows 上 NUL 设备也算 tty；读到 EOF 是「没有人在回答」，不是「人说了不」。
    assert _ask(tty=True, answer="") == "UNAVAILABLE"

    stream = _Stream(tty=True, answer="y\n")
    prompt = _Stream(tty=True)
    StdinApprovalGate(stream=stream, prompt_stream=prompt).request(
        tool_name="write", detail="C:\\ws\\a.md"
    )
    assert "write" in prompt.written[0]
    assert "a.md" in prompt.written[0]
    assert stream.written == []


def test_the_default_gate_asks_on_stderr_and_leaves_stdout_empty(
    capsys: pytest.CaptureFixture[str],
) -> None:
    gate = StdinApprovalGate(stream=_Stream(tty=True, answer="y\n"))

    assert gate.request(tool_name="write", detail="notes/plan.md") == "APPROVED"

    captured = capsys.readouterr()
    assert "write" in captured.err
    assert "notes/plan.md" in captured.err
    assert captured.out == ""
