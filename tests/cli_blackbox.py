"""seam ⑥ 共用的 CLI 黑盒 helper：真实子进程调用，且子进程的执行也计入覆盖率。"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from paths import PYPROJECT_TOML, REPO_ROOT

__all__ = ["_cli"]


def _cli(
    *args: str, cwd: Path, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    """跑一次 `python -m mini_harness.cli.main`，返回 CompletedProcess（UTF-8 文本）。

    子进程自己套一层 `coverage run`，这样 seam ⑥ 的黑盒调用也记账。两个坑都在这儿解决：
    测试的 `cwd` 是 tmp_path（在仓库外），coverage 找不到配置文件，所以显式 `--rcfile` 指回
    仓库根的 pyproject.toml；partial 数据文件默认落在 cwd，`coverage combine` 扫不到，所以
    用 `COVERAGE_FILE` 把它写进仓库根，配合 `-p` 让每个子进程各写一份 `.coverage.<pid>`。
    """
    child_env = dict(os.environ if env is None else env)
    child_env["COVERAGE_FILE"] = str(REPO_ROOT / ".coverage")

    return subprocess.run(
        [
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
        ],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=child_env,
        # 子进程的 stdin 固定成「非 tty 且立刻 EOF」：approval 门因此不会挂在真实终端上，
        # 黑盒测试拿到的是确定的 UNAVAILABLE，而不是看运行环境脸色。
        stdin=subprocess.DEVNULL,
    )
