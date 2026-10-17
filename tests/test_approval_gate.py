"""seam ②④：approval 门——只有会改动的工具问人，问与答都落到日志。

这里的工具是测试本地的桩：组 5 判的是「谁问人、问答怎么记账」，不是 `write` 本身。
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from mini_harness.events import EventLog, read_events
from mini_harness.loop import RunOutcome, SessionSettings, run_session
from mini_harness.loop.settings import ApprovalMode
from mini_harness.provider import FixtureProvider
from mini_harness.tools import ToolArgs, ToolRegistry, ToolResult
from mini_harness.tools.fences import ApprovalDecision, DispatchContext
from mini_harness.tools.registry import ToolDefinition


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


def _registry_and_entries(*, mutates: bool) -> tuple[ToolRegistry, list[dict[str, object]]]:
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
                {"id": "c1", "name": name, "arguments": {"file_path": "a.md", "content": "A\n"}},
                {"id": "c2", "name": name, "arguments": {"file_path": "b.md", "content": "B\n"}},
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
    log = EventLog.create(session_dir=tmp_path, session_id=session_id)
    settings = SessionSettings(
        workspace=tmp_path, provider_name="mock", max_turns=4, approval=approval
    )
    outcome = await run_session(
        prompt="任务",
        provider=FixtureProvider(entries=entries),
        log=log,
        registry=registry,
        settings=settings,
        cancel=asyncio.Event(),
        approval_gate=gate,
    )
    return log, outcome


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
