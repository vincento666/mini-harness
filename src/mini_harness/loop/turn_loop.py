"""显式回合主循环：记账 → 装配上下文 → 调模型 → 派发工具 → 判定停止。"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, get_args

from mini_harness.events.fold import assembled_payload, fold
from mini_harness.events.reader import LogReadFailure, read_events
from mini_harness.events.writer import EventLog, LogWriteFailure
from mini_harness.provider.contract import Provider, ProviderFailure
from mini_harness.tools.dispatch import dispatch_tool_call
from mini_harness.tools.registry import ToolRegistry

# `turn/end.stop_reason` 的词表：常量与 `Literal` 同源，加一个值只改这一处。
StopReason = Literal["MODEL_COMPLETED", "TOOL_CALLS", "MAX_TURNS", "PROVIDER_ERROR", "ABORTED"]

STOP_MODEL_COMPLETED = "MODEL_COMPLETED"
STOP_TOOL_CALLS = "TOOL_CALLS"
STOP_MAX_TURNS = "MAX_TURNS"
STOP_PROVIDER_ERROR = "PROVIDER_ERROR"
STOP_ABORTED = "ABORTED"
STOP_REASONS: frozenset[str] = frozenset(get_args(StopReason))


@dataclass(frozen=True)
class RunOutcome:
    """一次运行的结果：CLI 层据此映射退出码。"""

    session_id: str
    stop_reason: str
    turns: int
    failure_code: str | None = None
    detail: str = ""


def _append_all(
    log: EventLog, events: Sequence[tuple[str, dict[str, Any]]]
) -> LogWriteFailure | None:
    """按顺序追加一组事件；第一个写失败就是结果，后续事件不再写。"""
    for event_type, payload in events:
        outcome = log.append(event_type, payload)
        if isinstance(outcome, LogWriteFailure):
            return outcome
    return None


def _kernel_failure(
    log: EventLog, failure: LogWriteFailure | LogReadFailure, turns: int
) -> RunOutcome:
    """日志层失败作为结果结束。`stop_reason` 取失败码，它不是 `turn/end` 的词表值：
    日志层坏了就写不出 `turn/end`。"""
    return RunOutcome(
        session_id=log.session_id,
        stop_reason=failure.code,
        turns=turns,
        failure_code=failure.code,
        detail=failure.detail,
    )


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
    failure = _append_all(
        log,
        [
            (
                "session/start",
                {
                    "workspace": str(Path(workspace).resolve()),
                    "provider": provider_name,
                    "max_turns": max_turns,
                    "append_system_prompt": append_system_prompt,
                    "prompt": prompt,
                },
            ),
        ],
    )
    if failure is not None:
        return _kernel_failure(log, failure, 0)

    stop_reason = STOP_MODEL_COMPLETED
    turns = 0
    for turn_index in range(1, max_turns + 1):
        turns = turn_index
        turn_id = f"t{turn_index}"
        tool_names = [spec.name for spec in registry.specs()]

        failure = _append_all(log, [("turn/start", {"turn_id": turn_id})])
        if failure is not None:
            return _kernel_failure(log, failure, turns)

        events = read_events(log.path)
        if isinstance(events, LogReadFailure):
            return _kernel_failure(log, events, turns)
        context = fold(
            events,
            append_system_prompt=append_system_prompt,
            tool_descriptions=tool_names,
        )
        failure = _append_all(
            log,
            [
                ("context/assembled", assembled_payload(turn_id, context)),
                ("model/request", {"turn_id": turn_id, "tools": tool_names}),
            ],
        )
        if failure is not None:
            return _kernel_failure(log, failure, turns)

        generated = await provider.generate(context.messages, registry.specs(), cancel)
        if isinstance(generated, ProviderFailure):
            failure = _append_all(
                log,
                [
                    (
                        "error/model",
                        {"turn_id": turn_id, "code": generated.code, "detail": generated.detail},
                    ),
                    ("turn/end", {"turn_id": turn_id, "stop_reason": STOP_PROVIDER_ERROR}),
                    ("session/end", {"stop_reason": STOP_PROVIDER_ERROR, "turns": turns}),
                ],
            )
            if failure is not None:
                return _kernel_failure(log, failure, turns)
            return RunOutcome(
                session_id=log.session_id,
                stop_reason=STOP_PROVIDER_ERROR,
                turns=turns,
                failure_code=generated.code,
                detail=generated.detail,
            )

        failure = _append_all(
            log,
            [
                (
                    "model/response",
                    {
                        "turn_id": turn_id,
                        "content": generated.content,
                        "tool_calls": [
                            call.model_dump(mode="json") for call in generated.tool_calls
                        ],
                        "usage": generated.usage.model_dump(mode="json"),
                        "finish_reason": generated.finish_reason,
                    },
                ),
            ],
        )
        if failure is not None:
            return _kernel_failure(log, failure, turns)

        for call in generated.tool_calls:
            failure = _append_all(
                log,
                [
                    (
                        "tool/call",
                        {
                            "turn_id": turn_id,
                            "tool_call_id": call.id,
                            "name": call.name,
                            "arguments": call.arguments,
                        },
                    ),
                ],
            )
            if failure is not None:
                return _kernel_failure(log, failure, turns)

            result = await dispatch_tool_call(call, registry)

            failure = _append_all(
                log,
                [
                    (
                        "tool/result",
                        {
                            "turn_id": turn_id,
                            "tool_call_id": call.id,
                            "outcome": result.outcome,
                            "content": result.content,
                        },
                    ),
                ],
            )
            if failure is not None:
                return _kernel_failure(log, failure, turns)

        if cancel.is_set():
            stop_reason = STOP_ABORTED
        elif not generated.tool_calls:
            stop_reason = STOP_MODEL_COMPLETED
        elif turn_index == max_turns:
            stop_reason = STOP_MAX_TURNS
        else:
            stop_reason = STOP_TOOL_CALLS

        closing_events: list[tuple[str, dict[str, Any]]] = []
        if cancel.is_set():
            closing_events.append(
                (
                    "error/abort",
                    {"turn_id": turn_id, "code": STOP_ABORTED, "detail": "取消被置位"},
                )
            )
        closing_events.append(("turn/end", {"turn_id": turn_id, "stop_reason": stop_reason}))

        failure = _append_all(log, closing_events)
        if failure is not None:
            return _kernel_failure(log, failure, turns)

        if cancel.is_set() or not generated.tool_calls or turn_index == max_turns:
            break

    failure = _append_all(log, [("session/end", {"stop_reason": stop_reason, "turns": turns})])
    if failure is not None:
        return _kernel_failure(log, failure, turns)
    return RunOutcome(session_id=log.session_id, stop_reason=stop_reason, turns=turns)
