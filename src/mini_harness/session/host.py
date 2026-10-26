"""宿主运行时状态：一个进程持有的会话表（H1 design D3）。

这一层只放「服务比会话活得久」需要的东西：服务器级默认设置、会话上限、许可开关。
单个会话的队列 / 取消 / 审批在 `HostSession` 里；HTTP 路由在 `cli/host.py`。
"""

from __future__ import annotations

import asyncio
from collections import deque
from dataclasses import dataclass, field
from datetime import UTC, datetime

from mini_harness.events import EventLog
from mini_harness.loop import SessionEnv, SessionSettings
from mini_harness.session.assembly import AssemblyRequest

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
