"""seam ③ 的 helper：不经 CLI 把一次调用跑完三段判定，或跑完一整段 fixture 回合。"""

from __future__ import annotations

import asyncio
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from mini_harness.events import EventLog, EventRecord, read_events
from mini_harness.loop import RunOutcome, SessionSettings, run_session
from mini_harness.loop.settings import ApprovalMode, SandboxLevel
from mini_harness.provider import FixtureProvider
from mini_harness.provider.contract import ToolCall
from mini_harness.tools import ToolRegistry
from mini_harness.tools.dispatch import DispatchOutcome, dispatch_tool_call
from mini_harness.tools.fences import (
    STDIN_APPROVAL_GATE,
    ApprovalDecision,
    ApprovalGate,
    DispatchContext,
    reads_from_records,
)
from mini_harness.tools.file_tools import file_tool_definitions


class _ApprovingGate:
    """seam ③ 判的是工具契约，approval 在这里不是被测对象。"""

    def request(self, *, tool_name: str, detail: str) -> ApprovalDecision:
        return "APPROVED"


def file_registry() -> ToolRegistry:
    """五个文件工具的注册表：helper 的默认注册表，也是「不注册 bash」的那一份。"""
    return ToolRegistry(file_tool_definitions())


def dispatch_context(
    workspace: Path,
    *,
    sandbox: SandboxLevel = "workspace-write",
    approval: ApprovalMode = "auto",
    records: Iterable[EventRecord] | None = None,
) -> DispatchContext:
    """seam ②③ 判据共用的围栏上下文。`SessionSettings` 只在这里构造一次。"""
    settings = SessionSettings(
        workspace=workspace,
        provider_name="mock",
        max_turns=8,
        sandbox=sandbox,
        approval=approval,
    )
    reads = None if records is None else reads_from_records(records, workspace)
    return DispatchContext.from_settings(settings, reads=reads)


async def dispatch_call(
    workspace: Path,
    name: str,
    arguments: dict[str, Any],
    *,
    sandbox: SandboxLevel = "workspace-write",
    approval: ApprovalMode = "auto",
    records: Iterable[EventRecord] | None = None,
    registry: ToolRegistry | None = None,
    approval_gate: ApprovalGate | None = None,
) -> DispatchOutcome:
    """跑完一次派发判定。注册表与 approval 门都可注入。"""
    call = ToolCall(id="c1", name=name, arguments=arguments)
    return await dispatch_tool_call(
        call,
        file_registry() if registry is None else registry,
        dispatch_context(workspace, sandbox=sandbox, approval=approval, records=records),
        _ApprovingGate() if approval_gate is None else approval_gate,
    )


def tool_call_entry(name: str, call_id: str, **arguments: object) -> dict[str, object]:
    return {
        "content": f"调用 {name}",
        "finish_reason": "tool_calls",
        "tool_calls": [{"id": call_id, "name": name, "arguments": dict(arguments)}],
    }


DONE: dict[str, object] = {"content": "算了", "finish_reason": "stop"}


async def run_fixture_session(
    tmp_path: Path,
    session_id: str,
    entries: list[dict[str, object]],
    *,
    sandbox: SandboxLevel = "workspace-write",
    approval: ApprovalMode = "auto",
    max_turns: int = 4,
    registry: ToolRegistry | None = None,
    approval_gate: ApprovalGate | None = None,
    cancel: asyncio.Event | None = None,
) -> tuple[EventLog, RunOutcome]:
    """跑完一整段 fixture 回合。注册表、档位、approval 门、取消信号都可注入。"""
    log = EventLog.create(session_dir=tmp_path, session_id=session_id)
    settings = SessionSettings(
        workspace=tmp_path,
        provider_name="mock",
        max_turns=max_turns,
        sandbox=sandbox,
        approval=approval,
    )
    outcome = await run_session(
        prompt="任务",
        provider=FixtureProvider(entries=entries),
        log=log,
        registry=file_registry() if registry is None else registry,
        settings=settings,
        cancel=asyncio.Event() if cancel is None else cancel,
        approval_gate=STDIN_APPROVAL_GATE if approval_gate is None else approval_gate,
    )
    return log, outcome


def tool_outcomes(log: EventLog) -> list[str]:
    results = [record for record in read_events(log.path) if record.type == "tool/result"]
    return [record.payload["outcome"] for record in results]
