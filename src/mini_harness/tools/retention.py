"""单条工具结果的有界剪枝与 spill（M14b）。

形状照 DSH 的 `compaction-tool-result-pruner`：头 + 固定标记 + 尾，按 Unicode 码点计；
全文落工作区 spill，结果里只留相对路径与取回指引。与 DSH 的差别是不引入 `surfaceOp`：
剪枝发生在写日志之前，日志里就是剪后内容（见 design D0）。
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

PRUNE_CHARS = 8192
HEAD_CHARS = 4096
TAIL_CHARS = 1024
PRUNE_MARKER = "\n\n[... tool result middle pruned ...]\n\n"
SPILL_DIR = Path(".mini-harness") / "spill"


def _spill_path(content: str, tool_name: str, workspace: Path) -> tuple[Path, str]:
    digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
    root = workspace.resolve()
    target = (workspace / SPILL_DIR / f"{tool_name}-{digest[:16]}.txt").resolve()
    if not target.is_relative_to(root):
        raise OSError(f"spill 路径越出工作区：{target}")
    return target, digest


def _bounded(head: str, tail: str, notice: str) -> str:
    """头 + 标记 + 尾 + 通知不超过阈值；超了先缩尾。"""
    while tail and len(head) + len(PRUNE_MARKER) + len(tail) + len(notice) > PRUNE_CHARS:
        tail = tail[:-1]
    return f"{head}{PRUNE_MARKER}{tail}{notice}"


def prune_tool_content(
    content: str, tool_name: str, workspace: Path
) -> tuple[str, dict[str, Any] | None]:
    """超阈值才剪；返回（结果文本, `pruned` 元数据或 None）。"""
    if len(content) <= PRUNE_CHARS:
        return content, None
    chars = len(content)
    try:
        target, digest = _spill_path(content, tool_name, workspace)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    except OSError as exc:
        return content, {"chars": chars, "digest": "", "spill": None, "error": str(exc)}
    relative = target.relative_to(workspace.resolve()).as_posix()
    notice = f"\n\n(full result: {relative}; use read with offset/limit, or grep this path.)"
    text = _bounded(content[:HEAD_CHARS], content[-TAIL_CHARS:], notice)
    return text, {"chars": chars, "digest": digest, "spill": relative}
