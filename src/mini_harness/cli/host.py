"""`minihns host` 的 HTTP 层：常驻、多会话、token 鉴权（H1 design D1/D4/D5）。

与 `serve` 分开：`serve` 是一进程一会话、会话收尾即退出；host 是服务比会话活得久。
这一层不跑内核，只把 HTTP 请求翻译成对 `HostState` 与会话句柄的操作。
"""

from __future__ import annotations

import argparse
import asyncio
import hmac
import json
import os
import re
import signal
import sys
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import replace
from types import FrameType
from typing import Any

from aiohttp import web

from mini_harness.cli.serve import SERVE_HOSTS, sse_frame
from mini_harness.events import LogReadFailure, LogTail, read_events
from mini_harness.events.fold import fold
from mini_harness.session.assembly import (
    EXIT_INVALID_ARGUMENT,
    AssemblyRequest,
    Failure,
    request_from_args,
)
from mini_harness.session.host import (
    HostState,
    cancel_session,
    close_session,
    create_session,
    resolve_approval,
    shutdown,
    submit_message,
)

HOST_TOKEN_ENV = "MINIHNS_HOST_TOKEN"
MIN_TOKEN_LENGTH = 32
DEFAULT_HOST_PORT = 19410
PROTOCOL_VERSION = 1

HEALTH_PATH = "/health"
SESSIONS_PATH = "/sessions"
SESSION_ID_PATTERN = r"[0-9a-f]{32}"
_SESSION_PATH = re.compile(r"^/sessions/([^/]+)")
_CURSOR_DIGITS = re.compile(r"[0-9]+")
# 事件流跟日志的方式与 `serve` 同一条：轮询偏移（design D8）。
EVENTS_POLL_SECONDS = 0.02
NO_CURSOR = -1

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


# 宿主层只读 `Failure.code`，不读 `exit_code`（那是 CLI 的映射）。
_FAILURE_TABLE: dict[str, tuple[int, str]] = {
    "TOO_MANY_SESSIONS": (429, "TOO_MANY_SESSIONS"),
    "SESSION_BUSY": (409, "SESSION_BUSY"),
    "SESSION_NOT_FOUND": (404, "SESSION_NOT_FOUND"),
    "LOG_WRITE_FAILED": (500, "INTERNAL"),
    "INTERNAL": (500, "INTERNAL"),
}


def _failure_response(failure: Failure) -> web.Response:
    status, code = _FAILURE_TABLE.get(failure.code, (400, "INVALID_ARGUMENT"))
    return _error(status, code, failure.detail)


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


def _cursor(request: web.Request) -> int | None:
    """`?from=` 覆盖 `Last-Event-ID`；没有游标时从第一条开始。非整数是 `None`（调用方回 400）。"""
    raw = request.query.get("from")
    if raw is None:
        raw = request.headers.get("Last-Event-ID")
    if raw is None:
        return NO_CURSOR
    if _CURSOR_DIGITS.fullmatch(raw) is None:
        return None
    return int(raw)


def _snapshot_frame(payload: dict[str, object]) -> bytes:
    return f"event: snapshot\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n".encode()


def _delta_frame(payload: dict[str, object]) -> bytes:
    """ephemeral 帧：不带 `id`，不参与 `Last-Event-ID`，也不落日志。"""
    return f"event: model/delta\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n".encode()


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
        router.add_post(f"{SESSIONS_PATH}/{{session_id}}/cancel", self._cancel_session)
        router.add_delete(f"{SESSIONS_PATH}/{{session_id}}", self._delete_session)
        router.add_post(
            f"{SESSIONS_PATH}/{{session_id}}/approvals/{{tool_call_id}}",
            self._post_approval,
        )
        router.add_get(f"{SESSIONS_PATH}/{{session_id}}/events", self._events)
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
        if origin is not None and not response.prepared:
            response.headers.update(_cors_headers(origin))
        return response

    async def _health(self, request: web.Request) -> web.Response:
        return web.json_response(
            {
                "protocol": PROTOCOL_VERSION,
                "sessions": self._state.session_count(),
                "features": ["delta"],
            }
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
        if isinstance(parsed, Failure):
            return _failure_response(parsed)
        created = create_session(self._state, parsed, os.environ)
        if isinstance(created, Failure):
            return _failure_response(created)
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

    async def _cancel_session(self, request: web.Request) -> web.Response:
        session_id = request.match_info["session_id"]
        handle = self._state.sessions.get(session_id)
        if handle is None:
            return _error(404, "SESSION_NOT_FOUND", f"没有会话 {session_id}")
        if cancel_session(handle):
            return web.json_response({"cancelled": True}, status=202)
        return web.json_response({"cancelled": False}, status=200)

    async def _delete_session(self, request: web.Request) -> web.Response:
        session_id = request.match_info["session_id"]
        handle = self._state.sessions.get(session_id)
        if handle is None:
            return _error(404, "SESSION_NOT_FOUND", f"没有会话 {session_id}")
        failure = close_session(handle)
        if failure is not None:
            return _failure_response(failure)
        return web.json_response(handle.view(), status=200)

    async def _post_approval(self, request: web.Request) -> web.Response:
        session_id = request.match_info["session_id"]
        handle = self._state.sessions.get(session_id)
        if handle is None:
            return _error(404, "SESSION_NOT_FOUND", f"没有会话 {session_id}")
        try:
            body = await request.json()
        except (ValueError, TypeError, web.HTTPBadRequest):
            return _error(400, "INVALID_ARGUMENT", "请求体必须是 JSON 对象")
        decision = body.get("decision") if isinstance(body, dict) else None
        if decision not in {"approve", "deny"}:
            return _error(400, "INVALID_ARGUMENT", 'decision 只接受 "approve" 或 "deny"')
        tool_call_id = request.match_info["tool_call_id"]
        if not resolve_approval(handle, tool_call_id, approve=decision == "approve"):
            return _error(404, "SESSION_NOT_FOUND", f"没有待决的审批：{tool_call_id}")
        return web.json_response({"resolved": True}, status=200)

    async def _events(self, request: web.Request) -> web.StreamResponse:
        session_id = request.match_info["session_id"]
        handle = self._state.sessions.get(session_id)
        if handle is None:
            return _error(404, "SESSION_NOT_FOUND", f"没有会话 {session_id}")
        cursor = _cursor(request)
        if cursor is None:
            return _error(400, "INVALID_ARGUMENT", "游标必须是非负整数")
        snapshot = request.query.get("snapshot") == "1"
        response = web.StreamResponse(headers={"Content-Type": "text/event-stream"})
        origin = request.headers.get("Origin")
        if origin is not None:
            # 中间件在 handler 返回之后才加头，而这里已经 prepare 并发流了；SSE 的 CORS
            # 头必须在 prepare 之前就位，否则浏览器读不到。
            response.headers.update(_cors_headers(origin))
        after = cursor
        if snapshot:
            records = read_events(handle.log.path)
            if isinstance(records, LogReadFailure):
                return _error(500, "INTERNAL", records.detail)
            last_seq = records[-1].seq if records else -1
            context = fold(records)
            await response.prepare(request)
            await response.write(
                _snapshot_frame(
                    {
                        "session_id": session_id,
                        "status": handle.status,
                        "last_seq": last_seq,
                        "messages": [
                            message.model_dump(mode="json") for message in context.messages
                        ],
                    }
                )
            )
            after = last_seq
        else:
            await response.prepare(request)
        tail = LogTail(handle.log.path, after=after)
        deltas = handle.subscribe_deltas()
        try:
            while True:
                transport = request.transport
                if transport is None or transport.is_closing():
                    return response
                records = tail.read_new()
                if isinstance(records, LogReadFailure):
                    return response
                try:
                    # 先把这一批 durable 记录按顺序写出去；遇到 `model/response` 时
                    # 先排空它之前的 delta——provider 在落 response 前已经发过所有片段。
                    for record in records:
                        if record.type == "model/response":
                            while not deltas.empty():
                                await response.write(_delta_frame(deltas.get_nowait()))
                        await response.write(sse_frame(record))
                except ConnectionResetError:
                    return response
                await asyncio.sleep(EVENTS_POLL_SECONDS)
        finally:
            handle.unsubscribe_deltas(deltas)

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

    async def close(self) -> None:
        if self._runner is not None:
            await self._runner.cleanup()
            self._runner = None


def _session_request(defaults: AssemblyRequest, body: object) -> AssemblyRequest | Failure:
    """请求体覆盖服务器默认设置；不认识的键与错类型都是 INVALID_ARGUMENT 的 detail。"""

    def bad(detail: str) -> Failure:
        return Failure("INVALID_ARGUMENT", detail, EXIT_INVALID_ARGUMENT)

    if not isinstance(body, dict):
        return bad("请求体必须是 JSON 对象")
    unknown = set(body) - _SESSION_FIELDS
    if unknown:
        return bad(f"请求体里有不认识的设置：{' / '.join(sorted(str(key) for key in unknown))}")
    for key, value in body.items():
        if key in _SESSION_STRING_FIELDS and not isinstance(value, str):
            return bad(f"设置 {key} 必须是字符串")
        if key in _SESSION_INT_FIELDS and (not isinstance(value, int) or isinstance(value, bool)):
            return bad(f"设置 {key} 必须是整数")
    return replace(defaults, **body)


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
        defaults=request_from_args(args),
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
        await stop.wait()
    finally:
        _restore_stop_handlers(previous)
        await server.close()
        await shutdown(state)
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
