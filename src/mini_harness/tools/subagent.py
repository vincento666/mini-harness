"""`subagent` 工具：spawn 一个独立子会话，父日志只留一对 tool 记录（M12 design D1-D6）。

工具层负责参数与结果词，内核负责子会话的 `run_session_env`、日志、深度/容量与取消。
父与子只共享工作区、围栏档位与 provider，不共享 approval 放行。
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from pathlib import Path as FilePath
from typing import Any, Literal

from pydantic import ConfigDict, Field, create_model, field_validator

from mini_harness.events import EventLog, LogReadFailure, LogWriteFailure, read_events
from mini_harness.loop.settings import SandboxLevel, SessionSettings
from mini_harness.loop.turn_loop import (
    ENTRY_SUBAGENT,
    STOP_FENCE_DENIED,
    STOP_PROVIDER_ERROR,
    STOP_REASONS,
    RunOutcome,
    SessionEnv,
    run_session_env,
)
from mini_harness.session.delegation import MAX_ACTIVE_SUBAGENTS, MAX_DEPTH, DelegationState
from mini_harness.tools.fences import UNAVAILABLE_APPROVAL_GATE, DispatchContext
from mini_harness.tools.registry import (
    ToolArgs,
    ToolDefinition,
    ToolOutcome,
    ToolRegistry,
    ToolResult,
)

# 档位的宽窄顺序：子会话只能比父会话更窄，不能更宽（ADR-0036）。
_SANDBOX_WIDTH: dict[str, int] = {"read-only": 0, "workspace-write": 1, "danger-full-access": 2}


@dataclass(frozen=True)
class SubagentPresets:
    """部署定义的子会话 preset：默认档、模型可选的白名单、以及每档的工具表。

    `registries` 里存的是**已编译好的**子工具表（从内置目录按 preset 的名字组合），
    spawn 时只按 id 取用；这是「组合」，不是授权。
    """

    default: str | None
    allowed: tuple[str, ...]
    registries: Mapping[str, ToolRegistry]
    personas: Mapping[str, str] = field(default_factory=dict)

    def registry_for(self, preset_id: str) -> ToolRegistry | None:
        return self.registries.get(preset_id)

    def persona_for(self, preset_id: str) -> str | None:
        return self.personas.get(preset_id)


class SubagentArgs(ToolArgs):
    """`subagent` 的入参：`task` 必须自足（spawn 不继承父会话的历史）。

    `agent_preset` 只在部署配了白名单时由 `_args_model` 动态加上；没有任意工具名列表。
    """

    model_config = ConfigDict(extra="forbid")

    task: str = Field(description="自足的任务提示词：子会话看不到父会话的历史")
    max_turns: int | None = Field(default=None, ge=1, description="子会话的回合上限")
    sandbox: SandboxLevel | None = Field(
        default=None, description="子会话的围栏档位：只能比父会话更窄"
    )

    @field_validator("task")
    @classmethod
    def _task_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("task 不能是空白")
        return value


def _args_model(presets: SubagentPresets | None) -> type[SubagentArgs]:
    """有白名单时把 `agent_preset` 加成枚举；没有白名单时字段不出现（模型不能选）。"""
    if presets is None or not presets.allowed:
        return SubagentArgs
    literal = Literal[tuple(presets.allowed)]  # type: ignore[valid-type]
    annotation: Any = literal | None
    return create_model(
        "SubagentArgsWithPreset",
        __base__=SubagentArgs,
        agent_preset=(
            annotation,
            Field(default=None, description="子会话的 preset id，取值是部署给的白名单"),
        ),
    )


def subagent_tool_definitions(presets: SubagentPresets | None = None) -> list[ToolDefinition]:
    """一个 `subagent` 定义；`parallel` 类别让同批的多个子代理真并发（design D5）。"""
    args_model = _args_model(presets)

    async def run(args: SubagentArgs, context: DispatchContext) -> ToolResult:
        return await _run_subagent(args, context, presets)

    return [
        ToolDefinition(
            name="subagent",
            description=(
                "把一个自足的任务交给独立子会话执行，只取回它的最终文本（spawn）。"
                "子会话看不到父会话的历史，也不会继承审批放行；工具面由部署的 preset 决定。"
            ),
            args_model=args_model,
            mutates=False,
            run=run,
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
    preset: str | None,
    persona: str | None,
) -> SessionSettings | ToolResult:
    """子会话继承档位/边界/provider 与 approval 模式，但审批门是 UNAVAILABLE（design D4）。

    模式（`auto` 钉定）是档位的一部分，随会话继承；一次性的「放行」不继承——
    子会话真要问人时只会得到不可用，不会由父代答、也不会自动放行。
    `sandbox` 参数只能把档位收窄：放宽容许子会话绕过服务器级的许可（ADR-0036）。
    """
    sandbox = parent.sandbox
    if args.sandbox is not None:
        if _SANDBOX_WIDTH[args.sandbox] > _SANDBOX_WIDTH[parent.sandbox]:
            return ToolResult(
                "TOOL_ARGS_INVALID",
                f"子会话的档位不能比父会话宽：父是 {parent.sandbox}，请求 {args.sandbox}",
            )
        sandbox = args.sandbox
    return replace(
        parent,
        max_turns=parent.max_turns if args.max_turns is None else args.max_turns,
        sandbox=sandbox,
        depth=depth,
        parent_session_id=parent_session_id,
        parent_tool_call_id=parent_tool_call_id,
        subagent_preset=preset,
        preset_persona=persona,
    )


def _chosen_preset(args: SubagentArgs, presets: SubagentPresets | None) -> str | None:
    """模型选的白名单档 → 部署的默认档；都没有就是「继承父的组合」。"""
    explicit = getattr(args, "agent_preset", None)
    if isinstance(explicit, str) and explicit:
        return explicit
    return None if presets is None else presets.default


def _final_text(log_path: FilePath) -> str:
    """子会话的最终文本 = 最后一条非摘要 `model/response` 的正文；不把子日志交给父。"""
    records = read_events(log_path)
    if isinstance(records, LogReadFailure):
        return ""
    for record in reversed(records):
        if record.type == "model/response" and record.payload.get("purpose") is None:
            content = record.payload.get("content")
            return content if isinstance(content, str) else ""
    return ""


def _child_result(env: SessionEnv, outcome: RunOutcome) -> ToolResult:
    """子会话收尾 → 父的结果。内核失败与模型失败都是失败，不能读成「成功了但没说话」。"""
    session_id = env.log.session_id
    if outcome.stop_reason == STOP_PROVIDER_ERROR:
        return ToolResult(
            "TOOL_IO_FAILED",
            f"子会话 {session_id} 的模型调用失败（{outcome.failure_code}）：{outcome.detail}",
        )
    if outcome.stop_reason == STOP_FENCE_DENIED:
        # 子会话被围栏拒绝：父拿到的也是拒绝结果词，不能读成「成功了但没做成」。
        # 父自己的回合不因此终止——被拒的是子会话，父还能决定换个做法。
        code = outcome.failure_code or "DENIED_BY_FENCE"
        denied: ToolOutcome = (
            "DENIED_BY_APPROVAL" if code.startswith("APPROVAL_") else "DENIED_BY_FENCE"
        )
        content = f"子会话 {session_id} 被围栏拒绝（{code}）：{outcome.detail or code}"
        text = _final_text(env.log.path)
        if text:
            content += f"\n子会话最后的文本：{text}"
        return ToolResult(denied, content)
    if outcome.stop_reason not in STOP_REASONS:
        return ToolResult(
            "TOOL_IO_FAILED",
            f"子会话 {session_id} 内核失败（{outcome.stop_reason}）：{outcome.detail}",
        )
    text = _final_text(env.log.path)
    if text:
        return ToolResult("OK", text)
    return ToolResult("OK", f"子会话 {session_id} 结束（{outcome.stop_reason}），没有最终文本")


async def _run_subagent(
    args: SubagentArgs, context: DispatchContext, presets: SubagentPresets | None
) -> ToolResult:
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
    if delegation.active >= MAX_ACTIVE_SUBAGENTS:
        return ToolResult(
            "ACTIVATION_LIMIT_REACHED",
            f"每个父会话最多 {MAX_ACTIVE_SUBAGENTS} 个活跃子代理，"
            f"第 {delegation.active + 1} 个被拒绝",
        )
    preset = _chosen_preset(args, presets)
    persona = None if preset is None or presets is None else presets.persona_for(preset)
    child_registry = session.registry
    if preset is not None:
        # preset 决定工具面：从部署 preset 编译好的表里取，不导入父的局部工具限制。
        registry = None if presets is None else presets.registry_for(preset)
        if registry is None:
            return ToolResult("TOOL_ARGS_INVALID", f"未知的 preset：{preset}")
        child_registry = registry
    child_settings = _child_settings(
        parent,
        args,
        depth=depth,
        parent_session_id=session.log.session_id,
        parent_tool_call_id=context.tool_call_id,
        preset=preset,
        persona=persona,
    )
    if isinstance(child_settings, ToolResult):
        return child_settings

    child_log = EventLog.start(session.log.path.parent)
    if isinstance(child_log, LogWriteFailure):
        return ToolResult("TOOL_IO_FAILED", f"子会话日志建不出来：{child_log.detail}")
    child_env = SessionEnv(
        provider=session.provider,
        log=child_log,
        registry=child_registry,
        settings=child_settings,
        approval_gate=UNAVAILABLE_APPROVAL_GATE,
    )
    child_cancel = asyncio.Event()
    delegation.active += 1
    task = asyncio.create_task(
        run_session_env(prompt=args.task, entry=ENTRY_SUBAGENT, env=child_env, cancel=child_cancel)
    )
    try:
        try:
            # shield：父段取消不把子会话半路砍断，子会话自己按 ABORTED 收尾（design D6）。
            # 父取消到达执行器的方式是 `CancelledError`，所以取消桥就只需要下面这一行。
            outcome = await asyncio.shield(task)
        except asyncio.CancelledError:
            child_cancel.set()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await asyncio.shield(task)
            raise
    finally:
        delegation.active -= 1
        finished = delegation.on_child_finished
        if finished is not None:
            # 被取消的子会话也要登记：它照样留下了一份完整的子日志（design D7）。
            with contextlib.suppress(Exception):
                finished(child_env)
    return _child_result(child_env, outcome)
