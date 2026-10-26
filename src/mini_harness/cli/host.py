"""`minihns host` 的 HTTP 层：常驻、多会话、token 鉴权（H1 design D1/D4/D5）。

与 `serve` 分开：`serve` 是一进程一会话、会话收尾即退出；host 是服务比会话活得久。
这一层不跑内核，只把 HTTP 请求翻译成对 `HostState` 与会话句柄的操作。
"""

from __future__ import annotations

import argparse
import asyncio
import hmac
import os
import re
import signal
import sys
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import replace
from types import FrameType
from typing import Any

from aiohttp import web

from mini_harness.cli.serve import SERVE_HOSTS
from mini_harness.session.assembly import (
    EXIT_INTERNAL_ERROR,
    EXIT_INVALID_ARGUMENT,
    AssemblyRequest,
    Failure,
)
from mini_harness.session.host import HostState, create_session, submit_message

HOST_TOKEN_ENV = "MINIHNS_HOST_TOKEN"
MIN_TOKEN_LENGTH = 32
DEFAULT_HOST_PORT = 19410
PROTOCOL_VERSION = 1

HEALTH_PATH = "/health"
SESSIONS_PATH = "/sessions"
SESSION_ID_PATTERN = r"[0-9a-f]{32}"
_SESSION_PATH = re.compile(r"^/sessions/([^/]+)")

# 请求体只接受这些设置；`session_dir` 与 `config` 是服务器路径，不接受客户端给
# （H1 spec：日志路径由 id 派生，MUST NOT 接受客户端给路径）。
_SESSION_STRING_FIELDS = frozenset(
    {
        "workspace",
        "provider",
        "fixture",
        "base_url",
        "model",
        "api_key_env",
        "append_system_prompt",
        "sandbox",
        "approval",
    }
)
_SESSION_INT_FIELDS = frozenset({"max_turns", "window", "reserve"})
_SESSION_FIELDS = _SESSION_STRING_FIELDS | _SESSION_INT_FIELDS

_RequestHandler = Callable[[web.Request], Awaitable[web.StreamResponse]]


def _error(status: int, code: str, detail: str) -> web.Response:
    """宿主错误信封：`{"error": {"code": ..., "detail": ...}}`；detail 不含密钥。"""
    return web.json_response({"error": {"code": code, "detail": detail}}, status=status)


def _cors_headers(origin: str) -> dict[str, str]:
    return {
        "Access-Control-Allow-Origin": origin,
        "Access-Control-Allow-Headers": "Authorization, Content-Type",
        "Access-Control-Allow-Methods": "GET, POST, DELETE, OPTIONS",
        "Vary": "Origin",
    }


def _origin_allowed(request: web.Request) -> bool:
    """只放行同源与 `Origin: null`（Electron `file://`）；没有 Origin（curl）也放行。"""
    origin = request.headers.get("Origin")
    if origin is None or origin == "null":
        return True
    return origin == f"http://{request.host}"


class HostServer:
    """一个 aiohttp 应用 + 一个绑定：鉴权与来源在中间件里，路由只关心会话。"""

    def __init__(self, *, host: str, port: int, token: str, state: HostState) -> None:
        self.host = host
        self.port = port
        self._token = token
        self._state = state
        self._application = web.Application(middlewares=[self._guard])
        router = self._application.router
        router.add_get(HEALTH_PATH, self._health)
        router.add_get(SESSIONS_PATH, self._list_sessions)
        router.add_post(SESSIONS_PATH, self._create_session)
        router.add_get(f"{SESSIONS_PATH}/{{session_id}}", self._get_session)
        router.add_post(f"{SESSIONS_PATH}/{{session_id}}/messages", self._post_message)
        self._runner: web.AppRunner | None = None

    def _authorized(self, request: web.Request) -> bool:
        header = request.headers.get("Authorization", "")
        if not header.startswith("Bearer "):
            return False
        return hmac.compare_digest(header[len("Bearer ") :], self._token)

    @web.middleware
    async def _guard(self, request: web.Request, handler: _RequestHandler) -> web.StreamResponse:
        origin = request.headers.get("Origin")
        if not _origin_allowed(request):
            return _error(403, "FORBIDDEN", "来源不在放行名单里")
        if request.method == "OPTIONS":
            response: web.StreamResponse = web.Response(status=204)
        else:
            if request.path != HEALTH_PATH and not self._authorized(request):
                return _error(401, "UNAUTHORIZED", "缺少或错误的 Bearer token")
            match = _SESSION_PATH.match(request.path)
            if match is not None and re.fullmatch(SESSION_ID_PATTERN, match.group(1)) is None:
                return _error(400, "INVALID_ARGUMENT", "session_id 只接受 32 位小写十六进制")
            response = await handler(request)
        if origin is not None:
            response.headers.update(_cors_headers(origin))
        return response

    async def _health(self, request: web.Request) -> web.Response:
        return web.json_response(
            {"protocol": PROTOCOL_VERSION, "sessions": self._state.session_count()}
        )

    async def _list_sessions(self, request: web.Request) -> web.Response:
        return web.json_response(
            {"sessions": [handle.view() for handle in self._state.sessions.values()]}
        )

    async def _create_session(self, request: web.Request) -> web.Response:
        try:
            body = await request.json()
        except (ValueError, TypeError, web.HTTPBadRequest):
            return _error(400, "INVALID_ARGUMENT", "请求体必须是 JSON 对象")
        parsed = _session_request(self._state.defaults, body)
        if isinstance(parsed, str):
            return _error(400, "INVALID_ARGUMENT", parsed)
        created = create_session(self._state, parsed, os.environ)
        if isinstance(created, Failure):
            if created.code == "TOO_MANY_SESSIONS":
                return _error(429, "TOO_MANY_SESSIONS", created.detail)
            if created.exit_code == EXIT_INTERNAL_ERROR:
                return _error(500, "INTERNAL", created.detail)
            return _error(400, "INVALID_ARGUMENT", created.detail)
        return web.json_response(
            {"session_id": created.log.session_id, "cursor": created.last_seq},
            status=201,
        )

    async def _get_session(self, request: web.Request) -> web.Response:
        session_id = request.match_info["session_id"]
        handle = self._state.sessions.get(session_id)
        if handle is None:
            return _error(404, "SESSION_NOT_FOUND", f"没有会话 {session_id}")
        return web.json_response(handle.view())

    async def _post_message(self, request: web.Request) -> web.Response:
        session_id = request.match_info["session_id"]
        handle = self._state.sessions.get(session_id)
        if handle is None:
            return _error(404, "SESSION_NOT_FOUND", f"没有会话 {session_id}")
        try:
            body = await request.json()
        except (ValueError, TypeError, web.HTTPBadRequest):
            return _error(400, "INVALID_ARGUMENT", "请求体必须是 JSON 对象")
        content = body.get("content") if isinstance(body, dict) else None
        if not isinstance(content, str) or not content.strip():
            return _error(400, "INVALID_ARGUMENT", "content 必须是非空字符串")
        accepted = submit_message(handle, content)
        if isinstance(accepted, Failure):
            if accepted.code == "SESSION_BUSY":
                # 消息队列满：spec 的 `/messages` 场景写死 429（DELETE 段中才是 409）。
                return _error(429, "SESSION_BUSY", accepted.detail)
            return _error(404, "SESSION_NOT_FOUND", accepted.detail)
        return web.json_response(
            {
                "segment_id": accepted.segment_id,
                "cursor": handle.last_seq,
                "queued": accepted.queued,
            },
            status=202,
        )

    async def bind(self) -> str | None:
        """绑定并开始接收连接；失败返回 detail（调用方映射成退出码 2）。

        绑定失败不建日志、不发模型请求：它发生在任何 `POST /sessions` 之前。
        """
        runner = web.AppRunner(self._application)
        try:
            await runner.setup()
            await web.TCPSite(runner, self.host, self.port).start()
        except OSError as error:
            await runner.cleanup()
            return str(error)
        self._runner = runner
        return None

    async def run(self, stop: asyncio.Event) -> None:
        """常驻：直到进程收到停止信号。"""
        await stop.wait()

    async def close(self) -> None:
        if self._runner is not None:
            await self._runner.cleanup()
            self._runner = None


def _session_request(defaults: AssemblyRequest, body: object) -> AssemblyRequest | str:
    """请求体覆盖服务器默认设置；不认识的键与错类型都是 INVALID_ARGUMENT 的 detail。"""
    if not isinstance(body, dict):
        return "请求体必须是 JSON 对象"
    unknown = set(body) - _SESSION_FIELDS
    if unknown:
        return f"请求体里有不认识的设置：{' / '.join(sorted(str(key) for key in unknown))}"
    for key, value in body.items():
        if key in _SESSION_STRING_FIELDS and not isinstance(value, str):
            return f"设置 {key} 必须是字符串"
        if key in _SESSION_INT_FIELDS and (not isinstance(value, int) or isinstance(value, bool)):
            return f"设置 {key} 必须是整数"
    return replace(defaults, **body)


def _request_defaults(args: argparse.Namespace) -> AssemblyRequest:
    """服务器级默认设置：`POST /sessions` 的请求体只覆盖它给了的那几项。"""
    return AssemblyRequest(
        workspace=args.workspace,
        config=args.config,
        session_dir=args.session_dir,
        provider=args.provider,
        fixture=args.fixture,
        base_url=args.base_url,
        model=args.model,
        api_key_env=args.api_key_env,
        max_turns=args.max_turns,
        window=args.window,
        reserve=args.reserve,
        append_system_prompt=args.append_system_prompt,
        sandbox=args.sandbox,
        approval=None,
        auto_approve=False,
    )


def _report_failure(code: str, detail: str, exit_code: int) -> int:
    sys.stderr.write(f"{code}: {detail}\n" if detail else f"{code}\n")
    return exit_code


def _validate_startup(args: argparse.Namespace) -> str | None:
    port = args.port
    if not isinstance(port, int) or port < 1 or port > 65535:
        return f"--port 只接受 1 至 65535 的整数，收到 {port}"
    host = args.host
    if host not in SERVE_HOSTS:
        return f"--host 只接受 {' / '.join(SERVE_HOSTS)}，收到 {host}"
    return None


def _stop_handler(
    stop: asyncio.Event, loop: asyncio.AbstractEventLoop
) -> Callable[[int, FrameType | None], None]:
    """信号处理器只调度，不直接动 asyncio 对象（与 CLI 的 Ctrl-C 同一条规矩）。"""

    def handle(signum: int, frame: FrameType | None) -> None:
        loop.call_soon_threadsafe(stop.set)

    return handle


def _install_stop_handlers(stop: asyncio.Event, loop: asyncio.AbstractEventLoop) -> dict[int, Any]:
    """SIGINT / SIGTERM / SIGBREAK 都塌成同一个停止事件；返回旧处理器以便还原。"""
    previous: dict[int, Any] = {}
    handler = _stop_handler(stop, loop)
    for name in ("SIGINT", "SIGTERM", "SIGBREAK"):
        value = getattr(signal, name, None)
        if isinstance(value, int):
            previous[value] = signal.getsignal(value)
            signal.signal(value, handler)
    return previous


def _restore_stop_handlers(previous: Mapping[int, Any]) -> None:
    for signum, handler in previous.items():
        signal.signal(signum, handler)


async def _serve(args: argparse.Namespace, token: str) -> int:
    state = HostState(
        defaults=_request_defaults(args),
        allow_danger_full_access=args.allow_danger_full_access,
        allow_auto_approval=args.allow_auto_approval,
    )
    server = HostServer(
        host=args.host,
        port=args.port,
        token=token,
        state=state,
    )
    failure = await server.bind()
    if failure is not None:
        return _report_failure(
            "INVALID_ARGUMENT",
            f"--host {server.host} --port {server.port} 绑定失败：{failure}",
            EXIT_INVALID_ARGUMENT,
        )
    sys.stderr.write(f"host 监听 http://{server.host}:{server.port}\n")
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    previous = _install_stop_handlers(stop, loop)
    try:
        await server.run(stop)
    finally:
        _restore_stop_handlers(previous)
        await server.close()
    return 0


def host_main(args: argparse.Namespace, environ: Mapping[str, str] | None = None) -> int:
    """`minihns host --http` 的入口：token 缺失或过短在绑定之前就退出 2，不建日志。"""
    source = os.environ if environ is None else environ
    token = source.get(HOST_TOKEN_ENV)
    if token is None or len(token) < MIN_TOKEN_LENGTH:
        return _report_failure(
            "INVALID_ARGUMENT",
            f"{HOST_TOKEN_ENV} 未设置或短于 {MIN_TOKEN_LENGTH} 字符",
            EXIT_INVALID_ARGUMENT,
        )
    invalid = _validate_startup(args)
    if invalid is not None:
        return _report_failure("INVALID_ARGUMENT", invalid, EXIT_INVALID_ARGUMENT)
    return asyncio.run(_serve(args, token))
