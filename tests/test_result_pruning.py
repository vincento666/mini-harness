"""seam ②：单条工具结果的剪枝与 spill 读回（M14b）。"""

from __future__ import annotations

import hashlib
from pathlib import Path

from mini_harness.tools.bash_tools import TRUNCATION_MARK
from mini_harness.tools.dispatch import _finalize_content
from mini_harness.tools.registry import ToolResult

MARKER = "[... tool result middle pruned ...]"


def test_a_long_result_is_pruned_and_spilled(tmp_path: Path) -> None:
    original = "x" * 20000

    result = _finalize_content(ToolResult("OK", original), "grep", tmp_path)

    assert len(result.content) <= 8192
    assert MARKER in result.content
    assert result.content.startswith("x" * 100)
    pruned = (result.meta or {})["pruned"]
    spill = tmp_path / str(pruned["spill"])
    assert spill.is_file()
    assert (
        hashlib.sha256(spill.read_text(encoding="utf-8").encode()).hexdigest() == pruned["digest"]
    )
    assert pruned["chars"] == 20000
    assert str(tmp_path) not in result.content


def test_a_short_result_is_untouched(tmp_path: Path) -> None:
    result = _finalize_content(ToolResult("OK", "短结果"), "grep", tmp_path)

    assert result.content == "短结果"
    assert result.meta is None
    assert not (tmp_path / ".mini-harness" / "spill").exists()


def test_pruning_is_idempotent(tmp_path: Path) -> None:
    once = _finalize_content(ToolResult("OK", "y" * 20000), "grep", tmp_path)

    twice = _finalize_content(once, "grep", tmp_path)

    assert twice.content == once.content


def test_bash_keeps_its_own_tail_policy(tmp_path: Path) -> None:
    result = _finalize_content(ToolResult("OK", "z" * 40000), "bash", tmp_path)

    assert MARKER not in result.content
    assert TRUNCATION_MARK in result.content


def test_a_spill_failure_keeps_the_inline_result(tmp_path: Path) -> None:
    (tmp_path / ".mini-harness").write_text("这是个文件，挡在目录位置上", encoding="utf-8")

    result = _finalize_content(ToolResult("OK", "w" * 20000), "grep", tmp_path)

    assert result.content == "w" * 20000
    pruned = (result.meta or {})["pruned"]
    assert pruned["spill"] is None
    assert pruned["error"]


def test_the_payload_carries_pruned_metadata(tmp_path: Path) -> None:
    """`tool/result` 的 payload 带 `pruned`，审计可核对 spill 与原文。"""
    import asyncio

    from mini_harness.config import build_registry
    from mini_harness.events import read_events
    from tool_harness import DONE, run_fixture_session, tool_call_entry

    (tmp_path / "big.txt").write_text(
        "\n".join(f"needle {i}: " + "x" * 20 for i in range(1000)), encoding="utf-8"
    )
    entries = [
        tool_call_entry("grep", "c1", pattern="needle"),
        {"content": "完", "finish_reason": "stop"},
        DONE,
    ]

    asyncio.run(run_fixture_session(tmp_path, "s-prune", entries, registry=build_registry(None)))

    records = read_events(tmp_path / "s-prune.jsonl")
    result = next(record for record in records if record.type == "tool/result")
    assert result.payload["pruned"]["chars"] > 8192
    assert result.payload["pruned"]["spill"].startswith(".mini-harness/spill/")


def test_read_is_not_pruned(tmp_path: Path) -> None:
    """read 有自己的 capped window + 续读约定，不能被剪枝。"""
    result = _finalize_content(ToolResult("OK", "r" * 20000), "read", tmp_path)

    assert result.content == "r" * 20000
    assert result.meta is None
