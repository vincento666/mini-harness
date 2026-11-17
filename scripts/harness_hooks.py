"""harness hook 入口：SessionStart 装 git hook；PreToolUse 拦主规格与 ADR 的直接写入。

Claude Code 的 hook 协议：stdin 收 JSON，stdout 返回 JSON；退出码 0 表示不阻断。
DSH 通过 hooks-claude-code 桥接同一份 settings，因此这里只用协议内的字段。
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

PROTECTED_PREFIXES = ("openspec/specs/", "docs/adr/")
WRITE_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def session_start() -> int:
    """幂等安装 pre-commit；已装则静默。"""
    subprocess.run(
        [str(_repo_root() / "scripts" / "install-hooks.sh")],
        cwd=_repo_root(),
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return 0


def _relative(path: str, root: Path) -> str:
    try:
        return Path(path).resolve().relative_to(root).as_posix()
    except ValueError:
        return path


def pre_tool_use(payload: dict[str, object]) -> int:
    if payload.get("tool_name") not in WRITE_TOOLS:
        return 0
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        return 0
    raw_path = tool_input.get("file_path") or tool_input.get("notebook_path")
    if not isinstance(raw_path, str):
        return 0
    relative = _relative(raw_path, _repo_root())
    if not relative.startswith(PROTECTED_PREFIXES):
        return 0
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": (
                        f"{relative} 是主规格或 ADR：只能经 change 归档或人工确认后修改；"
                        "要改请走 openspec 归档流程。"
                    ),
                }
            },
            ensure_ascii=False,
        )
    )
    return 0


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("用法：harness_hooks.py <session-start|pre-tool-use>", file=sys.stderr)
        return 2
    if argv[1] == "session-start":
        return session_start()
    if argv[1] == "pre-tool-use":
        try:
            payload = json.load(sys.stdin)
        except json.JSONDecodeError:
            return 0
        return pre_tool_use(payload) if isinstance(payload, dict) else 0
    print(f"未知子命令：{argv[1]}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
