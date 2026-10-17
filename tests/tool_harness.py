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
from mini_harness.tools.fences import ApprovalDecision, DispatchContext, reads_from_records
from mini_harness.tools.file_tools import file_tool_definitions


class _ApprovingGate:
    """seam ③ 判的是工具契约，approval 在这里不是被测对象。"""

    def request(self, *, tool_name: str, detail: str) -> ApprovalDecision:
        return "APPROVED"


async def dispatch_call(
    workspace: Path,
    name: str,
    arguments: dict[str, Any],
    *,
    sandbox: SandboxLevel = "workspace-write",
    approval: ApprovalMode = "auto",
    records: Iterable[EventRecord] | None = None,
) -> DispatchOutcome:
    settings = SessionSettings(
        workspace=workspace,
        provider_name="mock",
        max_turns=8,
        sandbox=sandbox,
        approval=approval,
    )
    reads = None if records is None else reads_from_records(records, workspace)
    context = DispatchContext.from_settings(settings, reads=reads)
    call = ToolCall(id="c1", name=name, arguments=arguments)
    registry = ToolRegistry(file_tool_definitions())
    return await dispatch_tool_call(call, registry, context, _ApprovingGate())


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
    approval: ApprovalMode = "auto",
) -> tuple[EventLog, RunOutcome]:
    log = EventLog.create(session_dir=tmp_path, session_id=session_id)
    settings = SessionSettings(
        workspace=tmp_path, provider_name="mock", max_turns=4, approval=approval
    )
    outcome = await run_session(
        prompt="任务",
        provider=FixtureProvider(entries=entries),
        log=log,
        registry=ToolRegistry(file_tool_definitions()),
        settings=settings,
        cancel=asyncio.Event(),
    )
    return log, outcome


def tool_outcomes(log: EventLog) -> list[str]:
    results = [record for record in read_events(log.path) if record.type == "tool/result"]
    return [record.payload["outcome"] for record in results]
