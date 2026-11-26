"""显式轮主循环：记账 → 装配上下文 → 调模型 → 派发工具 → 判定停止。"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, get_args

from mini_harness.context.budget import (
    budget_reading,
    estimate_tokens,
    pressure_budget,
    shadowed_range,
    trigger_line,
)
from mini_harness.contracts import contract_home, load_contracts, render_removed
from mini_harness.events.fold import (
    GOAL_POLICY_VERSION,
    PURPOSE_COMPACTION,
    AssembledContext,
    Message,
    assembled_payload,
    fold,
    fold_plan_mode,
    fold_range,
)
from mini_harness.events.projection import project
from mini_harness.events.reader import LogReadFailure, read_events
from mini_harness.events.record import EventRecord
from mini_harness.events.writer import EventLog, LogWriteFailure
from mini_harness.goals import (
    GoalRound,
    GoalRuntime,
    GoalSnapshot,
    abort_goal,
    advance_round,
    entry_of,
    exhaust_goal,
    fold_goal,
    opened_by_human,
    render_goal_round,
)
from mini_harness.loop.goal_driver import NO_CONTINUE_REASONS, RoundDecision, next_round
from mini_harness.loop.settings import SessionSettings
from mini_harness.provider.contract import (
    AssistantTurn,
    Block,
    DeltaSink,
    Provider,
    ProviderFailure,
    ReasoningBlock,
    ReasoningSink,
    StepDeltaSink,
    TextBlock,
    ToolCall,
)
from mini_harness.session.delegation import DelegationState
from mini_harness.skill_providers import SkillRegistry
from mini_harness.skills import SkillDiscovery, catalog_digest, render_catalog_message
from mini_harness.tools.dispatch import ApprovalAsked, DispatchOutcome, dispatch_tool_call
from mini_harness.tools.fences import (
    STDIN_APPROVAL_GATE,
    UNAVAILABLE_QUESTION_GATE,
    ApprovalGate,
    DispatchContext,
    QuestionGate,
    reads_from_records,
)
from mini_harness.tools.registry import ToolRegistry, ToolResult

# `turn/end.stop_reason` 的词表：常量与 `Literal` 同源，加一个值只改这一处。
StopReason = Literal[
    "MODEL_COMPLETED",
    "TOOL_CALLS",
    "MAX_STEPS",
    "PROVIDER_ERROR",
    "ABORTED",
    "FENCE_DENIED",
    "CONTEXT_WINDOW_EXCEEDED",
]

STOP_MODEL_COMPLETED = "MODEL_COMPLETED"
STOP_TOOL_CALLS = "TOOL_CALLS"
STOP_MAX_STEPS = "MAX_STEPS"
STOP_PROVIDER_ERROR = "PROVIDER_ERROR"
STOP_ABORTED = "ABORTED"
STOP_FENCE_DENIED = "FENCE_DENIED"
STOP_CONTEXT_WINDOW_EXCEEDED = "CONTEXT_WINDOW_EXCEEDED"
STOP_REASONS: frozenset[str] = frozenset(get_args(StopReason))

# 哪个入口开的这个会话：`session/start.payload.entry` 只有这四个值（design D1；H1 加 `host`）。
SessionEntry = Literal["run", "chat", "serve", "host", "subagent"]
ENTRY_RUN: SessionEntry = "run"
ENTRY_CHAT: SessionEntry = "chat"
ENTRY_SERVE: SessionEntry = "serve"
ENTRY_HOST: SessionEntry = "host"
ENTRY_SUBAGENT: SessionEntry = "subagent"

# provider 失败码里只有这一种触发请求级压缩与一次重试（ADR-0019）。
PROVIDER_CONTEXT_OVERFLOW = "PROVIDER_CONTEXT_OVERFLOW"

# 同一步里同时在跑的只读调用上限；会改动文件的调用不吃这个额度，它们串行。
MAX_PARALLEL_TOOLS = 8

# 被超时或取消打断的结果词，各配一条 `tool/cancelled`。
CANCELLED_OUTCOMES: frozenset[str] = frozenset({"TOOL_TIMEOUT", "TOOL_CANCELLED"})


@dataclass(frozen=True)
class RunOutcome:
    """一次运行的结果：CLI 层据此映射退出码。"""

    session_id: str
    stop_reason: str
    steps: int
    failure_code: str | None = None
    detail: str = ""


@dataclass
class SkillCatalogState:
    """模型目录的状态：上次发出的指纹与消息 seq（M14+）。"""

    last_digest: str | None = None
    last_seq: int | None = None


@dataclass
class ContractState:
    """工作区契约的状态：上次发出的指纹、消息 seq 与路径（M14a）。"""

    last_digest: str | None = None
    last_seq: int | None = None
    last_paths: tuple[str, ...] = ()


@dataclass
class QuestionRuntime:
    """本轮最后一个没有答案的问题（进程内，不落盘）。轮首清零，轮尾还在就不自动续跑。"""

    pending: str | None = None


# 步末钩子：`(step_id, content)`。入口用它补打在流式里没有增量的那一步（chat 的渲染器）；
# host 与 `--no-stream` 不装——前者由 SSE 的 durable 帧承载，后者由轮末投影打印。
StepEndSink = Callable[[str, str], None]


@dataclass(frozen=True)
class SessionEnv:
    """一次会话的冻结环境：轮调用不再一路结伴（ADR-0002 第 21 条）。

    `cancel` 故意不在这里——每一轮一个取消事件（design D7），它是轮的入参而不是会话的。
    """

    provider: Provider
    log: EventLog
    registry: ToolRegistry
    settings: SessionSettings
    approval_gate: ApprovalGate = STDIN_APPROVAL_GATE
    question_gate: QuestionGate = UNAVAILABLE_QUESTION_GATE
    on_delta: StepDeltaSink | None = None
    # 思考增量（merge-reasoning-stream）：与正文增量分开走同一 sink 契约，思考不进 stdout。
    on_reasoning: ReasoningSink | None = None
    # 步末回退（restore-chat-streaming）：`step/end` 落盘之后、下一步开始之前调用。
    on_step_end: StepEndSink | None = None
    # 委派账本：活跃子代理数与宿主登记回调（M12）；每个会话一份。
    delegation: DelegationState = field(default_factory=DelegationState)
    # 技能注册表（skill-providers）：目录与命令面都读它的快照；None 时回落到 settings。
    skills_registry: SkillRegistry | None = None
    skill_catalog: SkillCatalogState = field(default_factory=SkillCatalogState)
    # 工作区契约：每 turn 观察两份 AGENTS.md，指纹变了才重发；首页目录取自环境。
    contracts_home: Path = field(default_factory=lambda: contract_home(os.environ))
    contracts: ContractState = field(default_factory=ContractState)
    # 目标武装位（M13）：进程内，不落盘（design D5）。
    goal_runtime: GoalRuntime = field(default_factory=GoalRuntime)
    # 本轮里最后一个没有答案的问题（`ask_user` 的 `QUESTION_UNAVAILABLE`）。
    # 轮首清零；轮尾还在就是「等人回答」，驱动据此不再自动续跑（design D11）。
    questions: QuestionRuntime = field(default_factory=QuestionRuntime)


@dataclass(frozen=True)
class TurnOutcome:
    """一轮怎么停的。会话是否继续由入口决定（ADR-0011），内核只报这一轮。

    `tool_calls` 是本轮真正派发过的工具调用数（含失败；取消/未派发不算）。驱动的停滞
    判定只看它：零调用的 goal 轮次是空转，不再开下一轮（D14）。
    """

    stop_reason: str
    steps: int
    failure_code: str | None = None
    detail: str = ""
    tool_calls: int = 0


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
    """执行区间逃出来的异常：不是工具的结果，是内核自己的故障。

    `code` 故意在 `StopReason` 词表外——写不出 `step/end`，也就不写；它走 `error/internal`。
    """

    code: str
    detail: str
    tool_call_id: str | None = None


def _turn_failure(
    failure: LogWriteFailure | LogReadFailure | InternalFailure, steps: int
) -> TurnOutcome:
    """内核失败作为轮的结果。`stop_reason` 取失败码，它不是 `step/end` 的词表值：
    内核坏了就写不出 `step/end`，也就写不出 `turn/end`。"""
    return TurnOutcome(
        stop_reason=failure.code,
        steps=steps,
        failure_code=failure.code,
        detail=failure.detail,
    )


def _run_outcome(log: EventLog, outcome: TurnOutcome) -> RunOutcome:
    """轮的结果加上 session id 就是一次运行的结果。"""
    return RunOutcome(
        session_id=log.session_id,
        stop_reason=outcome.stop_reason,
        steps=outcome.steps,
        failure_code=outcome.failure_code,
        detail=outcome.detail,
    )


@dataclass
class _BatchOutcome:
    """一个派发批次的结果：内核失败（日志层坏了，或执行区间逃出了异常），或第一个围栏拒绝。"""

    failure: LogWriteFailure | LogReadFailure | InternalFailure | None = None
    denial_code: str | None = None
    denial_detail: str = ""
    # 真正派发出去、产出了结果的调用数。取消与「未派发」不算动作（D14）。
    tool_calls: int = 0


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
    从执行区间逃出来的其它异常是内核故障，改名成取消就是往日志里写一件没发生过的事。
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


def _present_payload(call: ToolCall, result: ToolResult) -> dict[str, Any] | None:
    """`present` 成功时落一条产物事件；路径与标题来自工具 meta。"""
    if call.name != "present" or result.outcome != "OK" or result.meta is None:
        return None
    path = result.meta.get("present_path")
    title = result.meta.get("present_title")
    if not isinstance(path, str) or not isinstance(title, str):
        return None
    return {"path": path, "title": title}


def _todo_event_payload(call: ToolCall, outcome: str) -> dict[str, Any] | None:
    """`todo` 成功的调用落一条整表事件；其它工具或失败调用返回 None。"""
    if call.name != "todo" or outcome != "OK":
        return None
    items = call.arguments.get("items")
    if not isinstance(items, list):
        return None
    normalized: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            return None
        normalized.append(
            {
                "id": item.get("id"),
                "text": item.get("text"),
                "status": item.get("status", "pending"),
            }
        )
    return {"items": normalized}


def _approval_request_payload(step_id: str, call: ToolCall) -> dict[str, Any]:
    """`approval/request` 的形状；计划复核额外带 `purpose` 与计划正文（M14c）。"""
    payload: dict[str, Any] = {
        "step_id": step_id,
        "tool_call_id": call.id,
        "name": call.name,
        "arguments": call.arguments,
    }
    if call.name == "exit_plan_mode":
        payload["purpose"] = "plan-review"
        payload["plan"] = call.arguments.get("plan", "")
    return payload


async def _dispatch_batch(
    *,
    log: EventLog,
    step_id: str,
    calls: Sequence[ToolCall],
    registry: ToolRegistry,
    settings: SessionSettings,
    approval_gate: ApprovalGate,
    cancel: asyncio.Event,
    session: SessionEnv | None = None,
) -> _BatchOutcome:
    """派发一步声明的工具调用批次：只读的并发、会改动文件的串行。

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
        session=session,
        plan_active=fold_plan_mode(prefix),
        question_gate=None if session is None else session.question_gate,
        goal=fold_goal(prefix),
        todos=project(prefix, "todos")["value"],
        human_driven=opened_by_human(prefix),
        entry=entry_of(prefix),
    )

    # `started` 是「轮到过：开始派发或放弃」；`finished` 是「整个跑完」。
    started: list[asyncio.Event] = [asyncio.Event() for _ in calls]
    finished: list[asyncio.Event] = [asyncio.Event() for _ in calls]
    exclusive: list[bool] = []
    for call in calls:
        definition = registry.lookup(call.name)
        exclusive.append(definition is not None and definition.concurrency == "exclusive")
    stop = asyncio.Event()
    read_slots = asyncio.Semaphore(MAX_PARALLEL_TOOLS)
    exclusive_slot = asyncio.Lock()
    outcome = _BatchOutcome()

    def begin(index: int, call: ToolCall) -> bool:
        failure = _append_all(
            log,
            [
                (
                    "tool/call",
                    _approval_request_payload(step_id, call),
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
                    _approval_request_payload(step_id, call),
                )
            ],
        )
        if failure is not None:
            outcome.failure = failure
            stop.set()
            return False
        return True

    def escaped(call: ToolCall, error: BaseException) -> None:
        """执行区间逃出来的异常不是结果：写 `error/internal`，让 run 以内部错误收尾。"""
        detail = f"{call.name}：{type(error).__name__}: {error}"
        written = _append_all(
            log,
            [
                (
                    "error/internal",
                    {"step_id": step_id, "tool_call_id": call.id, "detail": detail},
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
                        "step_id": step_id,
                        "tool_call_id": call.id,
                        "decision": dispatched.approval,
                    },
                )
            )
        result_payload: dict[str, Any] = {
            "step_id": step_id,
            "tool_call_id": call.id,
            "outcome": dispatched.result.outcome,
            "content": dispatched.result.content,
        }
        if dispatched.result.meta is not None:
            result_payload.update(dispatched.result.meta)
        # 停滞判定只看「有没有真的派发过一个调用」：取消、未派发、围栏拒绝都不算动作。
        if (
            dispatched.result.outcome not in CANCELLED_OUTCOMES
            and dispatched.result.outcome != "ABORTED_BEFORE_DISPATCH"
        ):
            outcome.tool_calls += 1
        written.append(("tool/result", result_payload))
        if dispatched.plan_exit:
            written.append(("plan/mode", {"active": False}))
        todo_payload = _todo_event_payload(call, dispatched.result.outcome)
        if todo_payload is not None:
            written.append(("todo/updated", todo_payload))
        present_payload = _present_payload(call, dispatched.result)
        if present_payload is not None:
            written.append(("present/artifact", present_payload))
        if dispatched.result.outcome in CANCELLED_OUTCOMES:
            written.append(
                (
                    "tool/cancelled",
                    {"step_id": step_id, "tool_call_id": call.id},
                )
            )
        if dispatched.fence_code is not None:
            written.append(
                (
                    "error/fence",
                    {
                        "step_id": step_id,
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

        它被声明过，就要在日志里有个交代——步收尾后会话续跑时，assistant 的工具请求必须配平。
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
            if exclusive[index] or exclusive[index - 1]:
                # 只有一对相邻的只读调用允许同时在跑；沾上「要改动」的都排队。
                # 于是「拒绝之后的调用不再派发」是这条规则保证的，不是碰巧的调度顺序。
                await finished[index - 1].wait()
        if exclusive[index]:
            async with exclusive_slot:
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


# 摘要那次调用的指令文本：它进摘要调用的上下文，不进任何步的上下文。
SUMMARY_INSTRUCTION = (
    "把上面的对话压缩成一段摘要：任务是什么、已经做了什么、下一步是什么；保留文件路径与关键结论。"
)


def _retry_events(
    step_id: str, turn: AssistantTurn | ProviderFailure
) -> list[tuple[str, dict[str, Any]]]:
    """重试事实随结果回到步循环，由循环写进日志（不变量 A）。"""
    return [
        ("model/retry", {"step_id": step_id, "attempt": attempt.attempt, "status": attempt.status})
        for attempt in turn.attempts
    ]


@dataclass
class DeltaState:
    """本步是否流过非空正文 delta。

    取消分叉要用它：流过就说明屏幕上已有半句，不能再把半条回复写成 durable 真相；
    没流过就说明模型已完整返回、只是没流式，取消不该吞掉整段（restore-chat-streaming）。
    """

    streamed_any: bool = False


def _notify_step_end(env: SessionEnv, step_id: str, content: str, steps: int) -> TurnOutcome | None:
    """调步末钩子。渲染器的故障不该打断一轮：记一条 `error/internal`，`step/end` 已经在盘上。"""
    if env.on_step_end is None:
        return None
    try:
        env.on_step_end(step_id, content)
    except Exception as error:
        written = env.log.append(
            "error/internal",
            {"step_id": step_id, "code": "RENDER_FAILED", "detail": str(error)},
        )
        if isinstance(written, LogWriteFailure):
            return _turn_failure(written, steps)
    return None


def _forward_reasoning(sink: ReasoningSink | None, step_id: str) -> ReasoningSink | None:
    """把宿主 sink 包成 provider 只认 `(index, text)` 的回调，绑定当前步。"""
    if sink is None:
        return None

    async def forward(_step_id: str, index: int, text: str) -> None:
        await sink(step_id, index, text)

    return forward


@dataclass
class _StepCapture:
    """收当前步已交付的 reasoning/text 前缀；取消/失败时它就是 interrupted/attempt 的内容。"""

    reasoning: list[str]
    text: list[str]

    def __init__(self) -> None:
        self.reasoning = []
        self.text = []

    def blocks(self) -> list[Block]:
        blocks: list[Block] = []
        if self.reasoning:
            blocks.append(ReasoningBlock(text="".join(self.reasoning)))
        if self.text:
            blocks.append(TextBlock(text="".join(self.text)))
        return blocks


def _capture_sinks(
    capture: _StepCapture,
    on_delta: StepDeltaSink | None,
    on_reasoning: ReasoningSink | None,
    step_id: str,
    delta_state: DeltaState | None = None,
) -> tuple[DeltaSink | None, ReasoningSink | None]:
    """把 provider sink 包成「先收前缀、再转发宿主」；没有宿主 sink 也收。"""

    async def text(text_value: str) -> None:
        capture.text.append(text_value)
        if delta_state is not None and text_value:
            delta_state.streamed_any = True
        if on_delta is not None:
            await on_delta(step_id, text_value)

    async def reasoning(_step_id: str, index: int, text_value: str) -> None:
        capture.reasoning.append(text_value)
        if on_reasoning is not None:
            await on_reasoning(step_id, index, text_value)

    return text, reasoning


def _abort_turn(
    log: EventLog,
    step_id: str,
    steps: int,
    blocks: Sequence[Block] = (),
    *,
    evidence: bool = False,
) -> TurnOutcome:
    """流式取消的收尾：有已交付前缀写 interrupted message，否则只写 attempt + abort。"""
    events: list[tuple[str, dict[str, Any]]] = []
    if blocks:
        events.append(
            (
                "model/response",
                {
                    "step_id": step_id,
                    "content": "\n".join(
                        block.text for block in blocks if isinstance(block, TextBlock)
                    ),
                    "blocks": [block.model_dump(mode="json") for block in blocks],
                    "tool_calls": [],
                    "finish_reason": "interrupted",
                    "interrupted": True,
                },
            )
        )
    else:
        if evidence:
            events.append(
                (
                    "model/attempt",
                    {
                        "step_id": step_id,
                        "status": "aborted",
                        "error_code": STOP_ABORTED,
                        "partial_blocks": [],
                    },
                )
            )
    events.extend(
        [
            ("error/abort", {"step_id": step_id, "code": STOP_ABORTED, "detail": "取消被置位"}),
            ("step/end", {"step_id": step_id, "stop_reason": STOP_ABORTED}),
        ]
    )
    failure = _append_all(log, events)
    if failure is not None:
        return _turn_failure(failure, steps)
    return TurnOutcome(stop_reason=STOP_ABORTED, steps=steps)


async def _provider_error(
    log: EventLog,
    step_id: str,
    failure: ProviderFailure,
    steps: int,
    retry_events: Sequence[tuple[str, dict[str, Any]]],
    partial_blocks: Sequence[Block] = (),
) -> TurnOutcome:
    """provider 失败作为**步**收尾：有前缀先写 attempt，再 `error/model` + `step/end`（design D7）。

    轮的边界与 `session/end` 不在这里——它们归轮与入口（ADR-0011）。
    """
    attempt = (
        [
            (
                "model/attempt",
                {
                    "step_id": step_id,
                    "status": "error",
                    "error_code": failure.code,
                    "partial_blocks": [block.model_dump(mode="json") for block in partial_blocks],
                },
            )
        ]
        if partial_blocks
        else []
    )
    written = _append_all(
        log,
        [
            *retry_events,
            *attempt,
            ("error/model", {"step_id": step_id, "code": failure.code, "detail": failure.detail}),
            ("step/end", {"step_id": step_id, "stop_reason": STOP_PROVIDER_ERROR}),
        ],
    )
    if written is not None:
        return _turn_failure(written, steps)
    return TurnOutcome(
        stop_reason=STOP_PROVIDER_ERROR,
        steps=steps,
        failure_code=failure.code,
        detail=failure.detail,
    )


async def _context_overflow(
    log: EventLog,
    step_id: str,
    steps: int,
    detail: str,
    retry_events: Sequence[tuple[str, dict[str, Any]]] = (),
) -> TurnOutcome:
    """上下文装不下时是**步**终止结果不是异常（不变量 D）：不调模型，直接收尾。

    两条触发路径共用这里——估算兜底与 provider 报出的超限产出同一个停止理由。会话是否结束归入口。
    """
    written = _append_all(
        log,
        [
            *retry_events,
            (
                "error/context",
                {"step_id": step_id, "code": STOP_CONTEXT_WINDOW_EXCEEDED, "detail": detail},
            ),
            ("step/end", {"step_id": step_id, "stop_reason": STOP_CONTEXT_WINDOW_EXCEEDED}),
        ],
    )
    if written is not None:
        return _turn_failure(written, steps)
    return TurnOutcome(
        stop_reason=STOP_CONTEXT_WINDOW_EXCEEDED,
        steps=steps,
        failure_code=STOP_CONTEXT_WINDOW_EXCEEDED,
        detail=detail,
    )


def _trigger_line(settings: SessionSettings) -> int:
    """从冻结设置算触发线：四个压缩参数只在装配时取一次。"""
    return trigger_line(
        settings.window,
        settings.reserve,
        threshold_ratio=settings.compaction_threshold_ratio,
        headroom_tokens=settings.compaction_headroom_tokens,
    )


def _shadowed_range(
    events: Sequence[EventRecord], settings: SessionSettings
) -> dict[str, int] | None:
    """从冻结设置算遮蔽范围；`retain_tokens > 0` 时覆盖 ratio。"""
    return shadowed_range(
        events,
        settings.window,
        retain_ratio=settings.compaction_retain_ratio,
        retain_tokens=settings.compaction_retain_tokens,
    )


def _budget_triple(
    settings: SessionSettings, events: Sequence[EventRecord], messages: Sequence[Message]
) -> str:
    """溢出的 `detail` 里那三个数并排：预算读数、压力预算、触发线（ADR-0026）。

    死区只有靠这三个数并排才看得出来——只给触发线，读日志的人判断不了「离窗口还有多远」。
    两条触发路径共用 `_context_overflow`，也就共用这一串。
    """
    reading = budget_reading(events, messages)
    pressure = pressure_budget(settings.window, settings.reserve)
    line = _trigger_line(settings)
    return f"预算读数 {reading}、压力预算 {pressure}、触发线 {line}"


@dataclass(frozen=True)
class _RetriedRequest:
    """请求级压缩之后重试拿回的那一次调用：结果连同它带回的重试事实。"""

    generated: AssistantTurn
    retry_events: list[tuple[str, dict[str, Any]]]


async def _recover_overflowed_request(
    *,
    log: EventLog,
    step_id: str,
    steps: int,
    settings: SessionSettings,
    provider: Provider,
    registry: ToolRegistry,
    cancel: asyncio.Event,
    events: Sequence[EventRecord],
    context: AssembledContext,
    failure: ProviderFailure,
    retry_events: Sequence[tuple[str, dict[str, Any]]],
    on_delta: DeltaSink | None = None,
    delta_state: DeltaState | None = None,
    on_reasoning: ReasoningSink | None = None,
) -> _RetriedRequest | TurnOutcome:
    """provider 报出上下文超限时先压一次、再重试一次，上限 1 次（ADR-0019）。

    照 DSH 的 `agent/request-error`：只有上下文超限这一种失败触发这种重试，上限是它的
    `maxOverflowRetries` 默认 1。压不动（没有可遮蔽的内容）就直接把原失败塌成溢出；
    重试仍报同一失败也一样塌。两条路都不写 `error/model`。
    """
    compacted = await _compact_if_over_line(
        log=log,
        step_id=step_id,
        settings=settings,
        provider=provider,
        cancel=cancel,
        events=events,
        context=context,
    )
    if isinstance(compacted, (LogWriteFailure, LogReadFailure)):
        return _turn_failure(compacted, steps)
    if isinstance(compacted, ProviderFailure):
        return await _provider_error(log, step_id, compacted, steps, [])

    reread = read_events(log.path)
    if isinstance(reread, LogReadFailure):
        return _turn_failure(reread, steps)
    # `_compact_if_over_line` 的 `None` 只说「没失败」：真压没压要看日志里这一步的摘要记录。
    compacted_here = any(
        event.type == "compaction/summary" and event.payload.get("step_id") == step_id
        for event in reread
    )
    if not compacted_here:
        return await _context_overflow(
            log,
            step_id,
            steps,
            (
                f"provider 报出上下文超限且无可遮蔽的内容：{failure.detail}"
                f"（{_budget_triple(settings, reread, context.messages)}）"
            ),
            retry_events,
        )

    folded = fold(reread)
    tool_names = [spec.name for spec in registry.specs()]
    # 重试发出去的是遮蔽之后那份表层：快照先落，日志说的就是实际发出去的（ADR-0019）。
    written = _append_all(
        log,
        [
            ("context/assembled", assembled_payload(step_id, folded)),
            ("model/request", {"step_id": step_id, "tools": tool_names}),
        ],
    )
    if written is not None:
        return _turn_failure(written, steps)

    # 重试是另一次 generate：本步的增量事实从头算（design D6 的「含压缩重试」）。
    if delta_state is not None:
        delta_state.streamed_any = False
    generated = await provider.generate(
        folded.messages,
        registry.specs(),
        cancel,
        on_delta=on_delta,
        on_reasoning=on_reasoning,
    )
    attempts = _retry_events(step_id, generated)
    if isinstance(generated, ProviderFailure):
        if generated.code == PROVIDER_CONTEXT_OVERFLOW:
            return await _context_overflow(
                log,
                step_id,
                steps,
                (
                    f"请求级压缩之后 provider 仍报上下文超限：{generated.detail}"
                    f"（{_budget_triple(settings, reread, folded.messages)}）"
                ),
                attempts,
            )
        return await _provider_error(log, step_id, generated, steps, attempts)
    return _RetriedRequest(generated=generated, retry_events=attempts)


def _drop_leading_unit(body: list[Message]) -> list[Message]:
    """从头部丢一个完整单位：带调用的那条 assistant 与回答它的那些 tool 消息一起丢。

    逐条丢会把一组工具往返拆散——留下的 tool 消息带着没人请求它的 `tool_call_id`（ADR-0023）。
    """
    first = body[0]
    if not first.tool_calls:
        return body[1:]
    called = {call["id"] for call in first.tool_calls if isinstance(call.get("id"), str)}
    rest = body[1:]
    cut = 0
    while cut < len(rest) and rest[cut].role == "tool" and rest[cut].tool_call_id in called:
        cut += 1
    return rest[cut:]


async def _compact_if_over_line(
    *,
    log: EventLog,
    step_id: str,
    settings: SessionSettings,
    provider: Provider,
    cancel: asyncio.Event,
    events: Sequence[EventRecord],
    context: AssembledContext,
) -> ProviderFailure | LogWriteFailure | LogReadFailure | None:
    """越线时压缩一次：调模型生成摘要、写一条 `compaction/summary`（design D1 与 D2）。

    没有可遮蔽的内容、或那段裁到最小仍装不进窗口时什么都不写、返回 `None`：调用方重新读数，
    那条路通向溢出。
    """
    rng = _shadowed_range(events, settings)
    if rng is None:
        return None
    tokens_before = budget_reading(events, context.messages)

    # 摘要请求自己也要装得进窗口：装不下就从该段头部按往返整对丢，一条都不剩时不发请求（ADR-0023）。
    header = context.messages[:1]
    instruction = Message(role="user", content=SUMMARY_INSTRUCTION)
    summary_budget = pressure_budget(settings.window, settings.reserve)
    body = fold_range(events, start=rng["start"], end=rng["end"])
    while body and estimate_tokens([*header, *body, instruction]) > summary_budget:
        body = _drop_leading_unit(body)
    if not body:
        return None

    written = _append_all(
        log,
        [("model/request", {"step_id": step_id, "tools": [], "purpose": PURPOSE_COMPACTION})],
    )
    if written is not None:
        return written

    generated = await provider.generate(
        # 摘要请求只装本次要遮蔽的那一段（ADR-0023）：受保护头部加区间折出的对话，
        # 不是整份表层——整份表层正是它要缩小的那个东西。
        [*header, *body, instruction],
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
            *_retry_events(step_id, generated),
            (
                "model/response",
                {
                    "step_id": step_id,
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
                    "step_id": step_id,
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


def start_session(*, prompt: str, entry: SessionEntry, env: SessionEnv) -> TurnOutcome | None:
    """写 `session/start`。成功返回 None，日志层坏了就返回失败结果。"""
    settings = env.settings
    start_payload: dict[str, Any] = {
        "entry": entry,
        "workspace": str(Path(settings.workspace).resolve()),
        "provider": settings.provider_name,
        "max_steps": settings.max_steps,
        "append_system_prompt": settings.append_system_prompt,
        "goal_policy": GOAL_POLICY_VERSION,
        "prompt": prompt,
        "sandbox": settings.sandbox,
        "approval": settings.approval,
        "reasoning_effort": settings.reasoning_effort,
        "window": settings.window,
        "reserve": settings.reserve,
        "compaction_threshold_ratio": settings.compaction_threshold_ratio,
        "compaction_headroom_tokens": settings.compaction_headroom_tokens,
        "compaction_retain_ratio": settings.compaction_retain_ratio,
        "compaction_retain_tokens": settings.compaction_retain_tokens,
        "tools": [spec.name for spec in env.registry.specs()],
    }
    if settings.platform is not None:
        # 平台事实由入口填（ADR-0029）：`session/start` 原样写下去，折叠头部据此出运行环境块。
        start_payload["platform"] = dict(settings.platform)
    if settings.parent_session_id is not None:
        # 子会话的父子关系（M12）：根会话不写这两项，视图里回落成 null / 0。
        start_payload["parent_session_id"] = settings.parent_session_id
        start_payload["depth"] = settings.depth
        # 委派声明进受保护头部：子会话的权限范围固定、被拒的操作不要重试（照 DSH 的
        # `subagent:delegation`）。落在 `session/start` 里，回放折叠的是同一份事实。
        start_payload["delegated"] = True
        if settings.parent_tool_call_id is not None:
            start_payload["parent_tool_call_id"] = settings.parent_tool_call_id
    model_skills = [skill for skill in settings.skills if skill.model_invocable]
    if model_skills:
        # 模型面只列模型可调的技能（skill-invocation-policy）；正文不进 payload。
        start_payload["skills"] = [
            {
                "name": skill.name,
                "description": skill.description,
                "rank": skill.rank,
                "source": skill.source,
                "path": str(skill.path),
                "model_invocable": skill.model_invocable,
                "user_invocable": skill.user_invocable,
            }
            for skill in model_skills
        ]
    if not settings.skills_complete:
        start_payload["skills_incomplete"] = True
    if settings.subagent_preset is not None:
        # 子会话用哪一档部署 preset（M14）：回放不依赖配置，审计与对照要它。
        start_payload["preset"] = settings.subagent_preset
    if settings.preset_persona is not None:
        start_payload["preset_persona"] = settings.preset_persona
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
        return _turn_failure(failure, 0)
    return None


async def run_turn(
    *,
    env: SessionEnv,
    turn_id: str,
    first_step_index: int,
    cancel: asyncio.Event,
    user_message: str | None = None,
    message_source: Mapping[str, Any] | None = None,
    goal_round: GoalRound | None = None,
) -> TurnOutcome:
    """跑一轮：一条输入展开的那串往返。轮内上限是 `max_steps`，会话级没有上限。

    轮的边界在这里落盘——`turn/start` 在第一个 `step/start` 之前、`turn/end` 在最后一个
    `step/end` 之后（design D3）。这里不写 `session/end`：会话是否结束由入口决定（ADR-0011）。

    `user_message` 是开启这一轮的那条输入：给了就写成一条 `user/message`，落在轮边界之内
    （design D5）。不给是 `run`——它的人话住在 `session/start`（design D6 记的不对称）。

    `message_source` 区分这条输入是人打的还是目标轮次注入的（M13）：缺省 `{"kind": "user"}`。

    `goal_round` 是 goal 轮次的唯一入口：正文与来源都由它派生，且由 `_run_steps` 在首条
    `context/assembled` 之后与它同批补写 `goal/updated`（装配成功才消耗额度，ADR-0043）。
    """
    # 轮首清空：上一轮没答完的问题不带进新轮（与 `todos` 的轮作用域同一条边界）。
    env.questions.pending = None
    if goal_round is not None:
        if user_message is not None or message_source is not None:
            raise ValueError("goal_round 与 user_message / message_source 不能同时给")
        user_message = render_goal_round(goal_round.goal, goal_round.round)
        message_source = {
            "kind": "goal",
            "goal_id": goal_round.goal.id,
            "revision": goal_round.goal.revision,
            "round": goal_round.round,
        }
    opening: list[tuple[str, dict[str, Any]]] = [("turn/start", {"turn_id": turn_id})]
    if user_message is not None:
        source: dict[str, Any] = (
            {"kind": "user"} if message_source is None else dict(message_source)
        )
        opening.append(
            ("user/message", {"turn_id": turn_id, "content": user_message, "source": source})
        )
    failure = _append_all(env.log, opening)
    if failure is not None:
        return _turn_failure(failure, 0)

    outcome = await _run_steps(
        env=env,
        turn_id=turn_id,
        first_step_index=first_step_index,
        cancel=cancel,
        goal_round=goal_round,
    )
    if outcome.stop_reason not in STOP_REASONS:
        # 内核坏了：写不出 `step/end`，也就不写 `turn/end`。
        return outcome
    written = _append_all(
        env.log,
        [
            (
                "turn/end",
                {
                    "turn_id": turn_id,
                    "stop_reason": outcome.stop_reason,
                    "steps": outcome.steps,
                    "tool_calls": outcome.tool_calls,
                },
            ),
        ],
    )
    if written is not None:
        return _turn_failure(written, outcome.steps)
    return outcome


def _catalog_shadowed(events: Sequence[EventRecord], seq: int) -> bool:
    for event in events:
        if event.type != "compaction/summary":
            continue
        shadowed = event.payload.get("shadowed_range")
        if isinstance(shadowed, Mapping):
            start = shadowed.get("start")
            end = shadowed.get("end")
            if isinstance(start, int) and isinstance(end, int) and start <= seq <= end:
                return True
    return False


def _adopt_catalog(env: SessionEnv, events: Sequence[EventRecord]) -> None:
    """续跑/回放时从最新的目录消息恢复指纹，避免重复注入。"""
    for event in reversed(events):
        if event.type == "user/message" and event.payload.get("source") == "skill-catalog":
            digest = event.payload.get("digest")
            if isinstance(digest, str):
                env.skill_catalog.last_digest = digest
                env.skill_catalog.last_seq = event.seq
            return


def _adopt_contracts(env: SessionEnv, events: Sequence[EventRecord]) -> None:
    """续跑/回放时从最新的契约消息恢复指纹，避免重复注入。"""
    for event in reversed(events):
        if event.type == "user/message" and event.payload.get("source") == "workspace-instructions":
            digest = event.payload.get("digest")
            if isinstance(digest, str):
                env.contracts.last_digest = digest
                env.contracts.last_seq = event.seq
                scopes = event.payload.get("scopes")
                if isinstance(scopes, list):
                    env.contracts.last_paths = tuple(
                        str(item.get("path")) for item in scopes if isinstance(item, dict)
                    )
            return


def _maybe_emit_contracts(env: SessionEnv, turn_id: str) -> LogWriteFailure | None:
    """装配前观察工作区契约：首轮注入、指纹变了替换、两份都没了退休。"""
    render = load_contracts(env.settings.workspace, env.contracts_home)
    events = read_events(env.log.path)
    if isinstance(events, LogReadFailure):
        return None
    state = env.contracts
    if state.last_digest is None and state.last_seq is None:
        _adopt_contracts(env, events)
    if render.text:
        shadowed = state.last_seq is not None and _catalog_shadowed(events, state.last_seq)
        if state.last_digest == render.digest and not shadowed:
            return None
        payload: dict[str, Any] = {
            "turn_id": turn_id,
            "content": render.text,
            "source": "workspace-instructions",
            "digest": render.digest,
            "scopes": [
                {
                    "scope": item.scope,
                    "path": item.path,
                    "digest": item.digest,
                    "bytes": item.bytes,
                    "truncated": item.truncated,
                }
                for item in render.scopes
            ],
        }
    else:
        if state.last_digest is None or state.last_digest == render.digest:
            return None
        payload = {
            "turn_id": turn_id,
            "content": render_removed(state.last_paths or ("AGENTS.md",)),
            "source": "workspace-instructions",
            "removed": True,
            "digest": render.digest,
            "scopes": [],
        }
    record = env.log.append("user/message", payload)
    if isinstance(record, LogWriteFailure):
        return record
    state.last_digest = render.digest
    state.last_seq = record.seq
    state.last_paths = tuple(item.path for item in render.scopes)
    return None


def _maybe_emit_catalog(env: SessionEnv, turn_id: str) -> LogWriteFailure | None:
    """装配前观察技能目录：首轮注入、指纹变了替换、清空退休、压缩后重建。"""
    registry = env.skills_registry
    discovery = (
        registry.snapshot()
        if registry is not None
        else SkillDiscovery(env.settings.skills, env.settings.skills_complete)
    )
    model_skills = tuple(skill for skill in discovery.skills if skill.model_invocable)
    digest = catalog_digest(model_skills, discovery.complete)
    events = read_events(env.log.path)
    if isinstance(events, LogReadFailure):
        return None
    state = env.skill_catalog
    if state.last_digest is None and state.last_seq is None:
        _adopt_catalog(env, events)
    shadowed = state.last_seq is not None and _catalog_shadowed(events, state.last_seq)
    if state.last_digest == digest and not shadowed:
        return None
    if not model_skills and discovery.complete and state.last_digest is None and not shadowed:
        return None
    record = env.log.append(
        "user/message",
        {
            "turn_id": turn_id,
            "content": render_catalog_message(model_skills, discovery.complete),
            "source": "skill-catalog",
            "incomplete": not discovery.complete,
            "digest": digest,
        },
    )
    if isinstance(record, LogWriteFailure):
        return record
    state.last_digest = digest
    state.last_seq = record.seq
    return None


async def _run_steps(
    *,
    env: SessionEnv,
    turn_id: str,
    first_step_index: int,
    cancel: asyncio.Event,
    goal_round: GoalRound | None = None,
) -> TurnOutcome:
    """轮内的显式步循环：记账 → 装配上下文 → 调模型 → 派发工具 → 判定停止。"""
    log = env.log
    provider = env.provider
    registry = env.registry
    settings = env.settings
    approval_gate = env.approval_gate
    stop_reason = STOP_MODEL_COMPLETED
    denial_code: str | None = None
    denial_detail = ""
    steps = 0
    tool_calls = 0
    for offset in range(settings.max_steps):
        turn_index = first_step_index + offset
        steps = offset + 1
        step_id = f"t{turn_index}"
        tool_names = [spec.name for spec in registry.specs()]
        delta_state = DeltaState()
        capture = _StepCapture()
        if env.on_delta is None and env.on_reasoning is None:
            text_sink = None
            reasoning_sink = None
        else:
            text_sink, reasoning_sink = _capture_sinks(
                capture, env.on_delta, env.on_reasoning, step_id, delta_state
            )

        failure = _append_all(log, [("step/start", {"step_id": step_id})])
        if failure is not None:
            return _turn_failure(failure, steps)

        failure = _maybe_emit_contracts(env, turn_id)
        if failure is not None:
            return _turn_failure(failure, steps)

        failure = _maybe_emit_catalog(env, turn_id)
        if failure is not None:
            return _turn_failure(failure, steps)

        events = read_events(log.path)
        if isinstance(events, LogReadFailure):
            return _turn_failure(events, steps)
        context = fold(events)
        # 装配之内的一次压缩（design D5）：越线才压缩，一次装配最多一次，取消在场时不压缩。
        line = _trigger_line(settings)
        if budget_reading(events, context.messages) > line and not cancel.is_set():
            compacted = await _compact_if_over_line(
                log=log,
                step_id=step_id,
                settings=settings,
                provider=provider,
                cancel=cancel,
                events=events,
                context=context,
            )
            if isinstance(compacted, (LogWriteFailure, LogReadFailure)):
                return _turn_failure(compacted, steps)
            if isinstance(compacted, ProviderFailure):
                return await _provider_error(log, step_id, compacted, steps, [])
            events = read_events(log.path)
            if isinstance(events, LogReadFailure):
                return _turn_failure(events, steps)
            context = fold(events)
            reading = budget_reading(events, context.messages)
            # 溢出判据是压力预算 `W - O`：触发线只决定这次装配要不要尝试压缩。
            # 小窗口下触发线可以比保留预算还小，拿它判溢出会在真墙之前自己撞墙。
            pressure = pressure_budget(settings.window, settings.reserve)
            if reading > pressure:
                # 措辞跟着日志里的事实走：真写过摘要才说「压缩之后」；什么都没遮蔽才说
                # 「无可遮蔽」；有可遮蔽的那一段、只是它本身就装不进窗口，就说它装不下。
                compacted_here = any(
                    event.type == "compaction/summary" and event.payload.get("step_id") == step_id
                    for event in events
                )
                if compacted_here:
                    head = f"压缩之后预算读数 {reading} 仍超过压力预算 {pressure}"
                elif _shadowed_range(events, settings) is None:
                    head = f"无可遮蔽的内容，预算读数 {reading} 已超过压力预算 {pressure}"
                else:
                    head = f"可遮蔽的那一段本身就装不下，预算读数 {reading} 超过压力预算 {pressure}"
                return await _context_overflow(log, step_id, steps, f"{head}（触发线 {line}）")

        opening: list[tuple[str, dict[str, Any]]] = [
            ("context/assembled", assembled_payload(step_id, context))
        ]
        if goal_round is not None and offset == 0:
            # 额度在首条 context/assembled 落盘之后才计：这一轮真的装进了上下文才算数，
            # 装配之前失败（注入、折叠、压缩）不扣轮次（ADR-0043）。
            advanced = advance_round(goal_round.goal, goal_round.round)
            opening.append(("goal/updated", {"goal": advanced.model_dump(exclude_none=True)}))
        opening.append(("model/request", {"step_id": step_id, "tools": tool_names}))
        failure = _append_all(log, opening)
        if failure is not None:
            return _turn_failure(failure, steps)

        generated = await provider.generate(
            context.messages,
            registry.specs(),
            cancel,
            on_delta=text_sink,
            on_reasoning=reasoning_sink,
        )
        # 重试事实由 provider 带回、由循环写进日志：provider 不碰日志（不变量 A）。
        retry_events = _retry_events(step_id, generated)
        if isinstance(generated, ProviderFailure):
            if generated.code == PROVIDER_CONTEXT_OVERFLOW:
                # provider 报出的超限先压一次再重试一次；救不动时与估算兜底同一个结果
                # （不变量 D）：不写 `error/model`。
                recovered = await _recover_overflowed_request(
                    log=log,
                    step_id=step_id,
                    steps=steps,
                    settings=settings,
                    provider=provider,
                    registry=registry,
                    cancel=cancel,
                    events=events,
                    context=context,
                    failure=generated,
                    retry_events=retry_events,
                    on_delta=text_sink,
                    delta_state=delta_state,
                    on_reasoning=reasoning_sink,
                )
                if isinstance(recovered, TurnOutcome):
                    return recovered
                generated, retry_events = recovered.generated, recovered.retry_events
            if isinstance(generated, ProviderFailure):
                if (
                    generated.code == "PROVIDER_ABORTED"
                    and (env.on_delta is not None or env.on_reasoning is not None)
                    and cancel.is_set()
                ):
                    return _abort_turn(log, step_id, steps, capture.blocks(), evidence=True)
                return await _provider_error(
                    log, step_id, generated, steps, retry_events, capture.blocks()
                )

        if cancel.is_set() and delta_state.streamed_any:
            # 流式读取中途取消：已交付前缀写成 interrupted message，不写半条成功 response。
            # 没流过增量时走下面的正常路径——模型其实已经完整返回，取消不该吞掉整段。
            return _abort_turn(log, step_id, steps, capture.blocks(), evidence=True)

        failure = _append_all(
            log,
            [
                *retry_events,
                (
                    "model/response",
                    {
                        "step_id": step_id,
                        "content": generated.content,
                        "blocks": [block.model_dump(mode="json") for block in generated.blocks],
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
            return _turn_failure(failure, steps)

        fence_denied = False
        batch = await _dispatch_batch(
            log=log,
            step_id=step_id,
            calls=generated.tool_calls,
            registry=registry,
            settings=settings,
            approval_gate=approval_gate,
            cancel=cancel,
            session=env,
        )
        if batch.failure is not None:
            return _turn_failure(batch.failure, steps)
        tool_calls += batch.tool_calls
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
        elif steps == settings.max_steps:
            stop_reason = STOP_MAX_STEPS
        else:
            stop_reason = STOP_TOOL_CALLS

        closing_events: list[tuple[str, dict[str, Any]]] = []
        if cancel.is_set():
            closing_events.append(
                (
                    "error/abort",
                    {"step_id": step_id, "code": STOP_ABORTED, "detail": "取消被置位"},
                )
            )
        closing_events.append(("step/end", {"step_id": step_id, "stop_reason": stop_reason}))

        failure = _append_all(log, closing_events)
        if failure is not None:
            return _turn_failure(failure, steps)

        # 步末回退：`step/end` 已落盘、下一步还没开始。放在这里而不是轮末，
        # 同轮里「前一步没增量、后一步流式」才不会倒序（restore-chat-streaming design D3.1）。
        notified = _notify_step_end(env, step_id, generated.content, steps)
        if notified is not None:
            return notified

        if (
            cancel.is_set()
            or fence_denied
            or not generated.tool_calls
            or steps == settings.max_steps
        ):
            break

    return TurnOutcome(
        stop_reason=stop_reason,
        steps=steps,
        failure_code=denial_code,
        detail=denial_detail,
        tool_calls=tool_calls,
    )


def end_session(*, env: SessionEnv, stop_reason: str, steps: int) -> TurnOutcome | None:
    """写 `session/end`。成功返回 None，日志层坏了就返回失败结果。"""
    failure = _append_all(env.log, [("session/end", {"stop_reason": stop_reason, "steps": steps})])
    if failure is not None:
        return _turn_failure(failure, steps)
    return None


async def run_session(
    *,
    prompt: str,
    entry: SessionEntry,
    provider: Provider,
    log: EventLog,
    registry: ToolRegistry,
    settings: SessionSettings,
    cancel: asyncio.Event,
    approval_gate: ApprovalGate = STDIN_APPROVAL_GATE,
    on_delta: StepDeltaSink | None = None,
    on_reasoning: ReasoningSink | None = None,
    on_step_end: StepEndSink | None = None,
    skills_registry: SkillRegistry | None = None,
) -> RunOutcome:
    """一次性入口（`run` / `serve`）：开始会话、恰一轮、结束会话。

    轮编号与步编号都从 1 起；REPL 自己数轮、给下一个轮起始编号（design D3）。
    """
    env = SessionEnv(
        provider=provider,
        log=log,
        registry=registry,
        settings=settings,
        approval_gate=approval_gate,
        on_delta=on_delta,
        on_reasoning=on_reasoning,
        on_step_end=on_step_end,
        skills_registry=skills_registry,
    )
    return await run_session_env(prompt=prompt, entry=entry, env=env, cancel=cancel)


def goal_after(log: EventLog) -> GoalSnapshot | LogReadFailure | None:
    """按日志折当前目标；读不动就把失败往上抛，不猜。"""
    events = read_events(log.path)
    if isinstance(events, LogReadFailure):
        return events
    return fold_goal(events)


def next_goal_round(env: SessionEnv) -> GoalRound | None:
    """已武装、`active`、还有额度时算出下一轮；否则 `None`。

    `/goal resume` 的即时驱动（chat 与 host）共用这一份判定：命令层只负责确认
    「武装位确实从假翻到真」，目标相位与额度在这里读一次。
    """
    if not env.goal_runtime.armed:
        return None
    goal = goal_after(env.log)
    if isinstance(goal, LogReadFailure) or goal is None or goal.phase != "active":
        return None
    if goal.rounds_started >= goal.max_rounds:
        return None
    return GoalRound(goal=goal, round=goal.rounds_started + 1)


def exhaust_goal_rounds(
    *, env: SessionEnv, decision: RoundDecision, steps: int
) -> TurnOutcome | None:
    """额度用尽：落 `blocked{round-limit}` 并解除武装。写不进日志就是轮失败。"""
    assert decision.goal is not None
    blocked = exhaust_goal(decision.goal)
    written = env.log.append("goal/updated", {"goal": blocked.model_dump(exclude_none=True)})
    if isinstance(written, LogWriteFailure):
        return _turn_failure(written, steps)
    env.goal_runtime.armed = False
    return None


@dataclass(frozen=True)
class RoundSettlement:
    """一轮之后的收尾结果：判定 + 可能的写日志失败（失败时入口应当收会话）。"""

    decision: RoundDecision
    failure: TurnOutcome | None = None


def settle_turn(
    *, env: SessionEnv, turn: TurnOutcome, steps: int, goal_round: bool
) -> RoundSettlement:
    """轮后收尾的唯一实现：读目标、判下一轮、把该落的副作用落掉。

    `run` / `chat` / `host` 三处入口都调它，避免「host 只有命令面、没有驱动」这类分叉
    （2026-11-20 人裁）。它自己不打印、不决定入口怎么停——只回答「接下来该不该开轮」。
    """
    goal = goal_after(env.log)
    if isinstance(goal, LogReadFailure):
        return RoundSettlement(RoundDecision("stop"), _turn_failure(goal, steps))
    # 连续空转轮数：goal 轮次零工具调用加一，有动作清零；人类轮一律清零
    # （人参与了，空转链断了）。只有 `stall_rounds > 0` 时这个数才参与判定。
    if goal_round:
        env.goal_runtime.idle_rounds = (
            env.goal_runtime.idle_rounds + 1 if turn.tool_calls == 0 else 0
        )
    else:
        env.goal_runtime.idle_rounds = 0
    decision = next_round(
        goal=goal,
        armed=env.goal_runtime.armed,
        stop_reason=turn.stop_reason,
        question_pending=env.questions.pending is not None,
        idle_rounds=env.goal_runtime.idle_rounds,
        stall_rounds=env.settings.goal.stall_rounds,
        goal_round=goal_round,
    )
    if decision.kind == "exhausted":
        return RoundSettlement(
            decision, exhaust_goal_rounds(env=env, decision=decision, steps=steps)
        )
    if decision.kind == "stalled":
        # 空转不改相位、不落事件：`armed` 本来就是进程内的自动推进开关（D14）。
        # 计数清零，`/goal resume` 之后重新给满阈值。
        env.goal_runtime.armed = False
        env.goal_runtime.idle_rounds = 0
        return RoundSettlement(decision)
    if decision.kind == "stop" and turn.stop_reason in NO_CONTINUE_REASONS:
        return RoundSettlement(decision, close_failed_round(env=env, turn=turn))
    return RoundSettlement(decision)


def close_failed_round(*, env: SessionEnv, turn: TurnOutcome) -> TurnOutcome | None:
    """失败收尾：一律解除武装；`ABORTED`（人取消）另把 `active` 目标置 `paused`。

    其余失败 `phase` 留在 `active`——上游抖动不该替人决定目标作废，人 `/goal resume` 即可。
    """
    env.goal_runtime.armed = False
    if turn.stop_reason != STOP_ABORTED:
        return None
    goal = goal_after(env.log)
    if isinstance(goal, LogReadFailure):
        return _turn_failure(goal, turn.steps)
    if goal is None or goal.phase != "active":
        return None
    written = env.log.append(
        "goal/updated", {"goal": abort_goal(goal).model_dump(exclude_none=True)}
    )
    if isinstance(written, LogWriteFailure):
        return _turn_failure(written, turn.steps)
    return None


async def run_session_env(
    *, prompt: str, entry: SessionEntry, env: SessionEnv, cancel: asyncio.Event
) -> RunOutcome:
    """在已装配好的 `env` 上跑一次性会话：开始、按目标轮次展开若干轮、结束。

    `run` / `serve` 从 `run_session` 走到这里；`subagent` 直接带着子会话的 env 调用它——
    「开始 → 若干轮 → 结束」只有一份实现。

    轮数由目标决定（design D3）：没有可续跑的目标时恰一轮；目标 `active` 且已武装时，
    每个 `turn/end` 之后按 `next_round` 判定，续跑就再开一轮。驱动不另起协程：判定与
    开轮在同一个协程里顺序做完，写日志成功即准入。
    """
    log = env.log
    started = start_session(prompt=prompt, entry=entry, env=env)
    if started is not None:
        return _run_outcome(log, started)

    turns = 0
    steps = 0
    goal_round: GoalRound | None = None
    turn = await run_turn(env=env, turn_id="s1", first_step_index=1, cancel=cancel)
    while True:
        if turn.stop_reason not in STOP_REASONS:
            # 内核坏了：不再开轮，也不写 session/end。
            return _run_outcome(log, turn)
        turns += 1
        steps += turn.steps

        settlement = settle_turn(env=env, turn=turn, steps=steps, goal_round=goal_round is not None)
        if settlement.failure is not None:
            return _run_outcome(log, settlement.failure)
        decision = settlement.decision
        if decision.kind != "continue":
            # `stop` / `exhausted` / `awaiting_input` / `stalled` 都回到入口：
            # 一次性入口没有人可等，问题未决时直接收会话（目标保持 active，下次 resume 再续）。
            break
        assert decision.goal is not None
        goal_round = GoalRound(goal=decision.goal, round=decision.round)
        turn = await run_turn(
            env=env,
            turn_id=f"s{turns + 1}",
            first_step_index=steps + 1,
            cancel=cancel,
            goal_round=goal_round,
        )

    ended = end_session(env=env, stop_reason=turn.stop_reason, steps=steps)
    if ended is not None:
        return _run_outcome(log, ended)
    # 轮数可能大于一，`steps` 是这次会话的累计；失败码仍取最后一轮。
    return RunOutcome(
        session_id=log.session_id,
        stop_reason=turn.stop_reason,
        steps=steps,
        failure_code=turn.failure_code,
        detail=turn.detail,
    )
