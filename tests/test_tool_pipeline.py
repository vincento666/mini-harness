"""seam ②：工具派发的六段顺序与失败短路。"""

from __future__ import annotations

from pathlib import Path

from mini_harness.tools import ToolRegistry
from mini_harness.tools.fences import DispatchContext
from mini_harness.tools.registry import ToolArgs, ToolDefinition, ToolResult
from tool_harness import dispatch_call


class _EmptyArgs(ToolArgs):
    pass


async def test_dispatch_walks_six_stages_in_order(tmp_path: Path) -> None:
    (tmp_path / "a.md").write_text("甲\n", encoding="utf-8")
    seen: list[str] = []

    outcome = await dispatch_call(tmp_path, "read", {"file_path": "a.md"}, on_stage=seen.append)

    assert outcome.result.outcome == "OK"
    assert seen == [
        "pre-execute",
        "guard",
        "execute",
        "post-execute",
        "finalizeContent",
        "result",
    ]


async def test_execute_failure_skips_post_stage(tmp_path: Path) -> None:
    async def fail(_args: _EmptyArgs, _context: DispatchContext) -> ToolResult:
        return ToolResult("TOOL_IO_FAILED", "boom")

    registry = ToolRegistry(
        [
            ToolDefinition(
                name="fail",
                description="always fails",
                args_model=_EmptyArgs,
                mutates=False,
                run=fail,
            )
        ]
    )
    seen: list[str] = []

    outcome = await dispatch_call(
        tmp_path,
        "fail",
        {},
        registry=registry,
        on_stage=seen.append,
    )

    assert outcome.result.outcome == "TOOL_IO_FAILED"
    assert seen == ["pre-execute", "guard", "execute", "result"]
