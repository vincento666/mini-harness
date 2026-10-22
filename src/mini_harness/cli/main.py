"""`minihns` 入口：解析参数、跑内核、把结果映射成退出码。"""

from __future__ import annotations

import argparse
import asyncio
import io
import json
import os
import signal
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from types import FrameType
from typing import Any, NoReturn

from mini_harness.cli.serve import DEFAULT_HOST, DEFAULT_PORT, SERVE_HOSTS, BindFailure, ServeServer
from mini_harness.config import (
    ConfigFailure,
    build_registry,
    discover_config,
    layer_settings,
    load_config,
)
from mini_harness.context.budget import CONTEXT_HEADROOM_TOKENS
from mini_harness.events import EventLog, LogReadFailure, LogWriteFailure, read_events
from mini_harness.events.fold import assembled_payload, assembly_points, fold
from mini_harness.loop import (
    APPROVAL_MODES,
    ENTRY_CHAT,
    ENTRY_RUN,
    ENTRY_SERVE,
    SANDBOX_LEVELS,
    STOP_ABORTED,
    STOP_CONTEXT_WINDOW_EXCEEDED,
    STOP_FENCE_DENIED,
    STOP_MAX_TURNS,
    STOP_MODEL_COMPLETED,
    STOP_PROVIDER_ERROR,
    STOP_REASONS,
    STOP_TOOL_CALLS,
    ProviderEndpoint,
    RunOutcome,
    SessionEntry,
    SessionEnv,
    SessionSettings,
    end_session,
    run_session,
    run_turn_segment,
    start_session,
)
from mini_harness.provider import FixtureLoadFailure, load_fixture_provider
from mini_harness.provider.contract import Provider
from mini_harness.provider.openai_compat import OpenAICompatProvider, validate_base_url
from mini_harness.tools import ToolRegistry

EXIT_OK = 0
EXIT_INTERNAL_ERROR = 1
EXIT_INVALID_ARGUMENT = 2
EXIT_FENCE_DENIED = 3
EXIT_CONTEXT_WINDOW_EXCEEDED = 4
EXIT_ABORTED = 5

STOP_REASONS_TO_EXIT_CODES: dict[str, int] = {
    STOP_MODEL_COMPLETED: EXIT_OK,
    STOP_TOOL_CALLS: EXIT_OK,
    STOP_MAX_TURNS: EXIT_OK,
    STOP_PROVIDER_ERROR: EXIT_INTERNAL_ERROR,
    STOP_FENCE_DENIED: EXIT_FENCE_DENIED,
    STOP_CONTEXT_WINDOW_EXCEEDED: EXIT_CONTEXT_WINDOW_EXCEEDED,
    STOP_ABORTED: EXIT_ABORTED,
}


def exit_code_for(outcome: RunOutcome) -> int:
    """内核结果到退出码：词表外的 `stop_reason` 是日志层失败，一律 1。"""
    if outcome.stop_reason not in STOP_REASONS:
        return EXIT_INTERNAL_ERROR
    return STOP_REASONS_TO_EXIT_CODES[outcome.stop_reason]


class _ArgumentParser(argparse.ArgumentParser):
    """参数错误统一成 `INVALID_ARGUMENT` + 退出码 2。"""

    def error(self, message: str) -> NoReturn:
        self.print_usage(sys.stderr)
        sys.stderr.write(f"INVALID_ARGUMENT: {message}\n")
        raise SystemExit(EXIT_INVALID_ARGUMENT)


def _add_shared_flags(parser: argparse.ArgumentParser) -> None:
    """`run` 与 `chat` 共用同一份 flag。

    可配字段的 flag 默认值一律是 `None` 哨兵：内置默认只住在 `loop/settings.py`（design D2）。
    """
    parser.add_argument("--config", default=None)
    parser.add_argument("--workspace", default=None)
    parser.add_argument("--session-dir", default=None)
    parser.add_argument("--provider", default=None)
    parser.add_argument("--fixture", default=None)
    parser.add_argument("--base-url", default=None)
    parser.add_argument("--model", default=None)
    parser.add_argument("--api-key-env", default=None)
    parser.add_argument("--max-turns", type=int, default=None)
    parser.add_argument("--window", type=int, default=None)
    parser.add_argument("--reserve", type=int, default=None)
    parser.add_argument("--append-system-prompt", default=None)
    parser.add_argument("--sandbox", choices=SANDBOX_LEVELS, default=None)
    parser.add_argument("--yes", action="store_true")


def build_parser() -> argparse.ArgumentParser:
    """构造顶层解析器。"""
    parser = _ArgumentParser(prog="minihns", description="mini-harness：headless agent harness")
    subcommands = parser.add_subparsers(dest="command", required=True)

    shared = _ArgumentParser(add_help=False)
    _add_shared_flags(shared)

    run = subcommands.add_parser("run", help="跑完一个 session", parents=[shared])
    run.add_argument("-p", "--prompt", default=None)
    run.add_argument("--events", choices=("jsonl",), default=None)

    # `serve` 的 flag 表是 run 的表减去 `--events`、加上 `--host` 与 `--port`（event-stream 规格）；
    # M7 只有 HTTP 这一种传输，`--http` 是它的选择器。
    serve = subcommands.add_parser(
        "serve", help="跑一个会话并把日志作为事件流输出", parents=[shared]
    )
    serve.add_argument("--http", action="store_true", required=True)
    serve.add_argument("-p", "--prompt", default=None)
    serve.add_argument("--port", type=int, default=DEFAULT_PORT)
    serve.add_argument("--host", default=DEFAULT_HOST)

    # `chat` 没有 `-p/--prompt`，也没有 `--events`：一个会话的人话从 stdin 按行进来，
    # stdout 上只有模型回复正文与提示符（chat-repl 规格）。
    subcommands.add_parser("chat", help="跑一个连续会话的 REPL", parents=[shared])

    replay = subcommands.add_parser("replay", help="重放一个 session 的日志")
    replay.add_argument("session_id")
    replay.add_argument("--session-dir", default=None)
    return parser


def _report_failure(code: str, detail: str, exit_code: int) -> int:
    sys.stderr.write(f"{code}: {detail}\n")
    return exit_code


def _session_dir(value: str | None) -> Path:
    if value is not None:
        return Path(value)
    return Path.cwd() / "sessions"


def sigint_handler(cancel: asyncio.Event) -> Callable[[int, FrameType | None], None]:
    """Ctrl-C 的处理器：只调度，不直接动 asyncio 对象。"""
    loop = asyncio.get_running_loop()

    def handle(signum: int, frame: FrameType | None) -> None:
        loop.call_soon_threadsafe(cancel.set)

    return handle


async def _await_session(
    *,
    prompt: str,
    entry: SessionEntry,
    provider: Provider,
    settings: SessionSettings,
    log: EventLog,
    registry: ToolRegistry,
) -> RunOutcome:
    """装好 Ctrl-C 处理器再跑内核：Ctrl-C 是取消，不是崩溃。"""
    cancel = asyncio.Event()
    previous = signal.getsignal(signal.SIGINT)
    signal.signal(signal.SIGINT, sigint_handler(cancel))
    try:
        return await run_session(
            prompt=prompt,
            entry=entry,
            provider=provider,
            log=log,
            registry=registry,
            settings=settings,
            cancel=cancel,
        )
    finally:
        signal.signal(signal.SIGINT, previous)


@dataclass(frozen=True)
class _Prepared:
    """装配好的会话材料：`run` 与 `chat` 共用同一条装配路（design D1）。"""

    provider: Provider
    settings: SessionSettings
    log: EventLog
    registry: ToolRegistry


def _prepare_or_fail(args: argparse.Namespace) -> _Prepared | int:
    """参数校验 → 配置层叠 → 装配 → 开日志：`run` 与 `chat` 走同一条路。

    失败当场打成 stderr 并返回退出码；所有失败都在 session 日志创建之前（cli 规格）。
    """
    fixture: str | None = args.fixture
    # 配置文件发现用的工作区是「`--workspace` 或当前目录」这一层，不来自配置文件（design D7）。
    discovery_workspace = Path(args.workspace) if args.workspace is not None else Path.cwd()
    config: dict[str, Any] = {}
    config_path = discover_config(discovery_workspace, args.config)
    if config_path is not None:
        loaded_config = load_config(config_path)
        if isinstance(loaded_config, ConfigFailure):
            # 配置层失败与参数错误同形：退出码 2，且在日志创建之前。
            return _report_failure("INVALID_ARGUMENT", loaded_config.detail, EXIT_INVALID_ARGUMENT)
        config = loaded_config
    # 三层塌成一份有效设置：之后的校验与装配只认这一份。
    layered = layer_settings(args, config)
    max_turns = layered.max_turns
    provider_name = layered.provider
    if max_turns < 1:
        return _report_failure(
            "INVALID_ARGUMENT", f"--max-turns 至少为 1，收到 {max_turns}", EXIT_INVALID_ARGUMENT
        )
    if provider_name not in ("mock", "openai"):
        return _report_failure(
            "UNKNOWN_PROVIDER",
            f"--provider 只接受 mock 或 openai，收到 {provider_name}",
            EXIT_INVALID_ARGUMENT,
        )
    # 围栏两条轴的取值词表由围栏规定：配置文件写错档位不是「运行期再说」，是参数错误。
    for key, level, allowed in (
        ("sandbox", layered.sandbox, SANDBOX_LEVELS),
        ("approval", layered.approval, APPROVAL_MODES),
    ):
        if level not in allowed:
            return _report_failure(
                "INVALID_ARGUMENT",
                f"{key} 只接受 {' / '.join(allowed)}，收到 {level}",
                EXIT_INVALID_ARGUMENT,
            )
    # 窗口预算的两个参数在 session 开始之前判掉：非法取值不产生日志（context-budget 规格）。
    for flag, value in (("--window", layered.window), ("--reserve", layered.reserve)):
        if value < 1:
            return _report_failure(
                "INVALID_ARGUMENT", f"{flag} 至少为 1，收到 {value}", EXIT_INVALID_ARGUMENT
            )
    # 窗口减去预留与 headroom 之后没有剩余压力预算时触发线是 0：任何非空上下文都越线、
    # 压缩救不动。照 DSH，这是配置解析期的错误，不是运行期才发现的溢出（ADR-0019）。
    if layered.window - layered.reserve - CONTEXT_HEADROOM_TOKENS <= 0:
        return _report_failure(
            "INVALID_ARGUMENT",
            (
                f"--window {layered.window} 减去 --reserve {layered.reserve} 与余量 "
                f"{CONTEXT_HEADROOM_TOKENS} 之后没有剩余压力预算"
            ),
            EXIT_INVALID_ARGUMENT,
        )

    # 工具表从装配来：内置六定义按配置的白名单筛，未知名与别的配置失败同形。
    registry = build_registry(layered.tools)
    if isinstance(registry, ConfigFailure):
        return _report_failure("INVALID_ARGUMENT", registry.detail, EXIT_INVALID_ARGUMENT)

    provider: Provider
    endpoint: ProviderEndpoint | None = None
    if provider_name == "openai":
        if fixture is not None:
            return _report_failure(
                "INVALID_ARGUMENT",
                "--provider openai 不使用 --fixture",
                EXIT_INVALID_ARGUMENT,
            )
        # 密钥只从 --api-key-env 指定的环境变量读：它不进 argv、不进日志、不进 payload。
        invalid = validate_base_url(layered.base_url)
        if invalid is not None:
            return _report_failure("INVALID_ARGUMENT", invalid, EXIT_INVALID_ARGUMENT)
        # 端点三条在这里塌成一个对象：payload 那三个字段由它派生，不再各判一遍。
        endpoint = ProviderEndpoint(
            base_url=layered.base_url,
            model=layered.model,
            api_key_env=layered.api_key_env,
        )
        # 密钥是装配的必需项：未设或空串都在 session 开始之前当场失败，一个请求都不发。
        api_key = os.environ.get(endpoint.api_key_env)
        if not api_key:
            return _report_failure(
                "INVALID_ARGUMENT",
                f"环境变量 {endpoint.api_key_env} 未设置或为空：--provider openai 需要密钥",
                EXIT_INVALID_ARGUMENT,
            )
        provider = OpenAICompatProvider(
            base_url=endpoint.base_url,
            model=endpoint.model,
            api_key=api_key,
        )
    else:
        if fixture is None:
            return _report_failure(
                "INVALID_ARGUMENT",
                "--provider mock 需要 --fixture 指向 JSON 数组",
                EXIT_INVALID_ARGUMENT,
            )
        loaded = load_fixture_provider(Path(fixture))
        if isinstance(loaded, FixtureLoadFailure):
            return _report_failure(loaded.code, loaded.detail, EXIT_INVALID_ARGUMENT)
        provider = loaded

    log = EventLog.start(_session_dir(layered.session_dir))
    if isinstance(log, LogWriteFailure):
        return _report_failure(log.code, log.detail, EXIT_INTERNAL_ERROR)

    settings = SessionSettings(
        workspace=Path(layered.workspace) if layered.workspace is not None else Path.cwd(),
        provider_name=provider_name,
        max_turns=max_turns,
        sandbox=layered.sandbox,
        approval="auto" if args.yes else layered.approval,
        append_system_prompt=layered.append_system_prompt,
        window=layered.window,
        reserve=layered.reserve,
        endpoint=endpoint,
    )
    return _Prepared(provider=provider, settings=settings, log=log, registry=registry)


def _run(args: argparse.Namespace) -> int:
    """一次性 run：装配、跑内核、把结果映射成退出码。"""
    prompt: str | None = args.prompt
    if prompt is None or prompt == "":
        return _report_failure("INVALID_ARGUMENT", "-p/--prompt 必填且非空", EXIT_INVALID_ARGUMENT)
    prepared = _prepare_or_fail(args)
    if isinstance(prepared, int):
        return prepared

    outcome = asyncio.run(
        _await_session(
            prompt=prompt,
            entry=ENTRY_RUN,
            provider=prepared.provider,
            settings=prepared.settings,
            log=prepared.log,
            registry=prepared.registry,
        )
    )

    exit_code = exit_code_for(outcome)
    if outcome.stop_reason not in STOP_REASONS:
        return _report_failure(
            outcome.failure_code or outcome.stop_reason, outcome.detail, exit_code
        )

    if args.events == "jsonl":
        for line in prepared.log.path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                print(line)
    else:
        print(outcome.session_id)

    if exit_code != EXIT_OK:
        # 非 0 退出必须在 stderr 说清楚：stdout 归会话 id 与日志逐行输出。
        return _report_failure(
            outcome.failure_code or outcome.stop_reason, outcome.detail, exit_code
        )
    return exit_code


def _serve(args: argparse.Namespace) -> int:
    """一次性 serve：绑定、装配、跑会话、收尾即退出。"""
    prompt: str | None = args.prompt
    if prompt is None or prompt == "":
        return _report_failure("INVALID_ARGUMENT", "-p/--prompt 必填且非空", EXIT_INVALID_ARGUMENT)
    # host 与 port 的词表只在 CLI 上（design D4）：越界是参数错误，不是「绑定时再说」。
    port: int = args.port
    if port < 1 or port > 65535:
        return _report_failure(
            "INVALID_ARGUMENT",
            f"--port 只接受 1 至 65535 的整数，收到 {port}",
            EXIT_INVALID_ARGUMENT,
        )
    host: str = args.host
    if host not in SERVE_HOSTS:
        return _report_failure(
            "INVALID_ARGUMENT",
            f"--host 只接受 {' / '.join(SERVE_HOSTS)}，收到 {host}",
            EXIT_INVALID_ARGUMENT,
        )
    return asyncio.run(_serve_session(args=args, prompt=prompt))


async def _serve_session(*, args: argparse.Namespace, prompt: str) -> int:
    """绑定先于开日志（design D3）：绑定失败不留下 session 日志，也不发模型请求。"""
    server = ServeServer(host=args.host, port=args.port)
    failure = await server.bind()
    if isinstance(failure, BindFailure):
        return _report_failure(
            "INVALID_ARGUMENT",
            f"--host {failure.host} --port {failure.port} 绑定失败：{failure.detail}",
            EXIT_INVALID_ARGUMENT,
        )

    prepared = _prepare_or_fail(args)
    if isinstance(prepared, int):
        await server.close()
        return prepared

    server.attach(prepared.log.path)

    try:
        outcome = await _await_session(
            prompt=prompt,
            entry=ENTRY_SERVE,
            provider=prepared.provider,
            settings=prepared.settings,
            log=prepared.log,
            registry=prepared.registry,
        )
    finally:
        # 先让事件流跟到收尾，再结束监听：`cleanup()` 等在跑的处理器返回。
        server.session_finished.set()
        await server.close()

    exit_code = exit_code_for(outcome)
    if outcome.stop_reason not in STOP_REASONS:
        return _report_failure(
            outcome.failure_code or outcome.stop_reason, outcome.detail, exit_code
        )

    print(outcome.session_id)
    if exit_code != EXIT_OK:
        # 非 0 退出必须在 stderr 说清楚：stdout 归 session id。
        return _report_failure(
            outcome.failure_code or outcome.stop_reason, outcome.detail, exit_code
        )
    return exit_code


_CHAT_PROMPT = "> "


@dataclass
class _ChatSignals:
    """Ctrl-C 的落点：段在跑就取消那个段，没有段在跑就结束会话（design D7）。"""

    active: asyncio.Event | None = None


def _chat_sigint_handler(signals: _ChatSignals) -> Callable[[int, FrameType | None], None]:
    def handle(signum: int, frame: FrameType | None) -> None:
        if signals.active is not None:
            # 段在跑：取消当前段，会话继续。
            signals.active.set()
            return
        # 提示符上：没有段在跑，Ctrl-C 与 EOF 同一条路。
        raise KeyboardInterrupt

    return handle


def _print_new_replies(log: EventLog, printed: int) -> int | LogReadFailure:
    """把日志里新增的模型回复正文按发生顺序打到 stdout（design D11）。

    stdout 是日志的一个投影，不是第二真源：读回来打，内核就不需要知道有人在看着。
    带 `purpose` 的那次 `model/response` 是请求级压缩的内部摘要，不是给人的回复，不打。
    """
    events = read_events(log.path)
    if isinstance(events, LogReadFailure):
        return events
    seen = 0
    for event in events:
        if event.type != "model/response" or "purpose" in event.payload:
            continue
        seen += 1
        if seen > printed:
            print(str(event.payload.get("content", "")))
    return seen


async def _chat_session(prepared: _Prepared) -> int:
    """读一行、开一个段、回到提示符；EOF 或提示符上的 Ctrl-C 收尾整个会话。"""
    env = SessionEnv(
        provider=prepared.provider,
        log=prepared.log,
        registry=prepared.registry,
        settings=prepared.settings,
    )
    started = start_session(prompt="", entry=ENTRY_CHAT, env=env)
    if started is not None:
        return _report_failure(
            started.failure_code or started.stop_reason, started.detail, EXIT_INTERNAL_ERROR
        )

    signals = _ChatSignals()
    previous = signal.getsignal(signal.SIGINT)
    signal.signal(signal.SIGINT, _chat_sigint_handler(signals))
    segments = 0
    turn_index = 1
    printed = 0
    try:
        while True:
            print(_CHAT_PROMPT)
            line = sys.stdin.readline()
            if line == "":
                # EOF：会话正常收尾。
                break
            text = line.strip()
            if not text:
                # 空白输入不写记录，也不开段。
                continue
            segments += 1
            cancel = asyncio.Event()
            signals.active = cancel
            try:
                segment = await run_turn_segment(
                    env=env,
                    segment_id=f"s{segments}",
                    first_turn_index=turn_index,
                    cancel=cancel,
                    user_message=text,
                )
            finally:
                signals.active = None
            if segment.stop_reason not in STOP_REASONS:
                # 内核坏了：不再回到提示符，按内部错误收尾。
                return _report_failure(
                    segment.failure_code or segment.stop_reason, segment.detail, EXIT_INTERNAL_ERROR
                )
            turn_index += segment.turns
            replies = _print_new_replies(prepared.log, printed)
            if isinstance(replies, LogReadFailure):
                return _report_failure(replies.code, replies.detail, EXIT_INTERNAL_ERROR)
            printed = replies
    except KeyboardInterrupt:
        # 提示符上的 Ctrl-C：与 EOF 同一条路，写 `session/end`、退出码 0。
        pass
    finally:
        signal.signal(signal.SIGINT, previous)

    ended = end_session(env=env, stop_reason=STOP_MODEL_COMPLETED, turns=turn_index - 1)
    if ended is not None:
        return _report_failure(
            ended.failure_code or ended.stop_reason, ended.detail, EXIT_INTERNAL_ERROR
        )
    return EXIT_OK


def _chat(args: argparse.Namespace) -> int:
    """一个会话的 REPL：装配与 run 同一条路，之后只多「读行」这一件事。"""
    prepared = _prepare_or_fail(args)
    if isinstance(prepared, int):
        return prepared
    return asyncio.run(_chat_session(prepared))


def _replay(args: argparse.Namespace) -> int:
    session_id: str = args.session_id
    session_dir = _session_dir(args.session_dir)
    path = session_dir / f"{session_id}.jsonl"
    if not path.is_file():
        return _report_failure(
            "SESSION_NOT_FOUND", f"找不到 session 日志：{path}", EXIT_INVALID_ARGUMENT
        )

    records = read_events(path)
    if isinstance(records, LogReadFailure):
        return _report_failure(records.code, records.detail, EXIT_INTERNAL_ERROR)

    points = assembly_points(records)
    if not points:
        # 溢出与取消都能在第一次装配之前就把回合收掉，那份日志是合法的：
        # 没有可重算的点不等于重算不一致，但要说明它，不能冒充「一条都验过」。
        print("no_context_assembled: 这份日志没有装配点")

    for point in points:
        # 折叠入参只从该点之前的事实派生：工具块与追加段都在 `session/start` 里，
        # 回放侧不存在「进程内注册表」这个第二真源。
        recomputed = fold(point.prefix)
        if assembled_payload(point.turn_id, recomputed) != point.record.payload:
            return _report_failure(
                "REPLAY_MISMATCH",
                f"error/replay seq={point.record.seq} 的 context/assembled 与其前缀的重算不一致",
                EXIT_INTERNAL_ERROR,
            )
        print(f"verified seq={point.record.seq}: OK")

    for record in records:
        if record.type == "turn/end":
            print(f"turn {record.payload['turn_id']}: {record.payload['stop_reason']}")
    if points:
        print("final_context: " + json.dumps(points[-1].record.payload, ensure_ascii=False))
    return EXIT_OK


def _reconfigure_streams() -> None:
    # stdin 也算：`chat` 按行读人的输入，编码不能看运行环境的脸色。
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        if isinstance(stream, io.TextIOWrapper):
            stream.reconfigure(encoding="utf-8")


def main(argv: Sequence[str] | None = None) -> int:
    """解析参数并返回退出码。"""
    _reconfigure_streams()
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "run":
        return _run(args)
    if args.command == "serve":
        return _serve(args)
    if args.command == "chat":
        return _chat(args)
    return _replay(args)


if __name__ == "__main__":
    sys.exit(main())
