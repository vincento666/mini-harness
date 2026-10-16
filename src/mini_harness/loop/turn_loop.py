"""显式回合主循环：记账 → 装配上下文 → 调模型 → 派发工具 → 判定停止。"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path

from mini_harness.events.fold import fold
from mini_harness.events.reader import read_events
from mini_harness.events.record import SCHEMA_VERSION
from mini_harness.events.writer import EventLog
from mini_harness.provider.contract import Provider, ProviderFailure
from mini_harness.tools.dispatch import dispatch_tool_call
from mini_harness.tools.registry import ToolRegistry

STOP_MODEL_COMPLETED = "MODEL_COMPLETED"
STOP_MAX_TURNS = "MAX_TURNS"
STOP_PROVIDER_ERROR = "PROVIDER_ERROR"
STOP_ABORTED = "ABORTED"


@dataclass(frozen=True)
class RunOutcome:
    """一次运行的结果：CLI 层据此映射退出码。"""

    session_id: str
    stop_reason: str
    turns: int
    failure_code: str | None = None
    detail: str = ""


async def run_session(
    *,
    prompt: str,
    provider: Provider,
    provider_name: str,
    log: EventLog,
    registry: ToolRegistry,
    workspace: Path,
    max_turns: int,
    cancel: asyncio.Event,
    append_system_prompt: str = "",
) -> RunOutcome:
    """跑完一个 session 的全部回合。"""
    log.append(
        "session/start",
        {
            "schema_version": SCHEMA_VERSION,
            "workspace": str(Path(workspace).resolve()),
            "provider": provider_name,
            "max_turns": max_turns,
            "append_system_prompt": append_system_prompt,
            "prompt": prompt,
        },
    )

    stop_reason = STOP_MODEL_COMPLETED
    turns = 0
    for turn_index in range(1, max_turns + 1):
        turns = turn_index
        turn_id = f"t{turn_index}"
        log.append("turn/start", {"turn_id": turn_id})

        context = fold(
            read_events(log.path),
            append_system_prompt=append_system_prompt,
            tool_descriptions=[spec.name for spec in registry.specs()],
        )
        log.append("context/assembled", context.model_dump(mode="json"))
        log.append(
            "model/request",
            {"turn_id": turn_id, "tools": [spec.name for spec in registry.specs()]},
        )

        generated = await provider.generate(context.messages, registry.specs(), cancel)
        if isinstance(generated, ProviderFailure):
            log.append(
                "error/model",
                {"turn_id": turn_id, "code": generated.code, "detail": generated.detail},
            )
            log.append("turn/end", {"turn_id": turn_id, "stop_reason": STOP_PROVIDER_ERROR})
            log.append("session/end", {"stop_reason": STOP_PROVIDER_ERROR, "turns": turns})
            return RunOutcome(
                session_id=log.session_id,
                stop_reason=STOP_PROVIDER_ERROR,
                turns=turns,
                failure_code=generated.code,
                detail=generated.detail,
            )

        log.append(
            "model/response",
            {
                "turn_id": turn_id,
                "content": generated.content,
                "tool_calls": [call.model_dump(mode="json") for call in generated.tool_calls],
                "usage": generated.usage.model_dump(mode="json"),
                "finish_reason": generated.finish_reason,
            },
        )

        for call in generated.tool_calls:
            log.append(
                "tool/call",
                {
                    "turn_id": turn_id,
                    "tool_call_id": call.id,
                    "name": call.name,
                    "arguments": call.arguments,
                },
            )
            result = await dispatch_tool_call(call, registry)
            log.append(
                "tool/result",
                {
                    "turn_id": turn_id,
                    "tool_call_id": call.id,
                    "outcome": result.outcome,
                    "content": result.content,
                },
            )

        if cancel.is_set():
            stop_reason = STOP_ABORTED
        elif not generated.tool_calls:
            stop_reason = STOP_MODEL_COMPLETED
        elif turn_index == max_turns:
            stop_reason = STOP_MAX_TURNS
        else:
            stop_reason = STOP_MODEL_COMPLETED
        log.append("turn/end", {"turn_id": turn_id, "stop_reason": stop_reason})
        if (
            cancel.is_set()
            or not generated.tool_calls
            or turn_index == max_turns
        ):
            break

    log.append("session/end", {"stop_reason": stop_reason, "turns": turns})
    return RunOutcome(session_id=log.session_id, stop_reason=stop_reason, turns=turns)
