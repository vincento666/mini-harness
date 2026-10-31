"""宿主运行时状态：一个进程持有的会话表（H1 design D3）。

这一层只放「服务比会话活得久」需要的东西：服务器级默认设置、会话上限、许可开关。
单个会话的队列 / 取消 / 审批在 `HostSession` 里；HTTP 路由在 `cli/host.py`。
"""

from __future__ import annotations

import asyncio
import contextlib
from collections import deque
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from typing import Literal

from mini_harness.events import EventLog
from mini_harness.loop import (
    ENTRY_HOST,
    STOP_MODEL_COMPLETED,
    STOP_REASONS,
    SessionEnv,
    SessionSettings,
    end_session,
    run_turn_segment,
    start_session,
)
from mini_harness.session.assembly import (
    EXIT_INTERNAL_ERROR,
    EXIT_INVALID_ARGUMENT,
    AssemblyRequest,
    Failure,
    assemble,
)
from mini_harness.tools.fences import ApprovalDecision

# 同时在跑的会话上限（H1 spec：默认 4）。
MAX_SESSIONS = 4
# 审批等待上限（H1 spec：默认 300 s）；超时塌成 UNAVAILABLE，不默认批准。
APPROVAL_TIMEOUT_SECONDS = 300.0
# 每个 SSE 连接的 delta 队列上限；满了丢最旧，ephemeral 可丢（H2 design D3）。
DELTA_QUEUE_MAX = 256

# 会话状态：只有这三个值（H1 spec）。
SessionStatus = Literal["idle", "running", "ended"]
SESSION_IDLE: SessionStatus = "idle"
SESSION_RUNNING: SessionStatus = "running"
SESSION_ENDED: SessionStatus = "ended"


@dataclass
class HostSession:
    """一个会话的全部运行时句柄：一个 env、一个队列、一个取消事件、一组审批 future。"""

    settings: SessionSettings
    log: EventLog
    env: SessionEnv
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    status: SessionStatus = SESSION_IDLE
    queue: deque[str] = field(default_factory=deque)
    cancel: asyncio.Event | None = None
    approvals: dict[str, asyncio.Future[bool | None]] = field(default_factory=dict)
    subscribers: set[asyncio.Queue[dict[str, object]]] = field(default_factory=set)
    delta_indexes: dict[str, int] = field(default_factory=dict)
    reasoning_indexes: dict[str, int] = field(default_factory=dict)
    task: asyncio.Task[None] | None = None
    stopping: bool = False
    ended_by_failure: bool = False
    segments: int = 0
    turns: int = 0

    @property
    def last_seq(self) -> int:
        return self.log.last_seq

    def subscribe_deltas(self) -> asyncio.Queue[dict[str, object]]:
        """一个 SSE 连接一个队列；返回后由调用方在断开时退订。"""
        queue: asyncio.Queue[dict[str, object]] = asyncio.Queue(maxsize=DELTA_QUEUE_MAX)
        self.subscribers.add(queue)
        return queue

    def unsubscribe_deltas(self, queue: asyncio.Queue[dict[str, object]]) -> None:
        self.subscribers.discard(queue)

    async def publish_delta(self, turn_id: str, text: str) -> None:
        """把一个正文增量广播给当前所有订阅者；慢读者丢最旧，不反压 provider。"""
        index = self.delta_indexes.get(turn_id, 0)
        self.delta_indexes[turn_id] = index + 1
        frame: dict[str, object] = {
            "turn_id": turn_id,
            "index": index,
            "text": text,
        }
        self._publish_ephemeral(frame)

    async def publish_reasoning(self, turn_id: str, index: int, text: str) -> None:
        """把一个 reasoning 增量广播给当前所有订阅者，与正文队列并列。"""
        self.reasoning_indexes[turn_id] = self.reasoning_indexes.get(turn_id, 0) + 1
        self._publish_ephemeral(
            {"turn_id": turn_id, "index": index, "text": text, "kind": "reasoning"}
        )

    def _publish_ephemeral(self, frame: dict[str, object]) -> None:
        for queue in list(self.subscribers):
            if queue.full():
                with contextlib.suppress(asyncio.QueueEmpty):
                    queue.get_nowait()
            with contextlib.suppress(asyncio.QueueFull):
                queue.put_nowait(frame)

    def view(self) -> dict[str, object]:
        """`GET /sessions` / `GET /sessions/{id}` 的一条：不返回密钥或 Authorization。"""
        return {
            "session_id": self.log.session_id,
            "status": self.status,
            "workspace": str(self.settings.workspace.resolve()),
            "created_at": self.created_at,
            "last_seq": self.last_seq,
            "turns": self.turns,
        }


class HostState:
    """服务器级状态：默认设置、许可、会话表。"""

    def __init__(
        self,
        *,
        defaults: AssemblyRequest,
        allow_danger_full_access: bool = False,
        allow_auto_approval: bool = False,
    ) -> None:
        self.defaults = defaults
        self.allow_danger_full_access = allow_danger_full_access
        self.allow_auto_approval = allow_auto_approval
        self.sessions: dict[str, HostSession] = {}

    def session_count(self) -> int:
        return len(self.sessions)

    def active_session_count(self) -> int:
        """上限只数还在跑的会话；`ended` 留着给列表读，不占额度。"""
        return sum(1 for handle in self.sessions.values() if handle.status != SESSION_ENDED)


def create_session(
    state: HostState,
    request: AssemblyRequest,
    environ: Mapping[str, str],
) -> HostSession | Failure:
    """装配并开一个空闲会话：写 `session/start`（`entry=host`、`prompt=""`），不跑段。"""
    if state.active_session_count() >= MAX_SESSIONS:
        return Failure(
            "TOO_MANY_SESSIONS",
            f"同时在跑的会话上限是 {MAX_SESSIONS}",
            EXIT_INVALID_ARGUMENT,
        )
    prepared = assemble(
        request,
        environ,
        allow_danger_full_access=state.allow_danger_full_access,
        allow_auto_approval=state.allow_auto_approval,
    )
    if isinstance(prepared, Failure):
        return prepared
    env = SessionEnv(
        provider=prepared.provider,
        log=prepared.log,
        registry=prepared.registry,
        settings=prepared.settings,
    )
    started = start_session(prompt="", entry=ENTRY_HOST, env=env)
    if started is not None:
        return Failure(
            started.failure_code or started.stop_reason,
            started.detail,
            EXIT_INTERNAL_ERROR,
        )
    handle = HostSession(settings=prepared.settings, log=prepared.log, env=env)
    handle.env = replace(
        env,
        approval_gate=HostApprovalGate(handle),
        on_delta=handle.publish_delta,
        on_reasoning=handle.publish_reasoning,
    )
    state.sessions[prepared.log.session_id] = handle
    return handle


class HostApprovalGate:
    """host 的 approval 门：把 `tool_call_id` 登记成 future，等 HTTP 回程。

    它 MUST NOT 读 stdin：没有 HTTP 应答时只等超时，超时塌成 `UNAVAILABLE`，不默认批准。
    """

    def __init__(self, handle: HostSession, *, timeout: float = APPROVAL_TIMEOUT_SECONDS) -> None:
        self._handle = handle
        self._timeout = timeout

    async def request(self, *, tool_call_id: str, tool_name: str, detail: str) -> ApprovalDecision:
        # 同一会话同一时刻只可能有一个待审批项（design D7）；撞上重复登记说明调用方坏了，
        # 门只能回 UNAVAILABLE，不能覆盖掉正在等的那个 future。
        if tool_call_id in self._handle.approvals:
            return "UNAVAILABLE"
        loop = asyncio.get_running_loop()
        answer: asyncio.Future[bool | None] = loop.create_future()
        self._handle.approvals[tool_call_id] = answer
        try:
            async with asyncio.timeout(self._timeout):
                approved = await answer
        except TimeoutError:
            return "UNAVAILABLE"
        finally:
            self._handle.approvals.pop(tool_call_id, None)
        if approved is None or self._handle.stopping:
            return "UNAVAILABLE"
        return "APPROVED" if approved else "DENIED"


def resolve_approval(handle: HostSession, tool_call_id: str, *, approve: bool) -> bool:
    """把一次 HTTP 应答交给正在等待的门；未知或已失效的 id 返回 False。"""
    answer = handle.approvals.get(tool_call_id)
    if answer is None or answer.done():
        return False
    answer.set_result(approve)
    return True


@dataclass(frozen=True)
class MessageAccepted:
    """一次 `POST /messages` 的结果：直接起段时带 `segment_id`，排队时为 `None`。"""

    segment_id: str | None
    queued: bool


def submit_message(handle: HostSession, content: str) -> MessageAccepted | Failure:
    """空闲时直接起段；段进行中入深度 1 的队列；队列已满是一条 409 的结果。"""
    if handle.status == SESSION_ENDED:
        return Failure("SESSION_NOT_FOUND", "会话已经结束", EXIT_INVALID_ARGUMENT)
    if handle.status == SESSION_RUNNING:
        if handle.queue:
            return Failure("SESSION_BUSY", "会话的待跑队列已满", EXIT_INVALID_ARGUMENT)
        handle.queue.append(content)
        return MessageAccepted(segment_id=None, queued=True)
    segment_id = _begin_segment(handle, content)
    return MessageAccepted(segment_id=segment_id, queued=False)


def _begin_segment(handle: HostSession, content: str) -> str:
    handle.segments += 1
    segment_id = f"s{handle.segments}"
    handle.status = SESSION_RUNNING
    cancel = asyncio.Event()
    handle.cancel = cancel
    handle.task = asyncio.create_task(_run_segment(handle, segment_id, content, cancel))
    return segment_id


async def _run_segment(
    handle: HostSession, segment_id: str, content: str, cancel: asyncio.Event
) -> None:
    failed = False
    try:
        segment = await run_turn_segment(
            env=handle.env,
            segment_id=segment_id,
            first_turn_index=handle.turns + 1,
            cancel=cancel,
            user_message=content,
        )
        handle.turns += segment.turns
        # 词表外才是内核失败；FENCE_DENIED / CONTEXT_WINDOW_EXCEEDED 也带 failure_code，
        # 但它们只停段、会话仍可用（ADR-0019 / design D6）。
        failed = segment.stop_reason not in STOP_REASONS
    finally:
        handle.cancel = None
        handle.task = None
        if failed:
            handle.status = SESSION_ENDED
            handle.ended_by_failure = True
            handle.queue.clear()
        else:
            handle.status = SESSION_IDLE
            if not handle.stopping and handle.queue:
                _begin_segment(handle, handle.queue.popleft())
            elif handle.stopping:
                handle.queue.clear()


def cancel_session(handle: HostSession) -> bool:
    """只取消当前段；没有段在跑返回 False（一条记录都不写）。

    段如果停在 approval 上，未决的 future 塌成 `UNAVAILABLE`（design D7），门不默认批准。
    """
    if handle.status != SESSION_RUNNING or handle.cancel is None:
        return False
    handle.cancel.set()
    for answer in handle.approvals.values():
        if not answer.done():
            answer.set_result(None)
    return True


def close_session(handle: HostSession) -> Failure | None:
    """空闲时写 `session/end`；段在跑与已关闭都交给调用方映射成 409 / 404。"""
    if handle.status == SESSION_RUNNING:
        return Failure("SESSION_BUSY", "会话正在跑一个段", EXIT_INVALID_ARGUMENT)
    if handle.status == SESSION_ENDED:
        return Failure("SESSION_NOT_FOUND", "会话已经结束", EXIT_INVALID_ARGUMENT)
    ended = end_session(
        env=handle.env,
        stop_reason=STOP_MODEL_COMPLETED,
        turns=handle.turns,
    )
    if ended is not None:
        return Failure(
            ended.failure_code or ended.stop_reason,
            ended.detail,
            EXIT_INTERNAL_ERROR,
        )
    handle.status = SESSION_ENDED
    return None


async def shutdown(state: HostState) -> None:
    """服务退出：取消所有段、等它们写完收尾记录，再为每个会话写 `session/end`。"""
    handles = list(state.sessions.values())
    for handle in handles:
        handle.stopping = True
        if handle.cancel is not None:
            handle.cancel.set()
        for answer in handle.approvals.values():
            if not answer.done():
                answer.set_result(None)
    tasks = [handle.task for handle in handles if handle.task is not None]
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)
    for handle in handles:
        if handle.status == SESSION_RUNNING:
            # 段没有在取消后收尾（极端情况）：不让它留成半条，直接补 `session/end`。
            handle.status = SESSION_IDLE
        if handle.ended_by_failure:
            # 内核失败把会话标成 ended，但 spec 要求退出时为每个会话写 `session/end`。
            end_session(
                env=handle.env,
                stop_reason=STOP_MODEL_COMPLETED,
                turns=handle.turns,
            )
            handle.ended_by_failure = False
        elif handle.status == SESSION_IDLE:
            close_session(handle)
