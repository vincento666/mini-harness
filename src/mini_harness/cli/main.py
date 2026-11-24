"""`minihns` 入口：解析参数、跑内核、把结果映射成退出码。"""

from __future__ import annotations

import argparse
import asyncio
import io
import json
import os
import signal
import sys
import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from types import FrameType
from typing import NoReturn

from mini_harness.cli.host import DEFAULT_HOST_PORT, host_main
from mini_harness.cli.serve import DEFAULT_HOST, DEFAULT_PORT, SERVE_HOSTS, BindFailure, ServeServer
from mini_harness.commands import RESERVED, command_catalog, direct_skill, execute_command
from mini_harness.config.load import ConfigFailure, discover_config, load_config
from mini_harness.events import (
    EventLog,
    EventRecord,
    LogReadFailure,
    LogWriteFailure,
    read_events,
)
from mini_harness.events.fold import assembled_payload, assembly_points, fold
from mini_harness.goals import (
    DEFAULT_MAX_ROUNDS,
    GoalRefusal,
    GoalRound,
    GoalSnapshot,
    edit_goal,
    fold_goal,
    goal_round_defect,
)
from mini_harness.loop import (
    ENTRY_CHAT,
    ENTRY_RUN,
    ENTRY_SERVE,
    SANDBOX_LEVELS,
    STOP_ABORTED,
    STOP_CONTEXT_WINDOW_EXCEEDED,
    STOP_FENCE_DENIED,
    STOP_MAX_STEPS,
    STOP_MODEL_COMPLETED,
    STOP_PROVIDER_ERROR,
    STOP_REASONS,
    STOP_TOOL_CALLS,
    RunOutcome,
    SessionEntry,
    SessionEnv,
    SessionSettings,
    TurnOutcome,
    end_session,
    next_goal_round,
    run_session,
    run_turn,
    settle_segment,
    start_session,
)
from mini_harness.loop.settings import (
    DEFAULT_MAX_STEPS,
    DEFAULT_RESERVE,
    DEFAULT_SANDBOX,
    DEFAULT_WINDOW,
)
from mini_harness.metering import collect_usage, pricing_from
from mini_harness.provider.contract import Provider
from mini_harness.session.assembly import (
    EXIT_INTERNAL_ERROR,
    EXIT_INVALID_ARGUMENT,
    AssemblyRequest,
    Failure,
    Prepared,
    assemble,
    request_from_args,
)
from mini_harness.skill_providers import SkillRegistry, skills_view
from mini_harness.skills import skill_content
from mini_harness.tools import ToolRegistry
from mini_harness.tools.fences import STDIN_QUESTION_GATE

EXIT_OK = 0
EXIT_FENCE_DENIED = 3
EXIT_CONTEXT_WINDOW_EXCEEDED = 4
EXIT_ABORTED = 5

STOP_REASONS_TO_EXIT_CODES: dict[str, int] = {
    STOP_MODEL_COMPLETED: EXIT_OK,
    STOP_TOOL_CALLS: EXIT_OK,
    STOP_MAX_STEPS: EXIT_OK,
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
    parser.add_argument(
        "--config",
        default=None,
        help="配置文件路径。没给时找 workspace 根的那份 mini.config.toml。",
    )
    parser.add_argument("--workspace", default=None, help="工作区根。没给时是当前目录。")
    parser.add_argument(
        "--session-dir",
        default=None,
        help="session 日志目录。没给时是 workspace 下的 sessions。",
    )
    parser.add_argument(
        "--provider",
        default=None,
        help=(
            "端点预设名 mock / openai / deepseek。没给时这一层看环境变量 MINIHNS_API_KEY："
            "已设且非空就是 openai，否则是 mock。"
        ),
    )
    parser.add_argument(
        "--fixture",
        default=None,
        help="mock provider 的 JSON 数组路径。provider 是 mock 时必需。",
    )
    parser.add_argument(
        "--base-url",
        default=None,
        help=(
            "OpenAI 兼容端点地址。没给时随 provider：openai 是 https://api.openai.com/v1，"
            "deepseek 是 https://api.deepseek.com，mock 没有端点。"
        ),
    )
    parser.add_argument(
        "--model",
        default=None,
        help=(
            "模型名。没给时随 provider：deepseek 预设给 deepseek-chat，"
            "openai 预设不给默认，缺它当场失败。"
        ),
    )
    parser.add_argument(
        "--api-key-env",
        default=None,
        help=(
            "密钥所在环境变量的名字。没给时随 provider："
            "openai 读 MINIHNS_API_KEY，deepseek 读 DEEPSEEK_API_KEY。"
        ),
    )
    parser.add_argument(
        "--max-steps",
        dest="max_steps",
        type=int,
        default=None,
        help=(
            f"一轮最多跑几步（一步 = 一次模型往返）。默认 {DEFAULT_MAX_STEPS}。"
            "多轮目标会把它乘以轮次；它不限制轮次。"
        ),
    )
    # 旧名保留一个改造窗口：dest 相同，help 里不列。用到了就在 `main()` 里打一次弃用提示。
    parser.add_argument(
        "--max-turns",
        dest="max_steps",
        type=int,
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--window",
        type=int,
        default=None,
        help=f"上下文窗口预算，单位 token。默认 {DEFAULT_WINDOW}。",
    )
    parser.add_argument(
        "--reserve",
        type=int,
        default=None,
        help=f"窗口里为回复与工具输出预留的 token。默认 {DEFAULT_RESERVE}。",
    )
    parser.add_argument(
        "--append-system-prompt",
        default=None,
        help="追加在系统提示末尾的一段文本。默认是空串。",
    )
    parser.add_argument(
        "--sandbox",
        choices=SANDBOX_LEVELS,
        default=None,
        help=f"围栏档位。默认 {DEFAULT_SANDBOX}。",
    )
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
    # M7 只有 HTTP 这一种传输，`--http` 是它的装饰：带不带它跑的是同一个会话（人裁决）。
    serve = subcommands.add_parser(
        "serve", help="跑一个会话并把日志作为事件流输出", parents=[shared]
    )
    serve.add_argument("--http", action="store_true")
    serve.add_argument("-p", "--prompt", default=None)
    serve.add_argument("--port", type=int, default=DEFAULT_PORT)
    serve.add_argument("--host", default=DEFAULT_HOST)

    # `host` 是常驻多会话入口，不是 `serve` 的模式开关（ADR-0031）：`--http` 同样是装饰。
    # 服务器级许可只在这里给：请求体不能自己给自己放行 `danger-full-access` / `auto`。
    host = subcommands.add_parser("host", help="常驻多会话宿主服务（HTTP + SSE）", parents=[shared])
    host.add_argument("--http", action="store_true")
    host.add_argument("--port", type=int, default=DEFAULT_HOST_PORT)
    host.add_argument("--host", default=DEFAULT_HOST)
    host.add_argument("--allow-danger-full-access", action="store_true")
    host.add_argument("--allow-auto-approval", action="store_true")

    # `chat` 没有 `-p/--prompt`，也没有 `--events`：一个会话的人话从 stdin 按行进来，
    # stdout 上只有模型回复正文与提示符（chat-repl 规格）。
    chat = subcommands.add_parser("chat", help="跑一个连续会话的 REPL", parents=[shared])
    chat.add_argument("--resume", default=None)

    replay = subcommands.add_parser("replay", help="重放一个 session 的日志")
    replay.add_argument("session_id")
    replay.add_argument("--session-dir", default=None)

    usage = subcommands.add_parser("usage", help="按步汇总 token 用量（JSON）")
    usage.add_argument("session_id")
    usage.add_argument("--session-dir", default=None)
    usage.add_argument("--config", default=None)

    # 带参数的目标编辑放在这里，不放在会话内命令：提示符上不做 flag 解析（C 方案）。
    # 它是**离线**操作：只改日志里的目标定义，不碰运行中进程的武装位。
    goal = subcommands.add_parser("goal", help="查看或改写一个会话的目标定义（离线）")
    goal.add_argument("session_id")
    goal.add_argument("--session-dir", default=None)
    goal.add_argument("action", choices=("show", "edit", "clear"), nargs="?", default="show")
    goal.add_argument("--max-rounds", type=int, default=None)
    goal.add_argument("objective", nargs="*", help="新的目标正文（整段替换）")
    return parser


def _report_failure(code: str, detail: str, exit_code: int) -> int:
    # detail 为空时只打失败码：取消没有失败结果，尾巴上挂一个冒号是悬空的（design D6）。
    sys.stderr.write(f"{code}: {detail}\n" if detail else f"{code}\n")
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
    skills_registry: SkillRegistry | None = None,
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
            skills_registry=skills_registry,
        )
    finally:
        signal.signal(signal.SIGINT, previous)


def _assembly_request(args: argparse.Namespace) -> AssemblyRequest:
    """CLI 的 argv 到装配请求：字段搬运只有一份，住在装配层。"""
    return request_from_args(args, auto_approve=args.yes)


def _prepare_or_fail(args: argparse.Namespace) -> Prepared | Failure:
    """`run` / `chat` / `serve` 共用的装配路；失败在建日志之前（cli 规格）。"""
    return assemble(_assembly_request(args), os.environ)


def _run(args: argparse.Namespace) -> int:
    """一次性 run：装配、跑内核、把结果映射成退出码。"""
    prompt: str | None = args.prompt
    if prompt is None or prompt == "":
        return _report_failure("INVALID_ARGUMENT", "-p/--prompt 必填且非空", EXIT_INVALID_ARGUMENT)
    prepared = _prepare_or_fail(args)
    if isinstance(prepared, Failure):
        return _report_failure(prepared.code, prepared.detail, prepared.exit_code)

    outcome = asyncio.run(
        _await_session(
            prompt=prompt,
            entry=ENTRY_RUN,
            provider=prepared.provider,
            settings=prepared.settings,
            log=prepared.log,
            registry=prepared.registry,
            skills_registry=prepared.skills_registry,
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

    # 监听地址打在 stderr：stdout 归 session id（event-stream 规格）。
    sys.stderr.write(f"serve 监听 http://{server.host}:{server.port}\n")

    prepared = _prepare_or_fail(args)
    if isinstance(prepared, Failure):
        await server.close()
        return _report_failure(prepared.code, prepared.detail, prepared.exit_code)

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
    """Ctrl-C 的落点：轮在跑就取消那一轮，没有轮在跑就结束会话（design D7）。"""

    active: asyncio.Event | None = None
    # 轮跑起来之后才有的循环句柄：取消必须经它叫醒循环（见 handler 的注释）。
    loop: asyncio.AbstractEventLoop | None = None


def _chat_sigint_handler(signals: _ChatSignals) -> Callable[[int, FrameType | None], None]:
    def handle(signum: int, frame: FrameType | None) -> None:
        loop = signals.loop
        if signals.active is not None and loop is not None:
            # 轮在跑：取消当前轮，会话继续。
            # MUST 走 `call_soon_threadsafe`：它顺带写循环的自管道，能把睡在 selector 里的
            # 循环叫醒。直接 `Event.set()` 只排队一个回调，循环要等到下一次 I/O 或超时才处理——
            # 真实端点 UAT 里表现为「Ctrl-C 之后 bash 还跑满 30 s」。
            loop.call_soon_threadsafe(signals.active.set)
            return
        # 提示符上：没有轮在跑，Ctrl-C 与 EOF 同一条路。
        raise KeyboardInterrupt

    return handle


def _suppress_sigint(signum: int, frame: FrameType | None) -> None:
    """会话收尾这一轮的 Ctrl-C 处理器：什么都不做（design D7）。

    收尾已经开始就走完——取消落进「`end_session` 还在跑」那道缝隙里不该留下未捕获异常，
    也不该把 `session/end` 写成半条。不置 `SIG_IGN`：Windows 上被忽略的 Ctrl-C 会在解释器里
    炸成 `OSError: Signal 2 ignored due to race condition`。
    """
    return None


def _tool_observer() -> Callable[[EventRecord], None]:
    """把 append 的 tool 事件投影成 stderr 行；observer 不参与落账。"""
    names: dict[str, str] = {}

    def observe(event: EventRecord) -> None:
        if event.type not in {"tool/call", "tool/result", "tool/cancelled"}:
            return
        call_id = str(event.payload.get("tool_call_id", ""))
        if event.type == "tool/call":
            name = str(event.payload.get("name", "?"))
            names[call_id] = name
            arguments = json.dumps(
                event.payload.get("arguments", {}), ensure_ascii=False, sort_keys=True
            )
            print(f"[tool] {name} {arguments}", file=sys.stderr)
        elif event.type == "tool/result":
            name = names.get(call_id, "?")
            outcome = str(event.payload.get("outcome", "?"))
            content = str(event.payload.get("content", "")).replace("\n", " ")
            preview = content[:160]
            suffix = f": {preview}" if preview else ""
            print(f"[tool] {name} -> {outcome}{suffix}", file=sys.stderr)
        else:
            name = names.get(call_id, "?")
            print(f"[tool] {name} cancelled", file=sys.stderr)

    return observe


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
        if seen <= printed:
            continue
        # 只带工具调用的步 `content` 是空串：打出去就是一条空行（design D2）。
        content = str(event.payload.get("content", ""))
        if content.strip():
            print(content)
    return seen


# 只有这一种收尾不打那一行，其余收尾理由一律打（design D4 与 D5；2026-10-23 人裁决：写反面集合）。
# `ABORTED` 从「不打」搬进「打」这一半：取消也是人不打命令、会话却少了一轮，屏幕上要看得见。
_SEGMENT_NOTE_SUPPRESSED = frozenset({STOP_MODEL_COMPLETED})


def _print_segment_note(segment: TurnOutcome) -> None:
    """轮级收尾给人一行（design D5）：走 stderr，不是日志的投影，也不写进日志。

    组装规则是 design D3：停止理由 → 与它**不同**的 `code` → 非空 `detail`，一律不截断。
    此前 `CONTEXT_WINDOW_EXCEEDED` 那一行把同一个词打两遍、把日志里那句有用的 detail 丢掉。
    这一行不是新事实，是 `turn/end` 与 `error/*` 已有的事实说给人听。
    """
    if segment.stop_reason in _SEGMENT_NOTE_SUPPRESSED:
        return
    parts: list[str] = [segment.stop_reason]
    if segment.failure_code is not None and segment.failure_code != segment.stop_reason:
        parts.append(segment.failure_code)
    if segment.detail:
        parts.append(segment.detail)
    note = parts[0] if len(parts) == 1 else f"{parts[0]}：{' '.join(parts[1:])}"
    print(f"[轮] 收尾 {note}", file=sys.stderr)


def _print_shadow_feedback(log: EventLog, through: int) -> tuple[int, LogReadFailure | None]:
    """把新写出的 `compaction/summary` 说给人听（design D6）：走 stderr，不进 stdout、不写日志。

    内容全部取自那条记录已有的四个键——不新增事件类型，也不改 payload。
    `through` 是上次扫到的 `seq`：一轮只报它自己那一轮里发生的压缩。
    """
    events = read_events(log.path)
    if isinstance(events, LogReadFailure):
        return through, events
    latest = through
    for event in events:
        latest = max(latest, event.seq)
        # 只报 `through` 之后新写出的那几条：整份日志每次都要读，不卡这条线就会重复报。
        if event.seq <= through or event.type != "compaction/summary":
            continue
        shadowed = event.payload.get("shadowed_range") or {}
        print(
            f"[遮蔽] 折掉 seq {shadowed.get('start')} 至 {shadowed.get('end')}："
            f"tokens {event.payload.get('tokens_before')} 降至 "
            f"{event.payload.get('tokens_after')}",
            file=sys.stderr,
        )
    return latest, None


def _run_chat_command(prepared: Prepared, text: str, env: SessionEnv | None = None) -> str | None:
    """一条斜杠命令；返回非 None 表示它展开成了一条要开轮的用户消息。"""
    skills = skills_view(prepared.skills_registry, prepared.settings.skills)
    name, _, arguments = text[1:].partition(" ")
    if name == "help":
        catalog = command_catalog(skills)
        listing = " / ".join(f"/{command.name}" for command in catalog)
        print(f"命令：{listing}")
        return None
    skill = direct_skill(name, skills)
    if skill is not None:
        command_id = uuid.uuid4().hex
        prepared.log.append(
            "command/run", {"command_id": command_id, "name": name, "raw_input": text}
        )
        prepared.log.append(
            "command/done",
            {"command_id": command_id, "ok": True, "text": f"已加载技能 {name}"},
        )
        instruction = arguments.strip() or f"（用户调用了技能 {name}，请按技能执行。）"
        return skill_content(skill, instruction)
    if name not in RESERVED:
        print(f"未知命令：/{name}", file=sys.stderr)
        return None
    records = read_events(prepared.log.path)
    # `command/run` 先落：命令的副作用（`/goal` 的 `goal/updated`）排在它之后，
    # 回放时「谁让它变的」不会晚于变化本身。
    command_id = uuid.uuid4().hex
    prepared.log.append("command/run", {"command_id": command_id, "name": name, "raw_input": text})
    outcome = execute_command(
        name,
        arguments,
        skills,
        [] if isinstance(records, LogReadFailure) else records,
        env,
    )
    assert outcome is not None  # RESERVED 与 execute_command 的已知集合同源
    prepared.log.append(
        "command/done", {"command_id": command_id, "ok": outcome.ok, "text": outcome.text}
    )
    if outcome.plan_active is not None:
        written = prepared.log.append("plan/mode", {"active": outcome.plan_active})
        if isinstance(written, LogWriteFailure):
            print("计划状态写不进日志", file=sys.stderr)
            return None
    print(outcome.text)
    return None


def _resume_round(env: SessionEnv, text: str, *, was_armed: bool) -> GoalRound | None:
    """`/goal resume` 之后驱动立刻开的那个轮次；其余命令返回 `None`（design D12）。

    只认命令面确实把武装位**从假翻到真**的三种事实：命令是 `resume`、目标 `active`、
    还有额度。`was_armed` 是命令执行前的武装位：已经在自动推进时，`/goal resume` 只是
    一句「无需 resume」，不能再起一轮——尤其是问题未决、目标保持 active 的时候。
    读不动日志就不猜——返回 `None`，让人留在一个能看见提示符的状态里。
    """
    name, _, arguments = text.partition(" ")
    if name != "/goal" or arguments.strip() != "resume":
        return None
    if was_armed or not env.goal_runtime.armed:
        return None
    return next_goal_round(env)


async def _chat_session(prepared: Prepared, signals: _ChatSignals) -> int:
    """读一行、开一轮、回到提示符；EOF 或提示符上的 Ctrl-C 收尾整个会话。

    SIGINT 处理器由 `_chat` 装（design D7）：会话收尾也在它的覆盖范围里，
    取消落进「循环已经退出、`end_session` 还没开始」那道缝隙里也有人接。
    """
    signals.loop = asyncio.get_running_loop()
    env = SessionEnv(
        provider=prepared.provider,
        log=prepared.log,
        registry=prepared.registry,
        settings=prepared.settings,
        skills_registry=prepared.skills_registry,
        question_gate=STDIN_QUESTION_GATE,
    )
    if not prepared.resumed:
        started = start_session(prompt="", entry=ENTRY_CHAT, env=env)
        if started is not None:
            return _report_failure(
                started.failure_code or started.stop_reason, started.detail, EXIT_INTERNAL_ERROR
            )
    # 会话 id 走 stderr（design D5）：stdout 那个投影只有模型回复正文与提示符。
    # 这一行同时是「这次会话的日志在哪」的入口——拿它跑 `minihns replay <id>` 找得到这次会话。
    print(f"会话 {prepared.log.session_id}", file=sys.stderr)
    prepared.log.subscribe(_tool_observer())

    segments = 0
    turn_index = 1
    printed = 0
    scanned = 0
    if prepared.resumed:
        events = read_events(prepared.log.path)
        if isinstance(events, LogReadFailure):
            return _report_failure(events.code, events.detail, EXIT_INTERNAL_ERROR)
        segments = sum(1 for event in events if event.type == "turn/start")
        steps = [event for event in events if event.type == "step/start"]
        turn_index = len(steps) + 1
        printed = sum(1 for event in events if event.type == "model/response")
        scanned = events[-1].seq if events else 0
    # 连续溢出的说明靠这两个局部变量（design 的 Risks）：记住上一轮的收尾理由、这一句说过没有。
    # 不进日志、不新增状态机。
    previous_stop_reason: str | None = None
    said_cannot_come_down = False

    def finish() -> TurnOutcome | None:
        """会话收尾：先换一个什么都不做的处理器，再写 `session/end`（design D7）。

        收尾已经开始就走完——`session/end` 不会被写成半条，也不留未捕获异常。
        不置 `SIG_IGN`：Windows 上被忽略的 Ctrl-C 会在解释器里炸成
        `OSError: Signal 2 ignored due to race condition`。
        """
        signal.signal(signal.SIGINT, _suppress_sigint)
        return end_session(env=env, stop_reason=STOP_MODEL_COMPLETED, steps=turn_index - 1)

    try:
        try:
            while True:
                # 提示符不带换行（design D1）：人输入的那一行紧跟在它之后，不落在空行上。
                # 显式 flush：stdout 是管道时它自带缓冲，不 flush 就等于屏幕上还没有提示符。
                sys.stdout.write(_CHAT_PROMPT)
                sys.stdout.flush()
                line = sys.stdin.readline()
                if line == "":
                    # EOF：会话正常收尾。
                    break
                text = line.strip()
                if not text:
                    # 空白输入不写记录，也不开轮。
                    continue
                if text.startswith("/"):
                    # 命令本身不写 user/message；`/<技能名> 指令` 会展开成一条消息再开轮。
                    was_armed = env.goal_runtime.armed
                    expanded = _run_chat_command(prepared, text, env)
                    if expanded is None:
                        # `/goal resume` 把武装位放开之后，驱动立刻开下一轮——不必再等一行
                        # （design D12）。其余命令仍然回到提示符。
                        goal_round = _resume_round(env, text, was_armed=was_armed)
                        if goal_round is None:
                            continue
                    else:
                        text = expanded
                        goal_round = None
                else:
                    goal_round = None
                while True:
                    segments += 1
                    if goal_round is not None:
                        # 自动轮次由驱动开：人手里没有提示符，得有一行说明这是第几轮
                        # （不是日志事实，只是把 goal 消息里的 `Round: n/cap` 说给人听）。
                        print(
                            f"[轮] {goal_round.round}/{goal_round.goal.max_rounds}",
                            file=sys.stderr,
                        )
                    cancel = asyncio.Event()
                    signals.active = cancel
                    try:
                        segment = await run_turn(
                            env=env,
                            turn_id=f"s{segments}",
                            first_step_index=turn_index,
                            cancel=cancel,
                            user_message=None if goal_round is not None else text,
                            goal_round=goal_round,
                        )
                    finally:
                        signals.active = None
                    if segment.stop_reason not in STOP_REASONS:
                        # 内核坏了：不再回到提示符，按内部错误收尾。
                        return _report_failure(
                            segment.failure_code or segment.stop_reason,
                            segment.detail,
                            EXIT_INTERNAL_ERROR,
                        )
                    turn_index += segment.steps
                    _print_segment_note(segment)
                    if (
                        segment.stop_reason == STOP_CONTEXT_WINDOW_EXCEEDED
                        and previous_stop_reason == STOP_CONTEXT_WINDOW_EXCEEDED
                        and not said_cannot_come_down
                    ):
                        # 连续两轮溢出：这一句每个会话只说一次，措辞留给实现。
                        # 不进日志、不结束会话、不改退出码。
                        print(
                            "[降不下去] 连续两轮溢出：这份会话已经降不下去，"
                            "退出并新开一个会话是可选动作。",
                            file=sys.stderr,
                        )
                        said_cannot_come_down = True
                    previous_stop_reason = segment.stop_reason
                    scanned, shadow_failure = _print_shadow_feedback(prepared.log, scanned)
                    if shadow_failure is not None:
                        return _report_failure(
                            shadow_failure.code, shadow_failure.detail, EXIT_INTERNAL_ERROR
                        )
                    replies = _print_new_replies(prepared.log, printed)
                    if isinstance(replies, LogReadFailure):
                        return _report_failure(replies.code, replies.detail, EXIT_INTERNAL_ERROR)
                    printed = replies
                    # 轮后驱动（design D3/D13）：目标 active 且已武装时不打印提示符，直接判下一轮。
                    # 收尾只有一份实现（`settle_segment`），host 与本入口共用。
                    settlement = settle_segment(
                        env=env,
                        segment=segment,
                        steps=turn_index - 1,
                        goal_round=goal_round is not None,
                    )
                    if settlement.failure is not None:
                        failed = settlement.failure
                        return _report_failure(
                            failed.failure_code or failed.stop_reason,
                            failed.detail,
                            EXIT_INTERNAL_ERROR,
                        )
                    decision = settlement.decision
                    if decision.kind == "awaiting_input":
                        print(
                            "[轮] 本轮有一个没答完的问题：目标保持 active；"
                            "直接回答，回答后自动继续",
                            file=sys.stderr,
                        )
                        break
                    if decision.kind == "stalled":
                        print(
                            "[轮] 本轮没有工具调用：已停止自动推进"
                            "（/goal resume 继续，/goal complete 结束）",
                            file=sys.stderr,
                        )
                        break
                    if decision.kind == "exhausted":
                        assert decision.goal is not None
                        print(
                            f"[轮] 已用尽 {decision.goal.rounds_started}/"
                            f"{decision.goal.max_rounds}：目标置为 blocked（round-limit）",
                            file=sys.stderr,
                        )
                        break
                    if decision.kind == "stop":
                        break
                    assert decision.goal is not None
                    goal_round = GoalRound(goal=decision.goal, round=decision.round)
        except KeyboardInterrupt:
            # 提示符上的 Ctrl-C：与 EOF 同一条路，写 `session/end`、退出码 0。
            pass
        ended = finish()
    except KeyboardInterrupt:
        # 取消正落在「循环已经退出、收尾还没开始」那道缝里：会话已经在收尾，把它收完。
        ended = finish()
    if ended is not None:
        return _report_failure(
            ended.failure_code or ended.stop_reason, ended.detail, EXIT_INTERNAL_ERROR
        )
    return EXIT_OK


def _chat(args: argparse.Namespace) -> int:
    """一个会话的 REPL：装配与 run 同一条路，之后只多「读行」这一件事。"""
    prepared = _prepare_or_fail(args)
    if isinstance(prepared, Failure):
        return _report_failure(prepared.code, prepared.detail, prepared.exit_code)
    signals = _ChatSignals()
    signal.signal(signal.SIGINT, _chat_sigint_handler(signals))
    # 不换回旧处理器（design D7）：会话收尾之后进程正在退出，换回去等于在退出前的缝隙里
    # 重新开一个没人接的洞——那里落进一次 Ctrl-C 就是一段 traceback 加一个非 0 退出码。
    return asyncio.run(_chat_session(prepared, signals))


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

    defect = goal_round_defect(records)
    if defect is not None:
        return _report_failure("REPLAY_MISMATCH", defect, EXIT_INTERNAL_ERROR)

    points = assembly_points(records)
    if not points:
        # 溢出与取消都能在第一次装配之前就把步收掉，那份日志是合法的：
        # 没有可重算的点不等于重算不一致，但要说明它，不能冒充「一条都验过」。
        print("no_context_assembled: 这份日志没有装配点")

    for point in points:
        # 折叠入参只从该点之前的事实派生：工具块与追加段都在 `session/start` 里，
        # 回放侧不存在「进程内注册表」这个第二真源。
        recomputed = fold(point.prefix)
        if assembled_payload(point.step_id, recomputed) != point.record.payload:
            return _report_failure(
                "REPLAY_MISMATCH",
                f"error/replay seq={point.record.seq} 的 context/assembled 与其前缀的重算不一致",
                EXIT_INTERNAL_ERROR,
            )
        print(f"verified seq={point.record.seq}: OK")

    for record in records:
        if record.type == "step/end":
            print(f"step {record.payload['step_id']}: {record.payload['stop_reason']}")
    if points:
        print("final_context: " + json.dumps(points[-1].record.payload, ensure_ascii=False))
    return EXIT_OK


def _goal(args: argparse.Namespace) -> int:
    """`minihns goal <id> [show|edit|clear]`：离线读写目标定义。

    只做定义层（正文、上限、清除），不做 `pause` / `resume` / `complete`——
    那三个是运行期控制，离线写只会让日志出现「没人按过」的动作，而且 `--resume`
    之后武装位仍为假。运行中的会话请用 REPL 的 `/goal` 或 host 的命令面。
    """
    session_dir = _session_dir(args.session_dir)
    path = session_dir / f"{args.session_id}.jsonl"
    if not path.is_file():
        return _report_failure("SESSION_NOT_FOUND", f"找不到日志：{path}", 1)
    records = read_events(path)
    if isinstance(records, LogReadFailure):
        return _report_failure(records.code, records.detail, EXIT_INTERNAL_ERROR)
    goal = fold_goal(records)
    if args.action == "show":
        if goal is None:
            print("没有当前目标")
            return 0
        print(f"目标 {goal.id}（revision {goal.revision}）：{goal.objective}")
        print(f"相位 {goal.phase} · 轮次 {goal.rounds_started}/{goal.max_rounds}")
        if goal.blocked_reason is not None:
            print(f"阻塞 {goal.blocked_reason.code}：{goal.blocked_reason.message}")
        return 0

    opened = EventLog.open(session_dir, args.session_id)
    if isinstance(opened, LogWriteFailure):
        return _report_failure(opened.code, opened.detail, EXIT_INTERNAL_ERROR)
    if goal is None:
        return _report_failure("GOAL_NOT_FOUND", "这个会话没有当前目标", 1)

    if args.action == "clear":
        written = opened.append("goal/updated", {"goal": None})
        if isinstance(written, LogWriteFailure):
            return _report_failure(written.code, written.detail, EXIT_INTERNAL_ERROR)
        print("已清除当前目标")
        return 0

    objective = " ".join(args.objective).strip() or None
    if objective is None and args.max_rounds is None:
        return _report_failure("INVALID_ARGUMENT", "edit 至少要给一个新正文或 --max-rounds", 2)
    if args.max_rounds is not None and args.max_rounds < 1:
        return _report_failure("INVALID_ARGUMENT", "--max-rounds 必须是正整数", 2)
    result: GoalSnapshot | GoalRefusal = edit_goal(
        goal,
        objective=objective,
        max_rounds=args.max_rounds,
        ceiling=DEFAULT_MAX_ROUNDS,
    )
    if isinstance(result, GoalRefusal):
        return _report_failure(result.outcome, result.detail, 2)
    written = opened.append("goal/updated", {"goal": result.model_dump(exclude_none=True)})
    if isinstance(written, LogWriteFailure):
        return _report_failure(written.code, written.detail, EXIT_INTERNAL_ERROR)
    print(f"已改写目标（revision {result.revision}）：{result.objective}")
    print(f"上限 {result.max_rounds} 轮")
    return 0


def _usage(args: argparse.Namespace) -> int:
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
    steps, total = collect_usage(records)
    cost: float | None = None
    config_path = discover_config(Path.cwd(), args.config)
    if config_path is not None:
        values = load_config(config_path)
        if not isinstance(values, ConfigFailure):
            model = next(
                (
                    record.payload.get("model")
                    for record in records
                    if record.type == "session/start"
                    and isinstance(record.payload.get("model"), str)
                ),
                "",
            )
            pricing = pricing_from(values, model) if isinstance(model, str) else None
            if pricing is not None:
                cost = round(pricing.cost(total), 6)
    payload = {
        "turns": [{"turn_id": turn.step_id, **turn.usage.as_dict()} for turn in steps],
        "total": total.as_dict(),
        "cost": cost,
    }
    print(json.dumps(payload, ensure_ascii=False))
    return EXIT_OK


def _reconfigure_streams() -> None:
    # stdin 也算：`chat` 按行读人的输入，编码不能看运行环境的脸色。
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        if isinstance(stream, io.TextIOWrapper):
            stream.reconfigure(encoding="utf-8")


def main(argv: Sequence[str] | None = None) -> int:
    """解析参数并返回退出码。"""
    _reconfigure_streams()
    raw = list(sys.argv[1:] if argv is None else argv)
    # 旧 flag 只做一次提示，不进日志：它是入口的形状，不是会话事实。
    if any(arg == "--max-turns" or arg.startswith("--max-turns=") for arg in raw):
        sys.stderr.write("--max-turns 已改名为 --max-steps；旧名只保留到本 change 合并前。\n")
    parser = build_parser()
    args = parser.parse_args(raw)
    if args.command == "run":
        return _run(args)
    if args.command == "serve":
        return _serve(args)
    if args.command == "chat":
        return _chat(args)
    if args.command == "host":
        return host_main(args)
    if args.command == "usage":
        return _usage(args)
    if args.command == "goal":
        return _goal(args)
    return _replay(args)


if __name__ == "__main__":
    sys.exit(main())
