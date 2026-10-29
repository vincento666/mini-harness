"""`bash` 的执行契约：经平台 shell 跑一条命令，工作目录固定为工作区根（ADR-0009）。"""

from __future__ import annotations

import hashlib
import os
import sys
from pathlib import Path

from pydantic import Field

from mini_harness.tools.command_runner import (
    CommandRunner,
    default_command_runner,
)
from mini_harness.tools.fences import DispatchContext
from mini_harness.tools.registry import ToolArgs, ToolDefinition, ToolResult

DEFAULT_TIMEOUT_SECONDS = 30
MAX_TIMEOUT_SECONDS = 600
OUTPUT_LIMIT_BYTES = 16 * 1024
TRUNCATION_MARK = "[output truncated; full output: "

SHELL_FORM_POSIX = "/bin/sh -c"


def shell_form() -> str:
    """`bash` 实际用来执行命令的 shell 形态（ADR-0009）。

    不写死：Windows 上 `create_subprocess_shell` 用的是 `COMSPEC`，所以这里也读它——被改写时
    记录值才跟实际执行的那条一致；POSIX 一边 `create_subprocess_shell` 固定落 `/bin/sh`。
    """
    if sys.platform == "win32":
        return f"{os.path.basename(os.environ.get('COMSPEC', 'cmd.exe'))} /c"
    return SHELL_FORM_POSIX


def platform_facts() -> dict[str, str]:
    """进 `session/start` 的平台事实：`os` 与 `shell`（ADR-0029）。

    shell 这份事实住在知道它的这一层——`run_bash` 就是按它起进程的；CLI 只负责把它写下去，
    不再自己判一次平台（两处判断同一件事早晚分叉）。
    """
    return {"os": os.name, "shell": shell_form()}


def bound_bash_content(content: str, workspace: Path) -> str:
    """进日志的结果有界：超限保留尾部，完整内容落工作区 spill，结果只留 marker + 相对路径。"""
    encoded = content.encode("utf-8")
    if len(encoded) <= OUTPUT_LIMIT_BYTES:
        return content
    tail = encoded[-OUTPUT_LIMIT_BYTES:].decode("utf-8", errors="ignore")
    digest = hashlib.sha256(encoded).hexdigest()[:16]
    spill = workspace / ".mini-harness" / "spill" / f"bash-{digest}.txt"
    try:
        spill.parent.mkdir(parents=True, exist_ok=True)
        spill.write_text(content, encoding="utf-8")
        relative = spill.relative_to(workspace).as_posix()
        return f"{tail}\n{TRUNCATION_MARK}{relative}]"
    except OSError:
        return f"{tail}\n[output truncated; spill unavailable]"


class BashArgs(ToolArgs):
    command: str = Field(min_length=1)
    timeout_seconds: int = Field(default=DEFAULT_TIMEOUT_SECONDS, ge=1, le=MAX_TIMEOUT_SECONDS)

    def approval_detail(self) -> str:
        return self.command


async def run_bash(
    args: BashArgs, context: DispatchContext, runner: CommandRunner | None = None
) -> ToolResult:
    """跑一条命令：经注入的 runner；默认 runner 按平台选 adapter，cwd 是工作区根。"""
    try:
        result = await (runner or default_command_runner()).run(
            args.command,
            cwd=context.workspace,
            timeout_seconds=args.timeout_seconds,
        )
    except TimeoutError:
        return ToolResult(
            outcome="TOOL_TIMEOUT",
            content=f"命令超过 {args.timeout_seconds} 秒没有结束：{args.command}",
        )
    return ToolResult(
        outcome="OK",
        content=f"退出码 {result.exit_code}\n{result.output}",
    )


def bash_tool_definitions(runner: CommandRunner | None = None) -> list[ToolDefinition]:
    """`bash` 的工具定义：会改动，所以档位轴与问人都照常约束它。"""

    async def run(args: BashArgs, context: DispatchContext) -> ToolResult:
        return await run_bash(args, context, runner)

    return [
        ToolDefinition(
            name="bash",
            description=(
                "在工作区根跑一条真命令（构建、测试、版本控制、进程）并返回它的输出。"
                "命令自己的退出码非 0 不是 harness 失败，它出现在结果内容里。"
                "列文件用 glob、搜内容用 grep、读文件用 read：不要用 ls / grep / cat 这类等价命令，"
                "也不要临时写脚本。"
            ),
            args_model=BashArgs,
            mutates=True,
            run=run,
        )
    ]
