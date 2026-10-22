"""seam ⑥ 共用的 CLI 黑盒 helper：真实子进程调用，且子进程的执行也计入覆盖率。"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from paths import PYPROJECT_TOML, REPO_ROOT

__all__ = ["_cli", "_cli_process"]


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
