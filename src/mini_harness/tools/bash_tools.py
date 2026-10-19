"""`bash` 的执行契约：经平台 shell 跑一条命令，工作目录固定为工作区根（ADR-0009）。"""

from __future__ import annotations

import asyncio
import contextlib
import os
import signal
import sys
from typing import Any

from pydantic import Field

from mini_harness.tools.fences import DispatchContext
from mini_harness.tools.registry import ToolArgs, ToolDefinition, ToolResult

DEFAULT_TIMEOUT_SECONDS = 30
MAX_TIMEOUT_SECONDS = 600


class BashArgs(ToolArgs):
    command: str = Field(min_length=1)
    timeout_seconds: int = Field(default=DEFAULT_TIMEOUT_SECONDS, ge=1, le=MAX_TIMEOUT_SECONDS)

    def approval_detail(self) -> str:
        return self.command


async def _terminate_tree(process: asyncio.subprocess.Process) -> None:
    """收掉这条命令启动的进程树。手段按平台不同，规格只承诺后果（ADR-0009）。"""
    if sys.platform == "win32":
        killer = await asyncio.create_subprocess_exec(
            "taskkill",
            "/T",
            "/F",
            "/PID",
            str(process.pid),
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await killer.wait()
    else:
        with contextlib.suppress(ProcessLookupError):
            os.killpg(os.getpgid(process.pid), signal.SIGKILL)
    await process.wait()


async def run_bash(args: BashArgs, context: DispatchContext) -> ToolResult:
    """跑一条命令：Windows 走 `cmd.exe /c`、POSIX 走 `/bin/sh -c`，cwd 是工作区根。"""
    shell_kwargs: dict[str, Any] = {}
    if sys.platform != "win32":
        # POSIX：命令待在自己的进程组里，超时之后整组收。
        shell_kwargs["start_new_session"] = True
    process = await asyncio.create_subprocess_shell(
        args.command,
        cwd=str(context.workspace),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        **shell_kwargs,
    )
    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=args.timeout_seconds)
    except TimeoutError:
        await _terminate_tree(process)
        return ToolResult(
            outcome="TOOL_TIMEOUT",
            content=f"命令超过 {args.timeout_seconds} 秒没有结束：{args.command}",
        )
    return ToolResult(
        outcome="OK",
        content=stdout.decode("utf-8", errors="replace") + stderr.decode("utf-8", errors="replace"),
    )


def bash_tool_definitions() -> list[ToolDefinition]:
    """`bash` 的工具定义：会改动，所以档位轴与问人都照常约束它。"""
    return [
        ToolDefinition(
            name="bash",
            description=(
                "在工作区根跑一条 shell 命令并返回它的输出。"
                "命令自己的退出码非 0 不是 harness 失败，它出现在结果内容里。"
            ),
            args_model=BashArgs,
            mutates=True,
            run=run_bash,
        )
    ]
