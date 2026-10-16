"""seam ④⑤⑥ 共用的 fixture 仓库路径常量（fixture 仓库只读，测试只复制不修改）。

`REPO_ROOT` 与 `PYPROJECT_TOML` 是给 seam ⑥ 的子进程用的：CLI 测试的 cwd 在仓库外，
coverage 的配置与 partial 数据文件都要显式指回仓库根（见 `tests/cli_blackbox.py`）。
"""

from __future__ import annotations

from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
REPO_ROOT = TESTS_DIR.parent
PYPROJECT_TOML = REPO_ROOT / "pyproject.toml"
FIXTURES_DIR = TESTS_DIR / "fixtures"
SCENARIOS_DIR = FIXTURES_DIR / "scenarios"
HELLO_SCENARIO = SCENARIOS_DIR / "hello" / "turns.json"
TOOL_THEN_DONE_SCENARIO = SCENARIOS_DIR / "tool_then_done" / "turns.json"
TOOL_THEN_EXHAUST_SCENARIO = SCENARIOS_DIR / "tool_then_exhaust" / "turns.json"

__all__ = [
    "FIXTURES_DIR",
    "HELLO_SCENARIO",
    "PYPROJECT_TOML",
    "REPO_ROOT",
    "SCENARIOS_DIR",
    "TESTS_DIR",
    "TOOL_THEN_DONE_SCENARIO",
    "TOOL_THEN_EXHAUST_SCENARIO",
]
