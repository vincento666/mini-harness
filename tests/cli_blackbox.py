"""seam ⑥ 共用的 CLI 黑盒 helper：真实子进程调用，且子进程的执行也计入覆盖率。"""

from __future__ import annotations

import ctypes
import json
import os
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest

from paths import PYPROJECT_TOML, REPO_ROOT

__all__ = [
    "_FakeEndpoint",
    "_LiveStreams",
    "_cli",
    "_cli_console_process",
    "_cli_process",
    "_send_ctrl_c",
]

# Windows 的控制台常量：`CREATE_NEW_CONSOLE` 与 `CREATE_NEW_PROCESS_GROUP` 是
# `subprocess` 的同名值，`ATTACH_PARENT_PROCESS` 是 `AttachConsole` 的「接回父进程的控制台」。
CREATE_NEW_CONSOLE = 0x00000010
CREATE_NEW_PROCESS_GROUP = 0x00000200
ATTACH_PARENT_PROCESS = 0xFFFFFFFF
CTRL_C_EVENT = 0


class _FakeEndpoint:
    """一个只监听 127.0.0.1 的 chat completions 端点：记下收到的请求，回放固定响应。

    seam ⑥ 要判「真实适配器撞上真实 HTTP 状态」时用它：子进程走真的 httpx，server 在
    测试进程里监听 loopback 的一个随机端口——判据不依赖任何真端点、不需要密钥。
    """

    def __init__(self, *, status: int, body: dict[str, Any]) -> None:
        self.requests: list[dict[str, Any]] = []
        endpoint = self

        class _Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:
                length = int(self.headers.get("content-length", "0"))
                payload = json.loads(self.rfile.read(length).decode("utf-8"))
                endpoint.requests.append(
                    {
                        "path": self.path,
                        "authorization": self.headers.get("authorization"),
                        "body": payload,
                    }
                )
                encoded = json.dumps(body).encode("utf-8")
                self.send_response(status)
                self.send_header("content-type", "application/json")
                self.send_header("content-length", str(len(encoded)))
                self.end_headers()
                self.wfile.write(encoded)

            def log_message(self, *args: Any) -> None:
                return

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    def __enter__(self) -> _FakeEndpoint:
        self._thread.start()
        return self

    def __exit__(self, *exc_info: object) -> None:
        self._server.shutdown()
        self._server.server_close()

    @property
    def base_url(self) -> str:
        host, port = self._server.server_address
        return f"http://{host}:{port}/v1"


def _command(*args: str) -> list[str]:
    return [
        sys.executable,
        "-m",
        "coverage",
        "run",
        "--rcfile",
        str(PYPROJECT_TOML),
        "-p",
        "-m",
        "mini_harness.cli.main",
        *args,
    ]


def _child_env(env: dict[str, str] | None) -> dict[str, str]:
    child_env = dict(os.environ if env is None else env)
    child_env["COVERAGE_FILE"] = str(REPO_ROOT / ".coverage")
    return child_env


def _cli(
    *args: str,
    cwd: Path,
    env: dict[str, str] | None = None,
    stdin_text: str | None = None,
) -> subprocess.CompletedProcess[str]:
    """跑一次 `python -m mini_harness.cli.main`，返回 CompletedProcess（UTF-8 文本）。

    子进程自己套一层 `coverage run`，这样 seam ⑥ 的黑盒调用也记账。两个坑都在这儿解决：
    测试的 `cwd` 是 tmp_path（在仓库外），coverage 找不到配置文件，所以显式 `--rcfile` 指回
    仓库根的 pyproject.toml；partial 数据文件默认落在 cwd，`coverage combine` 扫不到，所以
    用 `COVERAGE_FILE` 把它写进仓库根，配合 `-p` 让每个子进程各写一份 `.coverage.<pid>`。

    `stdin_text` 只给一条判据用：把 stdin 换成**管道**（仍然不是 tty），看门会不会把喂进来的
    `y` 当成人的回答。默认那条路径固定成「非 tty 且立刻 EOF」，黑盒因此拿到确定的 UNAVAILABLE，
    不看运行环境脸色。
    """
    return subprocess.run(
        _command(*args),
        cwd=str(cwd),
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=_child_env(env),
        stdin=None if stdin_text is not None else subprocess.DEVNULL,
        input=stdin_text,
    )


def _cli_process(*args: str, cwd: Path, keep_stdin_open: bool = False) -> subprocess.Popen[str]:
    """同一条命令，但以 `Popen` 起：用来在 session 进行中给它发信号。

    `keep_stdin_open` 给 `chat` 用：REPL 的 stdin 是一根一直开着的管道，测试往里写行、写完再关。
    默认那条路径仍是「非 tty 且立刻 EOF」。
    """
    return subprocess.Popen(
        _command(*args),
        cwd=str(cwd),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        env=_child_env(None),
        stdin=subprocess.PIPE if keep_stdin_open else subprocess.DEVNULL,
    )


def _cli_console_process(
    *args: str, cwd: Path, keep_stdin_open: bool = False
) -> subprocess.Popen[str]:
    """Windows 的 Ctrl-C 黑盒：子进程有自己的真实控制台、在新的进程组里。

    本机实测（2026-10-23）：只带 `CREATE_NEW_PROCESS_GROUP` 时 `GenerateConsoleCtrlEvent` 返回成功、
    子进程却收不到（`os.kill` 不报错，进程照常跑完）；先 `AttachConsole` 到子进程自己新开的那个
    控制台才送得进去——同一条路线在 M2 的 approval 冒烟脚手架上用过（`WriteConsoleInput` 那一版）。
    控制台是新开的，std 三条句柄仍是管道，所以 tty 检测与别的黑盒一致。
    """
    return subprocess.Popen(
        _command(*args),
        cwd=str(cwd),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        env=_child_env(None),
        stdin=subprocess.PIPE if keep_stdin_open else subprocess.DEVNULL,
        creationflags=CREATE_NEW_CONSOLE | CREATE_NEW_PROCESS_GROUP,
    )


def _send_ctrl_c(pid: int) -> None:
    """把 Ctrl-C 只发给那一个进程组；发完把控制台接回父进程。"""
    kernel32 = ctypes.windll.kernel32
    kernel32.FreeConsole()
    if not kernel32.AttachConsole(pid):
        error = kernel32.GetLastError()
        kernel32.FreeConsole()
        kernel32.AttachConsole(ATTACH_PARENT_PROCESS)
        raise RuntimeError(f"AttachConsole({pid}) 失败：win32 error {error}")
    try:
        if not kernel32.GenerateConsoleCtrlEvent(CTRL_C_EVENT, pid):
            raise RuntimeError(
                f"GenerateConsoleCtrlEvent(CTRL_C_EVENT, {pid}) 失败："
                f"win32 error {kernel32.GetLastError()}"
            )
    finally:
        kernel32.FreeConsole()
        kernel32.AttachConsole(ATTACH_PARENT_PROCESS)


class _LiveStreams:
    """把子进程的 stdout / stderr 实时读进内存：判据能在会话进行中看到已经打出来的东西。

    逐字符读，不按行：提示符不带换行之后，按行读要等到下一条带换行的输出才看得见它。
    """

    def __init__(self, process: subprocess.Popen[str]) -> None:
        self._process = process
        self._out: list[str] = []
        self._err: list[str] = []
        self._lock = threading.Lock()
        self._threads = [
            threading.Thread(target=self._pump, args=(stream, sink), daemon=True)
            for stream, sink in ((process.stdout, self._out), (process.stderr, self._err))
        ]

    @staticmethod
    def _pump(stream: Any, sink: list[str]) -> None:
        if stream is None:
            return
        while True:
            char = stream.read(1)
            if not char:
                return
            sink.append(char)

    def start(self) -> _LiveStreams:
        for thread in self._threads:
            thread.start()
        return self

    def stdout(self) -> str:
        with self._lock:
            return "".join(self._out)

    def stderr(self) -> str:
        with self._lock:
            return "".join(self._err)

    def wait_for_stdout(self, needle: str, reason: str, timeout: float = 25.0) -> None:
        """等到 stdout 上出现那串字符；等不到就是「屏幕上还没到那一刻」，判据当场失败。"""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if needle in self.stdout():
                return
            if self._process.poll() is not None:
                break
            time.sleep(0.05)
        self._process.kill()
        pytest.fail(f"子进程的 stdout 上没出现 {needle!r}（{reason}）：实得 {self.stdout()!r}")

    def finish(self, timeout: float = 40.0) -> tuple[int, str, str]:
        """等子进程退出、把两条流收全，返回 (退出码, stdout, stderr)。"""
        try:
            returncode = self._process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            self._process.kill()
            raise
        for thread in self._threads:
            thread.join(timeout=10)
        return returncode, self.stdout(), self.stderr()
