"""`minihns serve` 的 HTTP 层：绑定、事件流路由、断开处理（design D7）。

这一层只读那份日志，不写任何东西进会话：客户端断开、慢读、从未连接都不是取消信号。
"""

from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass
from pathlib import Path

from aiohttp import web

from mini_harness.events import EventRecord, LogReadFailure, LogTail

# 默认监听地址。19387 是 DSH 的 desktop profile 在这台机器上的端口
# （`dsh-desktop-host/lib/index.js:231-235`），mini 故意错开，免得两个 harness 抢同一个端口。
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 19400

# host 的词表照 DSH 的 `dsh-host-webserver`：`host: union("127.0.0.1","0.0.0.0")`。
SERVE_HOSTS: tuple[str, ...] = ("127.0.0.1", "0.0.0.0")

# 事件流只有这一条路径；其它路径是 aiohttp 默认的 404。
EVENTS_PATH = "/events"
# 日志是追加写的文件，事件流跟它的方式是轮询偏移（design D6）。
TAIL_POLL_SECONDS = 0.02
# 续读游标的两个来源与优先级：查询参数覆盖 `Last-Event-ID` header（event-stream 规格）。
CURSOR_QUERY = "from"
CURSOR_HEADER = "Last-Event-ID"
# 没有游标时从第一条记录之前开始：日志的第一条 `seq` 是 0。
NO_CURSOR = -1
_CURSOR_DIGITS = re.compile(r"[0-9]+")


@dataclass(frozen=True)
class BindFailure:
    """绑定失败：它是 session 开始之前的参数错误，不是运行期故障。"""

    host: str
    port: int
    detail: str


def _sse_frame(record: EventRecord) -> bytes:
    """一条记录一帧：`id` 是 `seq`、`event` 是事件类型、`data` 是那一行的 JSON。"""
    return (
        f"id: {record.seq}\n"
        f"event: {record.type}\n"
        f"data: {json.dumps(record.model_dump(mode='json'), ensure_ascii=False)}\n\n"
    ).encode()


def _cursor(request: web.Request) -> int:
    """读出续读游标：`?from=<seq>` 覆盖 `Last-Event-ID`，两者都没有时从第一条记录开始。

    游标是「读到过的那条记录的 `seq`」，所以第一帧是它之后的一条；日志的第一条 `seq` 是 0，
    所以 `0` 是合法游标。负数或非整数是这条请求的参数错误，与会话无关：aiohttp 把
    `HTTPBadRequest` 变成 400 响应。
    """
    raw = request.query.get(CURSOR_QUERY)
    if raw is None:
        raw = request.headers.get(CURSOR_HEADER)
    if raw is None:
        return NO_CURSOR
    if not _CURSOR_DIGITS.fullmatch(raw) or int(raw) < 0:
        raise web.HTTPBadRequest(text=f"INVALID_ARGUMENT: 游标不是非负整数：{raw}")
    return int(raw)


class ServeServer:
    """一个进程一个会话：HTTP 层是那份日志的实时投影。"""

    def __init__(self, *, host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> None:
        self.host = host
        self.port = port
        # 会话收尾时置位：事件流跟到这一位就结束，进程跟着结束。
        self.session_finished = asyncio.Event()
        self._application = web.Application()
        self._application.router.add_get(EVENTS_PATH, self._events)
        self._runner: web.AppRunner | None = None
        self._log_path: Path | None = None

    def attach(self, log_path: Path) -> None:
        """把这份日志交给事件流。绑定在先、日志在后（design D3），所以这是分开的两步。"""
        self._log_path = log_path

    async def bind(self) -> BindFailure | None:
        """绑定并接收连接。端口被占时 `TCPSite.start()` 里的 `create_server` 抛 `OSError`。

        失败当场塌成 `BindFailure`。aiohttp 3.14 的顺序是 `runner.setup()` 先跑、站点后建：
        `BaseSite.__init__` 在 `runner.server is None` 时直接抛 `RuntimeError`
        （`web_runner.py:56-57`）。
        """
        runner = web.AppRunner(self._application)
        try:
            await runner.setup()
            await web.TCPSite(runner, self.host, self.port).start()
        except OSError as error:
            await runner.cleanup()
            return BindFailure(host=self.host, port=self.port, detail=str(error))
        self._runner = runner
        return None

    async def _events(self, request: web.Request) -> web.StreamResponse:
        """`GET /events`：从日志开头跟到会话收尾，一条记录一帧。"""
        # 绑定与 `attach` 之间没有 await，请求处理器不可能在日志存在之前跑起来。
        assert self._log_path is not None
        # 游标在 prepare 之前判：坏游标是 400 响应，不是一个开了一半的事件流。
        tail = LogTail(self._log_path, after=_cursor(request))
        response = web.StreamResponse(headers={"Content-Type": "text/event-stream"})
        await response.prepare(request)
        while True:
            records = tail.read_new()
            if isinstance(records, LogReadFailure):
                # 日志读不动是会话自己的失败，不在事件流里编一帧出来。
                return response
            for record in records:
                await response.write(_sse_frame(record))
            if self.session_finished.is_set():
                return response
            await asyncio.sleep(TAIL_POLL_SECONDS)

    async def close(self) -> None:
        """结束监听。会话收尾就是进程退出，所以监听跟着一起结束。"""
        if self._runner is not None:
            await self._runner.cleanup()
            self._runner = None
