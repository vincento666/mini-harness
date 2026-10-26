"""宿主运行时状态：一个进程持有的会话表（H1 design D3）。

这一层只放「服务比会话活得久」需要的东西：服务器级默认设置、会话上限、许可开关。
单个会话的队列 / 取消 / 审批在 `HostSession` 里；HTTP 路由在 `cli/host.py`。
"""

from __future__ import annotations

import asyncio
from collections import deque
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime

from mini_harness.events import EventLog
from mini_harness.loop import (
    ENTRY_HOST,
    STOP_REASONS,
    SessionEnv,
    SessionSettings,
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

# 同时在跑的会话上限（H1 spec：默认 4）。
MAX_SESSIONS = 4
# 审批等待上限（H1 spec：默认 300 s）；超时塌成 UNAVAILABLE，不默认批准。
APPROVAL_TIMEOUT_SECONDS = 300.0

# 会话状态：只有这三个值（H1 spec）。
SESSION_IDLE = "idle"
SESSION_RUNNING = "running"
SESSION_ENDED = "ended"


@dataclass
class HostSession:
    """一个会话的全部运行时句柄：一个 env、一个队列、一个取消事件、一组审批 future。"""

    settings: SessionSettings
    log: EventLog
    env: SessionEnv
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    status: str = SESSION_IDLE
    queue: deque[str] = field(default_factory=deque)
    cancel: asyncio.Event | None = None
    approvals: dict[str, asyncio.Future[bool]] = field(default_factory=dict)
    task: asyncio.Task[None] | None = None
    segments: int = 0
    turns: int = 0

    @property
    def last_seq(self) -> int:
        return self.log.last_seq

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
        max_sessions: int = MAX_SESSIONS,
    ) -> None:
        self.defaults = defaults
        self.allow_danger_full_access = allow_danger_full_access
        self.allow_auto_approval = allow_auto_approval
        self.max_sessions = max_sessions
        self.sessions: dict[str, HostSession] = {}

    def session_count(self) -> int:
        return len(self.sessions)


def create_session(
    state: HostState,
    request: AssemblyRequest,
    environ: Mapping[str, str],
) -> HostSession | Failure:
    """装配并开一个空闲会话：写 `session/start`（`entry=host`、`prompt=""`），不跑段。"""
    if state.session_count() >= state.max_sessions:
        return Failure(
            "TOO_MANY_SESSIONS",
            f"同时在跑的会话上限是 {state.max_sessions}",
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
    state.sessions[prepared.log.session_id] = handle
    return handle


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
        failed = segment.stop_reason not in STOP_REASONS
    finally:
        handle.cancel = None
        handle.task = None
        if failed:
            handle.status = SESSION_ENDED
            handle.queue.clear()
        else:
            handle.status = SESSION_IDLE
            if handle.queue:
                _begin_segment(handle, handle.queue.popleft())
