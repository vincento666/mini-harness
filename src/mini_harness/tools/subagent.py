"""`subagent` 工具：spawn 一个独立子会话，父日志只留一对 tool 记录（M12 design D1-D6）。

工具层负责参数与结果词，内核负责子会话的 `run_session`、日志、深度/容量与取消。
父与子只共享工作区、围栏档位与 provider，不共享 approval 放行。
"""

from __future__ import annotations

import asyncio
import contextlib
from dataclasses import replace
from pathlib import Path

from pydantic import Field, field_validator

from mini_harness.events import EventLog, LogReadFailure, LogWriteFailure, read_events
from mini_harness.loop.settings import SandboxLevel, SessionSettings
from mini_harness.loop.turn_loop import (
    ENTRY_SUBAGENT,
    STOP_ABORTED,
    STOP_REASONS,
    SessionEnv,
    end_session,
    run_turn_segment,
    start_session,
)
from mini_harness.session.delegation import MAX_DEPTH, DelegationState
from mini_harness.tools.fences import UNAVAILABLE_APPROVAL_GATE, DispatchContext
from mini_harness.tools.registry import ToolArgs, ToolDefinition, ToolRegistry, ToolResult


class SubagentArgs(ToolArgs):
    """`subagent` 的入参：`task` 必须自足（spawn 不继承父会话的历史）。"""

    task: str = Field(description="自足的任务提示词：子会话看不到父会话的历史")
    max_turns: int | None = Field(default=None, ge=1, description="子会话的回合上限")
    tools: list[str] | None = Field(default=None, description="子会话可用的工具名")
    sandbox: SandboxLevel | None = Field(default=None, description="子会话的围栏档位")

    @field_validator("task")
    @classmethod
    def _task_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("task 不能是空白")
        return value


def subagent_tool_definitions() -> list[ToolDefinition]:
    """一个 `subagent` 定义；`parallel` 类别让同批的多个子代理真并发（design D5）。"""
    return [
        ToolDefinition(
            name="subagent",
            description=(
                "把一个自足的任务交给独立子会话执行，只取回它的最终文本（spawn）。"
                "子会话看不到父会话的历史，也不会继承审批放行。"
            ),
            args_model=SubagentArgs,
            mutates=False,
            run=_run_subagent,
            concurrency="parallel",
        )
    ]


def _child_settings(
    parent: SessionSettings,
    args: SubagentArgs,
    *,
    depth: int,
    parent_session_id: str,
    parent_tool_call_id: str | None,
) -> SessionSettings:
    """子会话继承档位/边界/provider 与 approval 模式，但审批门是 UNAVAILABLE（design D4）。

    模式（`auto` 钉定）是档位的一部分，随会话继承；一次性的「放行」不继承——
    子会话真要问人时只会得到不可用，不会由父代答、也不会自动放行。
    """
    return replace(
        parent,
        max_turns=parent.max_turns if args.max_turns is None else args.max_turns,
        sandbox=parent.sandbox if args.sandbox is None else args.sandbox,
        depth=depth,
        parent_session_id=parent_session_id,
        parent_tool_call_id=parent_tool_call_id,
    )


def _child_registry(parent: ToolRegistry, args: SubagentArgs) -> ToolRegistry | ToolResult:
    """子会话的工具表默认继承父会话；`tools` 给了就按名字筛，未知名是入参错误。"""
    if args.tools is None:
        return parent
    known = {definition.name for definition in parent.definitions()}
    unknown = [name for name in args.tools if name not in known]
    if unknown:
        return ToolResult(
            "TOOL_ARGS_INVALID",
            f"子会话请求了未注册的工具：{' / '.join(unknown)}",
        )
    wanted = set(args.tools)
    return ToolRegistry([d for d in parent.definitions() if d.name in wanted])


def _final_text(log_path: Path) -> str:
    """子会话的最终文本 = 最后一条非摘要 `model/response` 的正文；不把子日志交给父。"""
    records = read_events(log_path)
    if isinstance(records, LogReadFailure):
        return ""
    for record in reversed(records):
        if record.type == "model/response" and record.payload.get("purpose") is None:
            content = record.payload.get("content")
            return content if isinstance(content, str) else ""
    return ""


async def _run_child(env: SessionEnv, *, task: str, cancel: asyncio.Event) -> tuple[str, int, str]:
    """跑一个子会话：开始 → 恰一个段 → 结束；返回（停止理由，回合数，detail）。"""
    started = start_session(prompt=task, entry=ENTRY_SUBAGENT, env=env)
    if started is not None:
        return started.stop_reason, 0, started.detail
    segment = await run_turn_segment(env=env, segment_id="s1", first_turn_index=1, cancel=cancel)
    if segment.stop_reason not in STOP_REASONS:
        return segment.stop_reason, segment.turns, segment.detail
    ended = end_session(env=env, stop_reason=segment.stop_reason, turns=segment.turns)
    if ended is not None:
        return ended.stop_reason, ended.turns, ended.detail
    return segment.stop_reason, segment.turns, segment.detail


async def _forward_cancel(parent: asyncio.Event, child: asyncio.Event) -> None:
    """父段的取消传播到本段派生的子会话（design D6）。"""
    await parent.wait()
    child.set()


async def _run_subagent(args: SubagentArgs, context: DispatchContext) -> ToolResult:
    """深度与容量都是结果词；子会话的日志/过程只留在子会话自己那里。"""
    session = context.session
    if session is None:
        return ToolResult(
            "TOOL_IO_FAILED", "当前派发上下文没有会话运行时：subagent 只能在会话里调用"
        )
    parent = session.settings
    depth = parent.depth + 1
    if depth > MAX_DEPTH:
        return ToolResult(
            "DEPTH_EXCEEDED",
            f"子代理的深度 {depth} 超过 maxDepth {MAX_DEPTH}：子代理不能再派子代理",
        )
    delegation: DelegationState = session.delegation
    if delegation.active >= delegation.max_active:
        return ToolResult(
            "ACTIVATION_LIMIT_REACHED",
            f"每个父会话最多 {delegation.max_active} 个活跃子代理，"
            f"第 {delegation.active + 1} 个被拒绝",
        )
    child_registry = _child_registry(session.registry, args)
    if isinstance(child_registry, ToolResult):
        return child_registry

    child_log = EventLog.start(session.log.path.parent)
    if isinstance(child_log, LogWriteFailure):
        return ToolResult("TOOL_IO_FAILED", f"子会话日志建不出来：{child_log.detail}")
    child_env = SessionEnv(
        provider=session.provider,
        log=child_log,
        registry=child_registry,
        settings=_child_settings(
            parent,
            args,
            depth=depth,
            parent_session_id=session.log.session_id,
            parent_tool_call_id=context.tool_call_id,
        ),
        approval_gate=UNAVAILABLE_APPROVAL_GATE,
    )
    child_cancel = asyncio.Event()
    bridge: asyncio.Task[None] | None = None
    if context.cancel is not None:
        bridge = asyncio.create_task(_forward_cancel(context.cancel, child_cancel))
    delegation.active += 1
    task = asyncio.create_task(_run_child(child_env, task=args.task, cancel=child_cancel))
    try:
        try:
            # shield：父段取消不把子会话半路砍断，子会话自己按 ABORTED 收尾（design D6）。
            stop_reason, turns, _ = await asyncio.shield(task)
        except asyncio.CancelledError:
            child_cancel.set()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await asyncio.shield(task)
            raise
    finally:
        delegation.active -= 1
        if bridge is not None:
            bridge.cancel()
    if delegation.on_child_finished is not None:
        with contextlib.suppress(Exception):
            delegation.on_child_finished(child_env, turns)

    if stop_reason == STOP_ABORTED:
        return ToolResult("TOOL_CANCELLED", f"子会话 {child_log.session_id} 被取消")
    text = _final_text(child_log.path)
    if text:
        return ToolResult("OK", text)
    return ToolResult("OK", f"子会话 {child_log.session_id} 结束（{stop_reason}），没有最终文本")
