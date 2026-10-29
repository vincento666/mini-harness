"""外部命令执行缝：平台 adapter + fail-closed 的不可用异常。"""

from __future__ import annotations

import asyncio
import contextlib
import os
import signal
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol


class SandboxUnavailable(RuntimeError):
    """当前平台没有可用的受限 runner；调用方必须 fail closed，不得回退到未受限执行。"""


@dataclass(frozen=True)
class CommandResult:
    exit_code: int
    output: str


class CommandRunner(Protocol):
    """`bash` 只认这个缝；测试可注入 spy / unavailable runner。"""

    platform: str

    async def run(self, command: str, *, cwd: Path, timeout_seconds: int) -> CommandResult: ...


class _SubprocessRunner:
    """两个平台 adapter 的共同实现；平台差异只在进程组与收树手段。"""

    platform: str

    async def run(self, command: str, *, cwd: Path, timeout_seconds: int) -> CommandResult:
        shell_kwargs: dict[str, Any] = {}
        if self.platform != "win32":
            shell_kwargs["start_new_session"] = True
        process = await asyncio.create_subprocess_shell(
            command,
            cwd=str(cwd),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            **shell_kwargs,
        )
        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout_seconds)
        except TimeoutError:
            await self._terminate_tree(process)
            raise
        except asyncio.CancelledError:
            await self._terminate_tree(process)
            raise
        output = stdout.decode("utf-8", errors="replace") + stderr.decode("utf-8", errors="replace")
        return CommandResult(exit_code=process.returncode or 0, output=output)

    async def _terminate_tree(self, process: asyncio.subprocess.Process) -> None:
        if self.platform == "win32":
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
                os.killpg(  # type: ignore[attr-defined]
                    os.getpgid(process.pid),  # type: ignore[attr-defined]
                    signal.SIGKILL,  # type: ignore[attr-defined]
                )
        await process.wait()


class Win32CommandRunner(_SubprocessRunner):
    platform = "win32"


class PosixCommandRunner(_SubprocessRunner):
    platform = "posix"


def default_command_runner() -> CommandRunner:
    """按运行平台选 adapter；不在运行时把 posix adapter 塞给 win32。"""
    if sys.platform == "win32":
        return Win32CommandRunner()
    return PosixCommandRunner()
