"""`minihns serve` 的 HTTP 层：绑定、事件流路由、断开处理（design D7）。

这一层只读那份日志，不写任何东西进会话：客户端断开、慢读、从未连接都不是取消信号。
"""

from __future__ import annotations

from dataclasses import dataclass

from aiohttp import web

# 默认监听地址。19387 是 DSH 的 desktop profile 在这台机器上的端口
# （`dsh-desktop-host/lib/index.js:231-235`），mini 故意错开，免得两个 harness 抢同一个端口。
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 19400

# host 的词表照 DSH 的 `dsh-host-webserver`：`host: union("127.0.0.1","0.0.0.0")`。
SERVE_HOSTS: tuple[str, ...] = ("127.0.0.1", "0.0.0.0")


@dataclass(frozen=True)
class BindFailure:
    """绑定失败：它是 session 开始之前的参数错误，不是运行期故障。"""

    host: str
    port: int
    detail: str


class ServeServer:
    """一个进程一个会话：HTTP 层是那份日志的实时投影。"""

    def __init__(self, *, host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> None:
        self.host = host
        self.port = port
        self._application = web.Application()
        self._runner: web.AppRunner | None = None

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

    async def close(self) -> None:
        """结束监听。会话收尾就是进程退出，所以监听跟着一起结束。"""
        if self._runner is not None:
            await self._runner.cleanup()
            self._runner = None
