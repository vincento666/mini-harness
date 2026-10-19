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
from typing import NoReturn

from mini_harness.events import EventLog, LogReadFailure, LogWriteFailure, read_events
from mini_harness.events.fold import assembled_payload, fold
from mini_harness.loop import (
    STOP_ABORTED,
    STOP_FENCE_DENIED,
    STOP_MAX_TURNS,
    STOP_MODEL_COMPLETED,
    STOP_PROVIDER_ERROR,
    STOP_REASONS,
    STOP_TOOL_CALLS,
    RunOutcome,
    SessionSettings,
    run_session,
)
from mini_harness.provider import FixtureLoadFailure, load_fixture_provider
from mini_harness.provider.contract import Provider
from mini_harness.provider.openai_compat import OpenAICompatProvider, validate_base_url
from mini_harness.tools import ToolRegistry
from mini_harness.tools.bash_tools import bash_tool_definitions
from mini_harness.tools.file_tools import file_tool_definitions

EXIT_OK = 0
EXIT_INTERNAL_ERROR = 1
EXIT_INVALID_ARGUMENT = 2
EXIT_FENCE_DENIED = 3
EXIT_ABORTED = 5

STOP_REASONS_TO_EXIT_CODES: dict[str, int] = {
    STOP_MODEL_COMPLETED: EXIT_OK,
    STOP_TOOL_CALLS: EXIT_OK,
    STOP_MAX_TURNS: EXIT_OK,
    STOP_PROVIDER_ERROR: EXIT_INTERNAL_ERROR,
    STOP_FENCE_DENIED: EXIT_FENCE_DENIED,
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
    run.add_argument("-p", "--prompt", default=None)
    run.add_argument("--workspace", default=None)
    run.add_argument("--session-dir", default=None)
    run.add_argument("--provider", default="mock")
    run.add_argument("--fixture", default=None)
    run.add_argument("--base-url", default="https://api.deepseek.com")
    run.add_argument("--model", default="deepseek-chat")
    run.add_argument("--api-key-env", default="DEEPSEEK_API_KEY")
    run.add_argument("--max-turns", type=int, default=8)
    run.add_argument("--append-system-prompt", default="")
    run.add_argument("--events", choices=("jsonl",), default=None)
    run.add_argument(
        "--sandbox",
        choices=("read-only", "workspace-write", "danger-full-access"),
        default="workspace-write",
    )
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
            registry=ToolRegistry([*file_tool_definitions(), *bash_tool_definitions()]),
            settings=settings,
            cancel=cancel,
        )
    finally:
        signal.signal(signal.SIGINT, previous)


def _run(args: argparse.Namespace) -> int:
    prompt: str | None = args.prompt
    max_turns: int = args.max_turns
    provider_name: str = args.provider
    fixture: str | None = args.fixture

    if prompt is None or prompt == "":
        return _report_failure("INVALID_ARGUMENT", "-p/--prompt 必填且非空", EXIT_INVALID_ARGUMENT)
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

    provider: Provider
    if provider_name == "openai":
        if fixture is not None:
            return _report_failure(
                "INVALID_ARGUMENT",
                "--provider openai 不使用 --fixture",
                EXIT_INVALID_ARGUMENT,
            )
        # 密钥只从 --api-key-env 指定的环境变量读：它不进 argv、不进日志、不进 payload。
        invalid = validate_base_url(args.base_url)
        if invalid is not None:
            return _report_failure("INVALID_ARGUMENT", invalid, EXIT_INVALID_ARGUMENT)
        provider = OpenAICompatProvider(
            base_url=args.base_url,
            model=args.model,
            api_key=os.environ.get(args.api_key_env),
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

    log = EventLog.start(_session_dir(args.session_dir))
    if isinstance(log, LogWriteFailure):
        return _report_failure(log.code, log.detail, EXIT_INTERNAL_ERROR)

    workspace: str | None = args.workspace
    openai = provider_name == "openai"
    settings = SessionSettings(
        workspace=Path(workspace) if workspace is not None else Path.cwd(),
        provider_name=provider_name,
        max_turns=max_turns,
        sandbox=args.sandbox,
        approval="auto" if args.yes else "ask",
        append_system_prompt=args.append_system_prompt,
        base_url=args.base_url if openai else None,
        model=args.model if openai else None,
        api_key_env=args.api_key_env if openai else None,
    )
    outcome = asyncio.run(
        _await_session(prompt=prompt, provider=provider, settings=settings, log=log)
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
        return _report_failure(
            "REPLAY_MISMATCH",
            f"error/replay 日志里没有任何 context/assembled：{path}",
            EXIT_INTERNAL_ERROR,
        )

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
