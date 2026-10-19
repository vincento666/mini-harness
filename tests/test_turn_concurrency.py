"""seam ①：同一回合的派发批次——只读并发、会改动串行、并发有上限。

判据测的是调度器，不是工具本身：注册表用真实文件工具的 `name` / `args_model` / `mutates`，
只把 `run` 包一层记录执行区间，于是「并发」是可观察的时间区间重叠，不是日志条数。
"""

from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import Any

from mini_harness.events import EventRecord, read_events
from mini_harness.provider import FixtureProvider
from mini_harness.provider.contract import ToolCall
from mini_harness.tools import ToolRegistry
from mini_harness.tools.fences import DispatchContext
from mini_harness.tools.file_tools import file_tool_definitions
from mini_harness.tools.registry import ToolDefinition, ToolResult
from tool_harness import DONE, run_session_fixture, turn_entry

_STEP_SECONDS = 0.05

# 一次工具执行的区间：(它操作的相对路径, 开始时刻, 结束时刻)。
Intervals = list[tuple[str, float, float]]


def _call(name: str, call_id: str, **arguments: object) -> ToolCall:
    return ToolCall(id=call_id, name=name, arguments=dict(arguments))


def _instrumented(observed: Intervals) -> ToolRegistry:
    """真实文件工具的契约原样保留，只把 `run` 包一层：先睡一小段，再记录执行区间。"""

    def wrap(definition: ToolDefinition) -> ToolDefinition:
        async def run(args: Any, context: DispatchContext) -> ToolResult:
            started = time.monotonic()
            await asyncio.sleep(_STEP_SECONDS)
            result = await definition.run(args, context)
            key = getattr(args, "file_path", definition.name)
            observed.append((key, started, time.monotonic()))
            return result

        return ToolDefinition(
            name=definition.name,
            description=definition.description,
            args_model=definition.args_model,
            mutates=definition.mutates,
            run=run,
        )

    return ToolRegistry([wrap(definition) for definition in file_tool_definitions()])


def _spans(observed: Intervals) -> dict[str, tuple[float, float]]:
    return {path: (started, ended) for path, started, ended in observed}


def _peak(observed: Intervals) -> int:
    """把执行区间展开成 +1/-1 事件，扫描线取「同时在跑」的最大数量。"""
    events = sorted(
        [(started, 1) for _, started, _ in observed] + [(ended, -1) for _, _, ended in observed],
        key=lambda item: (item[0], item[1]),
    )
    peak = 0
    current = 0
    for _, delta in events:
        current += delta
        peak = max(peak, current)
    return peak


def _ids(records: list[EventRecord], event_type: str) -> list[str]:
    """某一类事件里的 `tool_call_id`，按落盘顺序。"""
    return [str(record.payload["tool_call_id"]) for record in records if record.type == event_type]


async def test_two_reads_in_one_turn_overlap_in_time(tmp_path: Path) -> None:
    """规格 scenario「同一回合两个 read 并发」：两条 read 的执行时间区间重叠。"""
    (tmp_path / "a.md").write_text("甲\n", encoding="utf-8")
    (tmp_path / "b.md").write_text("乙\n", encoding="utf-8")
    observed: Intervals = []

    log, outcome = await run_session_fixture(
        tmp_path,
        "s-parallel-read",
        FixtureProvider(
            entries=[
                turn_entry(
                    _call("read", "c1", file_path="a.md"),
                    _call("read", "c2", file_path="b.md"),
                ),
                DONE,
            ]
        ),
        registry=_instrumented(observed),
        max_turns=4,
    )

    spans = _spans(observed)
    assert set(spans) == {"a.md", "b.md"}
    first = spans["a.md"]
    second = spans["b.md"]
    assert second[0] < first[1], "第二个 read 在第一个结束之后才开始：没有并发"

    records = read_events(log.path)
    assert isinstance(records, list)
    assert _ids(records, "tool/call") == ["c1", "c2"]
    assert _ids(records, "tool/result") == ["c1", "c2"]
    assert outcome.stop_reason == "MODEL_COMPLETED"


async def test_two_edits_in_one_turn_run_one_after_the_other(tmp_path: Path) -> None:
    """规格 scenario「同一回合两个 edit 串行」：第二个只在第一个执行结束之后才开始执行。

    两次 edit 声明在同一回合，读发生在更早的回合——同一批次的 read 不算已读过。
    """
    (tmp_path / "a.md").write_text("甲\n", encoding="utf-8")
    (tmp_path / "b.md").write_text("乙\n", encoding="utf-8")
    observed: Intervals = []

    await run_session_fixture(
        tmp_path,
        "s-serial-edit",
        FixtureProvider(
            entries=[
                turn_entry(
                    _call("read", "r1", file_path="a.md"),
                    _call("read", "r2", file_path="b.md"),
                ),
                turn_entry(
                    _call("edit", "c1", file_path="a.md", old_string="甲", new_string="甲甲"),
                    _call("edit", "c2", file_path="b.md", old_string="乙", new_string="乙乙"),
                ),
                DONE,
            ]
        ),
        registry=_instrumented(observed),
        max_turns=4,
    )

    spans = _spans(observed)
    assert set(spans) == {"a.md", "b.md"}
    first = spans["a.md"]
    second = spans["b.md"]
    assert second[0] >= first[1], "两个会改动文件的调用同时在跑：写没有串行"
    assert (tmp_path / "a.md").read_text(encoding="utf-8") == "甲甲\n"
    assert (tmp_path / "b.md").read_text(encoding="utf-8") == "乙乙\n"


async def test_ten_reads_in_one_turn_never_exceed_the_limit(tmp_path: Path) -> None:
    """规格 scenario「并发不超过上限」：10 条 read 同时在跑的不超过 8，10 个都有配对结果。"""
    for index in range(1, 11):
        (tmp_path / f"f{index}.md").write_text(f"{index}\n", encoding="utf-8")
    observed: Intervals = []
    reads = [_call("read", f"c{index}", file_path=f"f{index}.md") for index in range(1, 11)]
    batch = turn_entry(*reads)

    log, _ = await run_session_fixture(
        tmp_path,
        "s-limit",
        FixtureProvider(entries=[batch, DONE]),
        registry=_instrumented(observed),
        max_turns=4,
    )

    assert len(observed) == 10
    peak = _peak(observed)
    assert peak == 8, f"同时在跑的调用有 {peak} 个，上限是 8"

    records = read_events(log.path)
    assert isinstance(records, list)
    calls = _ids(records, "tool/call")
    assert len(calls) == 10
    assert _ids(records, "tool/result") == calls
