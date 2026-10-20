"""seam ③ 的 helper：不经 CLI 把一次调用跑完三段判定，或跑完一整段 fixture 回合。"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from mini_harness.events import EventLog, EventRecord, read_events
from mini_harness.loop import RunOutcome, SessionSettings, run_session
from mini_harness.loop.settings import ApprovalMode, SandboxLevel
from mini_harness.provider import FixtureProvider, Provider
from mini_harness.provider.contract import ToolCall
from mini_harness.tools import ToolRegistry
from mini_harness.tools.bash_tools import bash_tool_definitions
from mini_harness.tools.dispatch import DispatchOutcome, dispatch_tool_call
from mini_harness.tools.fences import (
    STDIN_APPROVAL_GATE,
    ApprovalDecision,
    ApprovalGate,
    DispatchContext,
    reads_from_records,
)
from mini_harness.tools.file_tools import file_tool_definitions
from mini_harness.tools.registry import ToolDefinition, ToolResult

# 一次工具执行的区间：(它操作的相对路径, 开始时刻, 结束时刻)。
Intervals = list[tuple[str, float, float]]

# 被包装的工具默认跑这么久：够长到能看出「同时在跑」，够短到测试不慢。
STEP_SECONDS = 0.05


class _ApprovingGate:
    """seam ③ 判的是工具契约，approval 在这里不是被测对象。"""

    async def request(self, *, tool_name: str, detail: str) -> ApprovalDecision:
        return "APPROVED"


def file_registry() -> ToolRegistry:
    """五个文件工具的注册表：helper 的默认注册表，也是「不注册 bash」的那一份。"""
    return ToolRegistry(file_tool_definitions())


def full_registry() -> ToolRegistry:
    """六个工具的注册表：文件工具加 `bash`。"""
    return ToolRegistry([*file_tool_definitions(), *bash_tool_definitions()])


async def cancel_after(cancel: asyncio.Event, seconds: float) -> None:
    """在 `seconds` 之后置位取消：让「取消落在批次中途」这件事可控。"""
    await asyncio.sleep(seconds)
    cancel.set()


def timed_registry(observed: Intervals, delays: dict[str, float] | None = None) -> ToolRegistry:
    """文件工具的契约原样保留，只把 `run` 包一层：先睡一小段，再记录执行区间。

    `delays` 按被操作的路径定制睡眠长度，用来让「谁先完成」与「谁还在跑」可控。
    """

    def wrap(definition: ToolDefinition) -> ToolDefinition:
        async def run(args: Any, context: DispatchContext) -> ToolResult:
            key = getattr(args, "file_path", definition.name)
            started = time.monotonic()
            await asyncio.sleep(STEP_SECONDS if delays is None else delays.get(key, STEP_SECONDS))
            result = await definition.run(args, context)
            observed.append((key, started, time.monotonic()))
            return result

        return ToolDefinition(
            name=definition.name,
            description=definition.description,
            args_model=definition.args_model,
            mutates=definition.mutates,
            run=run,
        )

    return ToolRegistry([wrap(definition) for definition in file_tool_definitions()])


def serialized_registry(observed: Intervals) -> ToolRegistry:
    """同一批调用被强制排队：并发跑与串行跑的对照组。"""
    gate = asyncio.Lock()

    def wrap(definition: ToolDefinition) -> ToolDefinition:
        async def run(args: Any, context: DispatchContext) -> ToolResult:
            key = getattr(args, "file_path", definition.name)
            async with gate:
                started = time.monotonic()
                result = await definition.run(args, context)
                observed.append((key, started, time.monotonic()))
            return result

        return ToolDefinition(
            name=definition.name,
            description=definition.description,
            args_model=definition.args_model,
            mutates=definition.mutates,
            run=run,
        )

    return ToolRegistry([wrap(definition) for definition in file_tool_definitions()])


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


def tool_call(name: str, call_id: str, **arguments: object) -> ToolCall:
    """契约里的一个工具调用，用来拼 `turn_entry` 的批次。"""
    return ToolCall(id=call_id, name=name, arguments=dict(arguments))


def turn_entry(*calls: ToolCall) -> dict[str, object]:
    """一次模型回复里声明多个调用：一个回合的派发批次就是这个形状。"""
    return {
        "content": "一次声明多个调用",
        "finish_reason": "tool_calls",
        "tool_calls": [call.model_dump(mode="json") for call in calls],
    }


def call_ids(records: Iterable[EventRecord], event_type: str) -> list[str]:
    """某一类事件里的 `tool_call_id`，按落盘顺序。"""
    return [str(record.payload["tool_call_id"]) for record in records if record.type == event_type]


def result_outcomes(records: Iterable[EventRecord]) -> list[tuple[str, str]]:
    """落盘的 `tool/result`：(它属于哪个调用, 结果词)，按落盘顺序。"""
    return [
        (str(record.payload["tool_call_id"]), str(record.payload["outcome"]))
        for record in records
        if record.type == "tool/result"
    ]


DONE: dict[str, object] = {"content": "算了", "finish_reason": "stop"}


async def run_session_fixture(
    tmp_path: Path,
    session_id: str,
    provider: Provider,
    *,
    workspace: Path | None = None,
    session_dir: Path | None = None,
    sandbox: SandboxLevel = "workspace-write",
    approval: ApprovalMode = "auto",
    max_turns: int = 8,
    prompt: str = "任务",
    provider_name: str = "mock",
    window: int = 128000,
    reserve: int = 8192,
    registry: ToolRegistry | None = None,
    approval_gate: ApprovalGate | None = None,
    cancel: asyncio.Event | None = None,
) -> tuple[EventLog, RunOutcome]:
    """seam ① 唯一的「跑完一整段 session」形状：建日志、建设置、调 `run_session`。

    注册表、档位、approval 门、取消信号、provider 与日志目录都从这里注入，测试文件里不再各自手搓。
    """
    log = EventLog.create(tmp_path if session_dir is None else session_dir, session_id=session_id)
    settings = SessionSettings(
        workspace=tmp_path if workspace is None else workspace,
        provider_name=provider_name,
        max_turns=max_turns,
        sandbox=sandbox,
        approval=approval,
        window=window,
        reserve=reserve,
    )
    outcome = await run_session(
        prompt=prompt,
        provider=provider,
        log=log,
        registry=file_registry() if registry is None else registry,
        settings=settings,
        cancel=asyncio.Event() if cancel is None else cancel,
        approval_gate=STDIN_APPROVAL_GATE if approval_gate is None else approval_gate,
    )
    return log, outcome


async def run_fixture_session(
    tmp_path: Path,
    session_id: str,
    entries: list[dict[str, object]],
    *,
    max_turns: int = 4,
    **options: Any,
) -> tuple[EventLog, RunOutcome]:
    """fixture provider 的常用形状：`entries` 造桩，其余透传给 `run_session_fixture`。"""
    return await run_session_fixture(
        tmp_path,
        session_id,
        FixtureProvider(entries=entries),
        max_turns=max_turns,
        **options,
    )


def tool_outcomes(log: EventLog) -> list[str]:
    results = [record for record in read_events(log.path) if record.type == "tool/result"]
    return [record.payload["outcome"] for record in results]
