"""用真 pty 跑 `minihns chat`，按脚本喂输入 —— 给「必须终端才成立」的判据用。

为什么需要它：`chat` 的 Ctrl-C 判据只有在「进程有控制终端」时才成立。用
`subprocess.Popen(stdin=slave)` 起的 pty **不算**终端——从设备没有成为子进程的
控制终端，`os.tcgetpgrp(master)` 会是 0，写进去的 `0x03` 只是字节，不是信号，
于是「取消没生效」会被误读成功能坏了（`docs/lessons.md` L-101）。本脚本用
`pty.fork()`：子进程 `setsid` + 以从设备为控制终端 + dup2 + exec，`0x03` 走行
规程进 SIGINT，与人在终端里按键同一条路。

用法：

    uv run python scripts/uat/drive_chat_pty.py \
        --workspace .tmp/uat/m13 --session-dir .tmp/uat/m13/sessions \
        --script .tmp/uat/scene2.json -- --resume <session-id>

`--` 之后的内容原样交给 `chat`（本脚本固定加 `--provider openrouter --yes`，
端点与密钥按 `docs/reference/verification-endpoint.md`）。

脚本 JSON 是步骤数组，每步等一个正则再动作：

    [
      {"wait": "> ",        "send": "/goal",        "timeout": 120},
      {"wait": "\\\\[轮\\\\] 2/4", "sleep": 3, "send": "\\u0003", "timeout": 300},
      {"wait": "> ",        "send": "/goal resume", "timeout": 120},
      {"wait": "\\\\[轮\\\\] 3/4", "send": null,       "timeout": 300}
    ]

`send` 为 `null` 表示只等不输入；`"\\u0003"` 是 Ctrl-C，`"\\u0004"` 是 Ctrl-D。
末尾会打印终端全文与退出码；`[ctrl-c]` 行里的 `tcgetpgrp` 应当等于 `child_pid`，
这是「信号真的有去处」的现场判据。
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import pty
import re
import select
import signal
import sys
import time
from pathlib import Path

BOOTSTRAP = "import sys; from mini_harness.cli.main import main; sys.exit(main())"


def _args() -> tuple[Path, Path, Path, list[str]]:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--workspace", required=True, type=Path)
    parser.add_argument("--session-dir", required=True, type=Path)
    parser.add_argument("--script", required=True, type=Path, help="步骤 JSON")
    parser.add_argument("passthrough", nargs="*", help="`--` 之后交给 chat 的参数")
    parsed = parser.parse_args()
    return parsed.workspace, parsed.session_dir, parsed.script, parsed.passthrough


def main() -> int:
    workspace, session_dir, script_path, extra = _args()
    steps = json.loads(script_path.read_text(encoding="utf-8"))
    # 不要 resolve()：venv 里的 python 是指向基础解释器的符号链接，解开就丢了
    # 本项目的 site-packages（`_editable_impl_mini_harness.pth`），子进程 import 会失败。
    python = sys.executable
    argv = [
        python,
        "-c",
        BOOTSTRAP,
        "chat",
        "--provider",
        "openrouter",
        "--workspace",
        str(workspace),
        "--session-dir",
        str(session_dir),
        "--yes",
        *extra,
    ]

    pid, master = pty.fork()
    if pid == 0:  # 子进程：pty.fork 已完成 setsid 与被控终端设置
        os.execv(python, argv)
        os._exit(127)

    buf = ""
    pos = 0  # 已消费位置：要跳过自己那行的回显，但不能连同命令输出一起丢掉
    transcript: list[str] = []
    status: int | None = None
    fg = ""

    def drain(seconds: float) -> None:
        nonlocal buf
        until = time.time() + seconds
        while time.time() < until:
            ready, _, _ = select.select([master], [], [], 0.2)
            if master in ready:
                try:
                    chunk = os.read(master, 4096).decode("utf-8", "replace")
                except OSError:
                    return
                buf += chunk
                transcript.append(chunk)

    try:
        for index, step in enumerate(steps, 1):
            pattern = re.compile(step["wait"])
            deadline = time.time() + float(step.get("timeout", 120))
            matched = False
            while time.time() < deadline:
                drain(0.3)
                found = pattern.search(buf, pos)
                if found:
                    matched = True
                    pos = found.end()
                    break
                done, state = os.waitpid(pid, os.WNOHANG)
                if done == pid:
                    status = state
                    break
            print(f"[step {index} wait={step['wait']!r} matched={matched}]")
            if not matched:
                break
            if step.get("sleep"):
                drain(float(step["sleep"]))
            text = step.get("send")
            if text is None:
                continue
            if text == "\u0003":
                try:
                    fg = str(os.tcgetpgrp(master))
                except OSError as error:
                    fg = f"error:{error}"
                print(f"[ctrl-c] tcgetpgrp(master)={fg} child_pid={pid}")
                os.write(master, b"\x03")
                drain(0.2)
                continue
            os.write(master, text.encode("utf-8") + b"\n")
            deadline = time.time() + 3.0
            while time.time() < deadline:  # 等自己这一行的回显落地再推进游标
                drain(0.05)
                start = buf.find(text, pos)
                if start != -1:
                    newline = buf.find("\n", start + len(text))
                    if newline != -1:
                        pos = newline + 1
                        break
    finally:
        with contextlib.suppress(OSError):
            os.write(master, b"\x04")
        deadline = time.time() + 25
        while status is None and time.time() < deadline:
            done, state = os.waitpid(pid, os.WNOHANG)
            if done == pid:
                status = state
                break
            drain(0.2)
        if status is None:
            os.kill(pid, signal.SIGKILL)
            _, status = os.waitpid(pid, 0)
        drain(0.3)
        os.close(master)
        print("\n===== 终端全文（末 7000 字）=====")
        print("".join(transcript)[-7000:])
        code = os.waitstatus_to_exitcode(status)
        print(f"===== 退出码: {code} | fg_pgrp: {fg} | child_pid: {pid} =====")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
