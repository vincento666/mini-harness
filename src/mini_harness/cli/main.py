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
from pathlib import Path
from types import FrameType
from typing import Any, NoReturn

from mini_harness.config import (
    ConfigFailure,
    build_registry,
    discover_config,
    layer_settings,
    load_config,
)
from mini_harness.events import EventLog, LogReadFailure, LogWriteFailure, read_events
from mini_harness.events.fold import assembled_payload, fold
from mini_harness.loop import (
    APPROVAL_MODES,
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
    SessionSettings,
    run_session,
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


def build_parser() -> argparse.ArgumentParser:
    """构造顶层解析器。"""
    parser = _ArgumentParser(prog="minihns", description="mini-harness：headless agent harness")
    subcommands = parser.add_subparsers(dest="command", required=True)

    run = subcommands.add_parser("run", help="跑完一个 session")
    # 可配字段的 flag 默认值一律是 `None` 哨兵：内置默认只住在 `loop/settings.py`（design D2）。
    run.add_argument("-p", "--prompt", default=None)
    run.add_argument("--config", default=None)
    run.add_argument("--workspace", default=None)
    run.add_argument("--session-dir", default=None)
    run.add_argument("--provider", default=None)
    run.add_argument("--fixture", default=None)
    run.add_argument("--base-url", default=None)
    run.add_argument("--model", default=None)
    run.add_argument("--api-key-env", default=None)
    run.add_argument("--max-turns", type=int, default=None)
    run.add_argument("--window", type=int, default=None)
    run.add_argument("--reserve", type=int, default=None)
    run.add_argument("--append-system-prompt", default=None)
    run.add_argument("--events", choices=("jsonl",), default=None)
    run.add_argument("--sandbox", choices=SANDBOX_LEVELS, default=None)
    run.add_argument("--yes", action="store_true")

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
            provider=provider,
            log=log,
            registry=registry,
            settings=settings,
            cancel=cancel,
        )
    finally:
        signal.signal(signal.SIGINT, previous)


def _run(args: argparse.Namespace) -> int:
    prompt: str | None = args.prompt
    fixture: str | None = args.fixture

    if prompt is None or prompt == "":
        return _report_failure("INVALID_ARGUMENT", "-p/--prompt 必填且非空", EXIT_INVALID_ARGUMENT)
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
    outcome = asyncio.run(
        _await_session(
            prompt=prompt, provider=provider, settings=settings, log=log, registry=registry
        )
    )

    exit_code = exit_code_for(outcome)
    if outcome.stop_reason not in STOP_REASONS:
        return _report_failure(
            outcome.failure_code or outcome.stop_reason, outcome.detail, exit_code
        )

    if args.events == "jsonl":
        for line in log.path.read_text(encoding="utf-8").splitlines():
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

    assembled = [
        (index, record)
        for index, record in enumerate(records)
        if record.type == "context/assembled"
    ]
    if not assembled:
        # 溢出与取消都能在第一次装配之前就把回合收掉，那份日志是合法的：
        # 没有可重算的点不等于重算不一致，但要说明它，不能冒充「一条都验过」。
        print("no_context_assembled: 这份日志没有装配点")

    for index, record in assembled:
        preceding_turn = next(
            (item for item in reversed(records[:index]) if item.type == "turn/start"),
            None,
        )
        turn_id = "" if preceding_turn is None else str(preceding_turn.payload.get("turn_id", ""))
        # 折叠入参只从该点之前的事实派生：工具块与追加段都在 `session/start` 里，
        # 回放侧不存在「进程内注册表」这个第二真源。
        recomputed = fold(records[:index])
        if assembled_payload(turn_id, recomputed) != record.payload:
            return _report_failure(
                "REPLAY_MISMATCH",
                f"error/replay seq={record.seq} 的 context/assembled 与其前缀的重算不一致",
                EXIT_INTERNAL_ERROR,
            )
        print(f"verified seq={record.seq}: OK")

    for record in records:
        if record.type == "turn/end":
            print(f"turn {record.payload['turn_id']}: {record.payload['stop_reason']}")
    if assembled:
        print("final_context: " + json.dumps(assembled[-1][1].payload, ensure_ascii=False))
    return EXIT_OK


def _reconfigure_streams() -> None:
    for stream in (sys.stdout, sys.stderr):
        if isinstance(stream, io.TextIOWrapper):
            stream.reconfigure(encoding="utf-8")


def main(argv: Sequence[str] | None = None) -> int:
    """解析参数并返回退出码。"""
    _reconfigure_streams()
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "run":
        return _run(args)
    return _replay(args)


if __name__ == "__main__":
    sys.exit(main())
