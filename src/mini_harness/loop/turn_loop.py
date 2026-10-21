"""显式回合主循环：记账 → 装配上下文 → 调模型 → 派发工具 → 判定停止。"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, get_args

from mini_harness.context.budget import (
    budget_reading,
    estimate_tokens,
    shadowed_range,
    trigger_line,
)
from mini_harness.events.fold import (
    PURPOSE_COMPACTION,
    AssembledContext,
    Message,
    assembled_payload,
    fold,
)
from mini_harness.events.reader import LogReadFailure, read_events
from mini_harness.events.record import EventRecord
from mini_harness.events.writer import EventLog, LogWriteFailure
from mini_harness.loop.settings import SessionSettings
from mini_harness.provider.contract import (
    AssistantTurn,
    Provider,
    ProviderFailure,
    ToolCall,
)
from mini_harness.tools.dispatch import ApprovalAsked, DispatchOutcome, dispatch_tool_call
from mini_harness.tools.fences import (
    STDIN_APPROVAL_GATE,
    ApprovalGate,
    DispatchContext,
    reads_from_records,
)
from mini_harness.tools.registry import ToolRegistry, ToolResult

# `turn/end.stop_reason` 的词表：常量与 `Literal` 同源，加一个值只改这一处。
StopReason = Literal[
    "MODEL_COMPLETED",
    "TOOL_CALLS",
    "MAX_TURNS",
    "PROVIDER_ERROR",
    "ABORTED",
    "FENCE_DENIED",
    "CONTEXT_WINDOW_EXCEEDED",
]

STOP_MODEL_COMPLETED = "MODEL_COMPLETED"
STOP_TOOL_CALLS = "TOOL_CALLS"
STOP_MAX_TURNS = "MAX_TURNS"
STOP_PROVIDER_ERROR = "PROVIDER_ERROR"
STOP_ABORTED = "ABORTED"
STOP_FENCE_DENIED = "FENCE_DENIED"
STOP_CONTEXT_WINDOW_EXCEEDED = "CONTEXT_WINDOW_EXCEEDED"
STOP_REASONS: frozenset[str] = frozenset(get_args(StopReason))

# 同一回合里同时在跑的只读调用上限；会改动文件的调用不吃这个额度，它们串行。
MAX_PARALLEL_TOOLS = 8

# 被超时或取消打断的结果词，各配一条 `tool/cancelled`。
CANCELLED_OUTCOMES: frozenset[str] = frozenset({"TOOL_TIMEOUT", "TOOL_CANCELLED"})


@dataclass(frozen=True)
class RunOutcome:
    """一次运行的结果：CLI 层据此映射退出码。"""

    session_id: str
    stop_reason: str
    turns: int
    failure_code: str | None = None
    detail: str = ""


@dataclass(frozen=True)
class SessionEnv:
    """一次会话的冻结环境：段调用不再一路结伴（ADR-0002 第 21 条）。

    `cancel` 故意不在这里——每个段一个取消事件（design D7），它是段的入参而不是会话的。
    """

    provider: Provider
    log: EventLog
    registry: ToolRegistry
    settings: SessionSettings
    approval_gate: ApprovalGate = STDIN_APPROVAL_GATE


@dataclass(frozen=True)
class SegmentOutcome:
    """一个段怎么停的。会话是否继续由入口决定（ADR-0011），内核只报这一段。"""

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


@dataclass(frozen=True)
class InternalFailure:
    """执行段逃出来的异常：不是工具的结果，是内核自己的故障。

    `code` 故意在 `StopReason` 词表外——写不出 `turn/end`，也就不写；它走 `error/internal`。
    """

    code: str
    detail: str
    tool_call_id: str | None = None


def _segment_failure(
    failure: LogWriteFailure | LogReadFailure | InternalFailure, turns: int
) -> SegmentOutcome:
    """内核失败作为段的结果。`stop_reason` 取失败码，它不是 `turn/end` 的词表值：
    内核坏了就写不出 `turn/end`，也就写不出 `segment/end`。"""
    return SegmentOutcome(
        stop_reason=failure.code,
        turns=turns,
        failure_code=failure.code,
        detail=failure.detail,
    )


def _run_outcome(log: EventLog, outcome: SegmentOutcome) -> RunOutcome:
    """段的结果加上 session id 就是一次运行的结果。"""
    return RunOutcome(
        session_id=log.session_id,
        stop_reason=outcome.stop_reason,
        turns=outcome.turns,
        failure_code=outcome.failure_code,
        detail=outcome.detail,
    )


@dataclass
class _BatchOutcome:
    """一个派发批次的结果：内核失败（日志层坏了，或执行段逃出了异常），或第一个围栏拒绝。"""

    failure: LogWriteFailure | LogReadFailure | InternalFailure | None = None
    denial_code: str | None = None
    denial_detail: str = ""


async def _race_with_cancel(
    call: ToolCall,
    registry: ToolRegistry,
    context: DispatchContext,
    approval_gate: ApprovalGate,
    cancel: asyncio.Event,
    on_approval_request: ApprovalAsked,
) -> DispatchOutcome:
    """取消置位时打断正在执行的调用：被打断的那一条塌成 `TOOL_CANCELLED`。

    `dispatch_tool_call` 自己会把 `CancelledError` 塌成结果词；拿不到那个结果时这里补一条，
    于是「有 `tool/call` 必有 `tool/result`」不依赖工具配合。**只有 `CancelledError` 有这个兜底**：
    从执行段逃出来的其它异常是内核故障，改名成取消就是往日志里写一件没发生过的事。
    """
    running = asyncio.create_task(
        dispatch_tool_call(call, registry, context, approval_gate, on_approval_request)
    )
    watcher = asyncio.create_task(cancel.wait())
    _, pending = await asyncio.wait({running, watcher}, return_when=asyncio.FIRST_COMPLETED)
    for task in pending:
        task.cancel()
    settled = await asyncio.gather(running, watcher, return_exceptions=True)
    if isinstance(settled[0], DispatchOutcome):
        return settled[0]
    if isinstance(settled[0], asyncio.CancelledError):
        return DispatchOutcome(
            ToolResult("TOOL_CANCELLED", f"取消打断了正在执行的调用：{call.name}")
        )
    raise settled[0]


async def _dispatch_batch(
    *,
    log: EventLog,
    turn_id: str,
    calls: Sequence[ToolCall],
    registry: ToolRegistry,
    settings: SessionSettings,
    approval_gate: ApprovalGate,
    cancel: asyncio.Event,
) -> _BatchOutcome:
    """派发一个回合声明的工具调用批次：只读的并发、会改动文件的串行。

    `tool/call` 由「前一个已经轮到过——开始派发或放弃」这条链保证按声明顺序落盘；结果在产生时落盘
    （`settle`），所以 `tool/result` 之间是完成顺序。围栏拒绝之后，还没开始的调用不再派发
    （连 `tool/call` 都不写），已经开始的照常跑完并落结果。取消置位之后不再派发：未派发的落一对
    记录（`tool/call` 加 `ABORTED_BEFORE_DISPATCH`），已经开始的被打断并落 `TOOL_CANCELLED`。
    前缀只在本批次开始时取样一次，整批共用。
    """
    prefix = read_events(log.path)
    if isinstance(prefix, LogReadFailure):
        return _BatchOutcome(failure=prefix)
    context = DispatchContext.from_settings(
        settings,
        reads=reads_from_records(prefix, settings.workspace),
    )

    # `started` 是「轮到过：开始派发或放弃」；`finished` 是「整个跑完」。
    started: list[asyncio.Event] = [asyncio.Event() for _ in calls]
    finished: list[asyncio.Event] = [asyncio.Event() for _ in calls]
    mutating: list[bool] = []
    for call in calls:
        definition = registry.lookup(call.name)
        mutating.append(definition is not None and definition.mutates)
    stop = asyncio.Event()
    read_slots = asyncio.Semaphore(MAX_PARALLEL_TOOLS)
    mutating_slot = asyncio.Lock()
    outcome = _BatchOutcome()

    def begin(index: int, call: ToolCall) -> bool:
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
                )
            ],
        )
        started[index].set()
        if failure is not None:
            outcome.failure = failure
            stop.set()
            return False
        return True

    def ask_logged(call: ToolCall) -> bool:
        """「要问人」在提问之前先落盘：`approval/request` 先到日志，再到人跟前（D12）。

        写不进去就不问人——这一批已经注定失败，把人挂在提问前没有意义。
        """
        failure = _append_all(
            log,
            [
                (
                    "approval/request",
                    {
                        "turn_id": turn_id,
                        "tool_call_id": call.id,
                        "name": call.name,
                        "arguments": call.arguments,
                    },
                )
            ],
        )
        if failure is not None:
            outcome.failure = failure
            stop.set()
            return False
        return True

    def escaped(call: ToolCall, error: BaseException) -> None:
        """执行段逃出来的异常不是结果：写 `error/internal`，让 run 以内部错误收尾。"""
        detail = f"{call.name}：{type(error).__name__}: {error}"
        written = _append_all(
            log,
            [
                (
                    "error/internal",
                    {"turn_id": turn_id, "tool_call_id": call.id, "detail": detail},
                )
            ],
        )
        outcome.failure = (
            written if written is not None else InternalFailure("INTERNAL_ERROR", detail, call.id)
        )
        stop.set()

    def settle(call: ToolCall, dispatched: DispatchOutcome) -> None:
        """结果在产生时落盘：一个调用跑完就把它的事件写进日志，不等同批其他调用（ADR-0012）。

        落盘顺序因此是完成顺序。单个调用自己的相对顺序不变：`approval/response` 在
        `tool/result` 之前，`tool/cancelled` 紧跟它，`error/fence` 在配对的 `tool/result` 之后。
        """
        written: list[tuple[str, dict[str, Any]]] = []
        if dispatched.approval is not None:
            # `approval/request` 已经在提问之前落盘了（`ask_logged`），这里只补结论。
            written.append(
                (
                    "approval/response",
                    {
                        "turn_id": turn_id,
                        "tool_call_id": call.id,
                        "decision": dispatched.approval,
                    },
                )
            )
        written.append(
            (
                "tool/result",
                {
                    "turn_id": turn_id,
                    "tool_call_id": call.id,
                    "outcome": dispatched.result.outcome,
                    "content": dispatched.result.content,
                },
            ),
        )
        if dispatched.result.outcome in CANCELLED_OUTCOMES:
            written.append(
                (
                    "tool/cancelled",
                    {"turn_id": turn_id, "tool_call_id": call.id},
                )
            )
        if dispatched.fence_code is not None:
            written.append(
                (
                    "error/fence",
                    {
                        "turn_id": turn_id,
                        "tool_call_id": call.id,
                        "code": dispatched.fence_code,
                        "path": dispatched.path,
                        "raw_path": dispatched.raw_path,
                        "detail": dispatched.result.content,
                    },
                )
            )

        failure = _append_all(log, written)
        if failure is not None:
            outcome.failure = failure
            stop.set()
            return
        if dispatched.fence_code is not None:
            stop.set()
            if outcome.denial_code is None:
                outcome.denial_code = dispatched.fence_code
                outcome.denial_detail = dispatched.result.content

    def not_dispatched(call: ToolCall) -> None:
        """没开始的调用的那个结果词：`ABORTED_BEFORE_DISPATCH`（ADR-0011）。

        不配 `tool/cancelled`：「被打断」预设它开始过（design D5）。
        """
        settle(
            call,
            DispatchOutcome(
                ToolResult(
                    "ABORTED_BEFORE_DISPATCH",
                    f"取消在派发之前置位，这个调用没有开始：{call.name}",
                )
            ),
        )

    def abandoned(index: int, call: ToolCall) -> None:
        """取消置位后没轮到派发的调用：落一对记录。

        它被声明过，就要在日志里有个交代——回合收尾后会话续跑时，assistant 的工具请求必须配平。
        """
        if not begin(index, call):
            return
        not_dispatched(call)

    async def one(index: int, call: ToolCall) -> None:
        try:
            await dispatch_one(index, call)
        except Exception as error:
            escaped(call, error)
        finally:
            # 放弃派发也要把这两条链传下去：否则排在它后面的调用会永远等一个不会开始的调用。
            started[index].set()
            finished[index].set()

    async def dispatch_one(index: int, call: ToolCall) -> None:
        if index > 0:
            await started[index - 1].wait()
            if mutating[index] or mutating[index - 1]:
                # 只有一对相邻的只读调用允许同时在跑；沾上「要改动」的都排队。
                # 于是「拒绝之后的调用不再派发」是这条规则保证的，不是碰巧的调度顺序。
                await finished[index - 1].wait()
        if mutating[index]:
            async with mutating_slot:
                # 拿到独占权之后才决定要不要开始：串行链上「已声明」不等于「已派发」。
                if cancel.is_set():
                    abandoned(index, call)
                    return
                if stop.is_set():
                    return
                if not begin(index, call):
                    return
                settle(
                    call,
                    await _race_with_cancel(
                        call, registry, context, approval_gate, cancel, ask_logged
                    ),
                )
            return
        if cancel.is_set():
            abandoned(index, call)
            return
        if stop.is_set():
            return
        if not begin(index, call):
            return
        async with read_slots:
            # 拿到额度之后才决定要不要开始：排队期间「已声明」不等于「已派发」（design D5）。
            if cancel.is_set():
                not_dispatched(call)
                return
            settle(
                call,
                await _race_with_cancel(call, registry, context, approval_gate, cancel, ask_logged),
            )

    await asyncio.gather(*(one(index, call) for index, call in enumerate(calls)))
    if outcome.failure is not None and not isinstance(outcome.failure, InternalFailure):
        # 日志层坏了：后面的事件都写不出去。
        return outcome

    # 结果已经在 `settle` 里逐个落盘了；这里只交代批次结局。
    return outcome


# 摘要那次调用的指令文本：它进摘要调用的上下文，不进任何回合的上下文。
SUMMARY_INSTRUCTION = (
    "把上面的对话压缩成一段摘要：任务是什么、已经做了什么、下一步是什么；保留文件路径与关键结论。"
)


def _retry_events(
    turn_id: str, turn: AssistantTurn | ProviderFailure
) -> list[tuple[str, dict[str, Any]]]:
    """重试事实随结果回到回合循环，由循环写进日志（不变量 A）。"""
    return [
        ("model/retry", {"turn_id": turn_id, "attempt": attempt.attempt, "status": attempt.status})
        for attempt in turn.attempts
    ]


async def _provider_error(
    log: EventLog,
    turn_id: str,
    failure: ProviderFailure,
    turns: int,
    retry_events: Sequence[tuple[str, dict[str, Any]]],
) -> SegmentOutcome:
    """provider 失败作为**回合**收尾：`error/model` + `turn/end`（design D7）。

    段的边界与 `session/end` 不在这里——它们归段与入口（ADR-0011）。
    """
    written = _append_all(
        log,
        [
            *retry_events,
            ("error/model", {"turn_id": turn_id, "code": failure.code, "detail": failure.detail}),
            ("turn/end", {"turn_id": turn_id, "stop_reason": STOP_PROVIDER_ERROR}),
        ],
    )
    if written is not None:
        return _segment_failure(written, turns)
    return SegmentOutcome(
        stop_reason=STOP_PROVIDER_ERROR,
        turns=turns,
        failure_code=failure.code,
        detail=failure.detail,
    )


async def _context_overflow(
    log: EventLog,
    turn_id: str,
    turns: int,
    detail: str,
    retry_events: Sequence[tuple[str, dict[str, Any]]] = (),
) -> SegmentOutcome:
    """上下文装不下时是**回合**终止结果不是异常（不变量 D）：不调回合模型，直接收尾。

    两条触发路径共用这里——估算兜底与 provider 报出的超限产出同一个停止理由。会话是否结束归入口。
    """
    written = _append_all(
        log,
        [
            *retry_events,
            (
                "error/context",
                {"turn_id": turn_id, "code": STOP_CONTEXT_WINDOW_EXCEEDED, "detail": detail},
            ),
            ("turn/end", {"turn_id": turn_id, "stop_reason": STOP_CONTEXT_WINDOW_EXCEEDED}),
        ],
    )
    if written is not None:
        return _segment_failure(written, turns)
    return SegmentOutcome(
        stop_reason=STOP_CONTEXT_WINDOW_EXCEEDED,
        turns=turns,
        failure_code=STOP_CONTEXT_WINDOW_EXCEEDED,
        detail=detail,
    )


async def _compact_if_over_line(
    *,
    log: EventLog,
    turn_id: str,
    settings: SessionSettings,
    provider: Provider,
    cancel: asyncio.Event,
    events: Sequence[EventRecord],
    context: AssembledContext,
) -> ProviderFailure | LogWriteFailure | LogReadFailure | None:
    """越线时压缩一次：调模型生成摘要、写一条 `compaction/summary`（design D1 与 D2）。

    没有可遮蔽的内容时什么都不写、返回 `None`：调用方重新读数，那条路通向溢出。
    """
    rng = shadowed_range(events, settings.window)
    if rng is None:
        return None
    tokens_before = budget_reading(events, context.messages)
    written = _append_all(
        log,
        [("model/request", {"turn_id": turn_id, "tools": [], "purpose": PURPOSE_COMPACTION})],
    )
    if written is not None:
        return written

    generated = await provider.generate(
        [*context.messages, Message(role="user", content=SUMMARY_INSTRUCTION)],
        [],
        cancel,
    )
    if isinstance(generated, ProviderFailure):
        return generated

    # `tokens_after` 量的是遮蔽之后那份表层：把被遮蔽的记录滤掉，再补上摘要本身。
    surviving = [event for event in events if event.seq < rng["start"] or event.seq > rng["end"]]
    tokens_after = budget_reading(surviving, fold(surviving).messages) + estimate_tokens(
        [Message(role="system", content=generated.content)]
    )
    written = _append_all(
        log,
        [
            *_retry_events(turn_id, generated),
            (
                "model/response",
                {
                    "turn_id": turn_id,
                    "content": generated.content,
                    "tool_calls": [],
                    "usage": generated.usage.model_dump(mode="json"),
                    "finish_reason": generated.finish_reason,
                    "purpose": PURPOSE_COMPACTION,
                },
            ),
            (
                "compaction/summary",
                {
                    "turn_id": turn_id,
                    "shadowed_range": rng,
                    "summary": generated.content,
                    "tokens_before": tokens_before,
                    "tokens_after": tokens_after,
                },
            ),
        ],
    )
    if written is not None:
        return written
    return None


def start_session(*, prompt: str, env: SessionEnv) -> SegmentOutcome | None:
    """写 `session/start`。成功返回 None，日志层坏了就返回失败结果。"""
    settings = env.settings
    start_payload: dict[str, Any] = {
        "workspace": str(Path(settings.workspace).resolve()),
        "provider": settings.provider_name,
        "max_turns": settings.max_turns,
        "append_system_prompt": settings.append_system_prompt,
        "prompt": prompt,
        "sandbox": settings.sandbox,
        "approval": settings.approval,
        "window": settings.window,
        "reserve": settings.reserve,
        "tools": [spec.name for spec in env.registry.specs()],
    }
    if settings.endpoint is not None:
        # 记的是密钥环境变量的名字，不是它的值（cli spec：密钥 MUST NOT 进 payload）。
        start_payload["base_url"] = settings.endpoint.base_url
        start_payload["model"] = settings.endpoint.model
        start_payload["api_key_env"] = settings.endpoint.api_key_env

    failure = _append_all(
        env.log,
        [
            ("session/start", start_payload),
        ],
    )
    if failure is not None:
        return _segment_failure(failure, 0)
    return None


async def run_turn_segment(
    *, env: SessionEnv, segment_id: str, first_turn_index: int, cancel: asyncio.Event
) -> SegmentOutcome:
    """跑一个回合段：一条输入展开的那串往返。段内上限是 `max_turns`，会话级没有上限。

    段的边界在这里落盘——`segment/start` 在第一个 `turn/start` 之前、`segment/end` 在最后一个
    `turn/end` 之后（design D3）。这里不写 `session/end`：会话是否结束由入口决定（ADR-0011）。
    """
    failure = _append_all(env.log, [("segment/start", {"segment_id": segment_id})])
    if failure is not None:
        return _segment_failure(failure, 0)

    outcome = await _run_turns(env=env, first_turn_index=first_turn_index, cancel=cancel)
    if outcome.stop_reason not in STOP_REASONS:
        # 内核坏了：写不出 `turn/end`，也就不写 `segment/end`。
        return outcome
    written = _append_all(
        env.log,
        [
            (
                "segment/end",
                {
                    "segment_id": segment_id,
                    "stop_reason": outcome.stop_reason,
                    "turns": outcome.turns,
                },
            ),
        ],
    )
    if written is not None:
        return _segment_failure(written, outcome.turns)
    return outcome


async def _run_turns(
    *, env: SessionEnv, first_turn_index: int, cancel: asyncio.Event
) -> SegmentOutcome:
    """段内的显式回合循环：记账 → 装配上下文 → 调模型 → 派发工具 → 判定停止。"""
    log = env.log
    provider = env.provider
    registry = env.registry
    settings = env.settings
    approval_gate = env.approval_gate
    stop_reason = STOP_MODEL_COMPLETED
    denial_code: str | None = None
    denial_detail = ""
    turns = 0
    for offset in range(settings.max_turns):
        turn_index = first_turn_index + offset
        turns = offset + 1
        turn_id = f"t{turn_index}"
        tool_names = [spec.name for spec in registry.specs()]

        failure = _append_all(log, [("turn/start", {"turn_id": turn_id})])
        if failure is not None:
            return _segment_failure(failure, turns)

        events = read_events(log.path)
        if isinstance(events, LogReadFailure):
            return _segment_failure(events, turns)
        context = fold(events)
        # 装配之内的一次压缩（design D5）：越线才压缩，一次装配最多一次，取消在场时不压缩。
        line = trigger_line(settings.window, settings.reserve)
        if budget_reading(events, context.messages) > line and not cancel.is_set():
            compacted = await _compact_if_over_line(
                log=log,
                turn_id=turn_id,
                settings=settings,
                provider=provider,
                cancel=cancel,
                events=events,
                context=context,
            )
            if isinstance(compacted, (LogWriteFailure, LogReadFailure)):
                return _segment_failure(compacted, turns)
            if isinstance(compacted, ProviderFailure):
                return await _provider_error(log, turn_id, compacted, turns, [])
            events = read_events(log.path)
            if isinstance(events, LogReadFailure):
                return _segment_failure(events, turns)
            context = fold(events)
            reading = budget_reading(events, context.messages)
            if reading > line:
                # 措辞跟着日志里的事实走：这一回合真写过摘要才说「压缩之后」。
                compacted_here = any(
                    event.type == "compaction/summary" and event.payload.get("turn_id") == turn_id
                    for event in events
                )
                detail = (
                    f"压缩之后预算读数 {reading} 仍超过触发线 {line}"
                    if compacted_here
                    else f"无可遮蔽的内容，预算读数 {reading} 已超过触发线 {line}"
                )
                return await _context_overflow(log, turn_id, turns, detail)

        failure = _append_all(
            log,
            [
                ("context/assembled", assembled_payload(turn_id, context)),
                ("model/request", {"turn_id": turn_id, "tools": tool_names}),
            ],
        )
        if failure is not None:
            return _segment_failure(failure, turns)

        generated = await provider.generate(context.messages, registry.specs(), cancel)
        # 重试事实由 provider 带回、由循环写进日志：provider 不碰日志（不变量 A）。
        retry_events = _retry_events(turn_id, generated)
        if isinstance(generated, ProviderFailure):
            if generated.code == "PROVIDER_CONTEXT_OVERFLOW":
                # provider 报出的超限与估算兜底是同一个结果（不变量 D）：不写 `error/model`。
                return await _context_overflow(
                    log,
                    turn_id,
                    turns,
                    f"provider 报出上下文超限：{generated.detail}",
                    retry_events,
                )
            return await _provider_error(log, turn_id, generated, turns, retry_events)

        failure = _append_all(
            log,
            [
                *retry_events,
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
            return _segment_failure(failure, turns)

        fence_denied = False
        batch = await _dispatch_batch(
            log=log,
            turn_id=turn_id,
            calls=generated.tool_calls,
            registry=registry,
            settings=settings,
            approval_gate=approval_gate,
            cancel=cancel,
        )
        if batch.failure is not None:
            return _segment_failure(batch.failure, turns)
        if batch.denial_code is not None:
            fence_denied = True
            denial_code = batch.denial_code
            denial_detail = batch.denial_detail

        if cancel.is_set():
            stop_reason = STOP_ABORTED
        elif fence_denied:
            stop_reason = STOP_FENCE_DENIED
        elif not generated.tool_calls:
            stop_reason = STOP_MODEL_COMPLETED
        elif turns == settings.max_turns:
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
            return _segment_failure(failure, turns)

        if (
            cancel.is_set()
            or fence_denied
            or not generated.tool_calls
            or turns == settings.max_turns
        ):
            break

    return SegmentOutcome(
        stop_reason=stop_reason,
        turns=turns,
        failure_code=denial_code,
        detail=denial_detail,
    )


def end_session(*, env: SessionEnv, stop_reason: str, turns: int) -> SegmentOutcome | None:
    """写 `session/end`。成功返回 None，日志层坏了就返回失败结果。"""
    failure = _append_all(env.log, [("session/end", {"stop_reason": stop_reason, "turns": turns})])
    if failure is not None:
        return _segment_failure(failure, turns)
    return None


async def run_session(
    *,
    prompt: str,
    provider: Provider,
    log: EventLog,
    registry: ToolRegistry,
    settings: SessionSettings,
    cancel: asyncio.Event,
    approval_gate: ApprovalGate = STDIN_APPROVAL_GATE,
) -> RunOutcome:
    """一次性 run：开始会话、恰一个段、结束会话。

    段编号与回合编号都从 1 起；REPL 自己数段、给下一个段起始编号（design D3）。
    """
    env = SessionEnv(
        provider=provider,
        log=log,
        registry=registry,
        settings=settings,
        approval_gate=approval_gate,
    )
    started = start_session(prompt=prompt, env=env)
    if started is not None:
        return _run_outcome(log, started)
    segment = await run_turn_segment(env=env, segment_id="s1", first_turn_index=1, cancel=cancel)
    if segment.stop_reason not in STOP_REASONS:
        return _run_outcome(log, segment)
    ended = end_session(env=env, stop_reason=segment.stop_reason, turns=segment.turns)
    if ended is not None:
        return _run_outcome(log, ended)
    return _run_outcome(log, segment)
