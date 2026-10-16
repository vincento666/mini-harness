"""`minihns` 入口。"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence


def build_parser() -> argparse.ArgumentParser:
    """构造顶层解析器。"""
    return argparse.ArgumentParser(
        prog="minihns",
        description="mini-harness：headless agent harness",
    )


def main(argv: Sequence[str] | None = None) -> int:
    """解析参数并返回退出码。"""
    parser = build_parser()
    parser.parse_args(argv)
    return 0


if __name__ == "__main__":
    sys.exit(main())
