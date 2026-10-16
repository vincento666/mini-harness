"""seam ④⑤⑥ 共用的 fixture 仓库路径常量（fixture 仓库只读，测试只复制不修改）。"""

from __future__ import annotations

from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
FIXTURES_DIR = TESTS_DIR / "fixtures"
SCENARIOS_DIR = FIXTURES_DIR / "scenarios"
HELLO_SCENARIO = SCENARIOS_DIR / "hello" / "turns.json"

__all__ = ["FIXTURES_DIR", "HELLO_SCENARIO", "SCENARIOS_DIR", "TESTS_DIR"]
