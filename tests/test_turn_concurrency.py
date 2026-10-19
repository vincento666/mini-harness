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
from mini_harness.events.fold import fold
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


def _instrumented(observed: Intervals, delays: dict[str, float] | None = None) -> ToolRegistry:
    """真实文件工具的契约原样保留，只把 `run` 包一层：先睡一小段，再记录执行区间。

    `delays` 按被操作的路径定制睡眠长度，用来让「谁先完成」可控。
    """

    def wrap(definition: ToolDefinition) -> ToolDefinition:
        async def run(args: Any, context: DispatchContext) -> ToolResult:
            key = getattr(args, "file_path", definition.name)
            started = time.monotonic()
            await asyncio.sleep(_STEP_SECONDS if delays is None else delays.get(key, _STEP_SECONDS))
            result = await definition.run(args, context)
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


def _serialized(observed: Intervals) -> ToolRegistry:
    """同一批调用被强制排队：并发跑与串行跑的对照组。"""
    gate = asyncio.Lock()

    def wrap(definition: ToolDefinition) -> ToolDefinition:
        async def run(args: Any, context: DispatchContext) -> ToolResult:
            key = getattr(args, "file_path", definition.name)
            async with gate:
                started = time.monotonic()
                result = await definition.run(args, context)
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


def _outcomes(records: list[EventRecord]) -> list[tuple[str, str]]:
    """落盘的 `tool/result`：(它属于哪个调用, 结果词)，按落盘顺序。"""
    return [
        (str(record.payload["tool_call_id"]), str(record.payload["outcome"]))
        for record in records
        if record.type == "tool/result"
    ]


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


async def test_a_read_in_the_same_batch_does_not_unlock_a_write(tmp_path: Path) -> None:
    """规格 scenario「同批的 read 不算已读过」：前缀每回合取样一次，整批共用。"""
    (tmp_path / "a.md").write_text("甲\n", encoding="utf-8")
    observed: Intervals = []

    log, outcome = await run_session_fixture(
        tmp_path,
        "s-same-batch",
        FixtureProvider(
            entries=[
                turn_entry(
                    _call("read", "c1", file_path="a.md"),
                    _call("write", "c2", file_path="a.md", content="改写\n"),
                ),
                DONE,
            ]
        ),
        registry=_instrumented(observed),
        max_turns=4,
    )

    records = read_events(log.path)
    assert isinstance(records, list)
    assert _outcomes(records) == [("c1", "OK"), ("c2", "WRITE_WITHOUT_READ")]
    assert (tmp_path / "a.md").read_text(encoding="utf-8") == "甲\n"
    assert outcome.stop_reason == "MODEL_COMPLETED"


async def test_results_land_in_declared_order_when_the_second_finishes_first(
    tmp_path: Path,
) -> None:
    """规格 scenario「完成顺序与声明顺序不同」：落盘仍是声明顺序，两次折叠逐字段相等。"""
    (tmp_path / "a.md").write_text("甲\n", encoding="utf-8")
    (tmp_path / "b.md").write_text("乙\n", encoding="utf-8")
    observed: Intervals = []

    log, _ = await run_session_fixture(
        tmp_path,
        "s-declared-order",
        FixtureProvider(
            entries=[
                turn_entry(
                    _call("read", "c1", file_path="a.md"),
                    _call("read", "c2", file_path="b.md"),
                ),
                DONE,
            ]
        ),
        registry=_instrumented(observed, delays={"a.md": 0.2, "b.md": 0.02}),
        max_turns=4,
    )

    records = read_events(log.path)
    assert isinstance(records, list)
    spans = _spans(observed)
    assert spans["b.md"][1] < spans["a.md"][1], "第二个没有先完成：这个场景没构造出来"
    assert _ids(records, "tool/result") == ["c1", "c2"]
    assert fold(records).model_dump(mode="json") == fold(
        [record.model_copy(deep=True) for record in records]
    ).model_dump(mode="json")


async def test_a_fence_denial_does_not_swallow_the_calls_already_running(tmp_path: Path) -> None:
    """规格 scenario「围栏拒绝时已开始的并发调用不被吞」：它仍有配对的 `tool/result`。

    `c1` 是只读、先开始、还在跑；`c2` 是要改动的写、被档位轴拒绝；`c3` 声明在它之后，不派发。
    """
    (tmp_path / "a.md").write_text("甲\n", encoding="utf-8")
    (tmp_path / "b.md").write_text("乙\n", encoding="utf-8")
    observed: Intervals = []

    log, outcome = await run_session_fixture(
        tmp_path,
        "s-fence-midbatch",
        FixtureProvider(
            entries=[
                turn_entry(
                    _call("read", "c1", file_path="a.md"),
                    _call("write", "c2", file_path="a.md", content="改写\n"),
                    _call("read", "c3", file_path="b.md"),
                ),
                DONE,
            ]
        ),
        registry=_instrumented(observed),
        sandbox="read-only",
        max_turns=4,
    )

    records = read_events(log.path)
    assert isinstance(records, list)
    assert _ids(records, "tool/call") == ["c1", "c2"]
    assert _outcomes(records) == [("c1", "OK"), ("c2", "DENIED_BY_FENCE")]
    fences = [record for record in records if record.type == "error/fence"]
    assert len(fences) == 1
    assert fences[0].payload["code"] == "SANDBOX_DENIES_WRITE"
    assert fences[0].payload["tool_call_id"] == "c2"
    assert records[-1].type == "session/end"
    assert outcome.stop_reason == "FENCE_DENIED"
    assert outcome.failure_code == "SANDBOX_DENIES_WRITE"


async def test_the_same_batch_gives_the_same_outcomes_concurrently_and_serially(
    tmp_path: Path,
) -> None:
    """规格 scenario「同一批次重放得到同一判定」：并发跑与串行跑的每个 `outcome` 相同。

    两次 edit 共用同一份前缀：第二个的 CAS 对着快照，与它实际何时执行无关。
    """
    (tmp_path / "a.md").write_text("甲\n", encoding="utf-8")
    workspace_a = tmp_path / "ws-concurrent"
    workspace_b = tmp_path / "ws-serial"
    for workspace in (workspace_a, workspace_b):
        workspace.mkdir()
        (workspace / "a.md").write_text("甲\n", encoding="utf-8")
    entries = [
        turn_entry(_call("read", "r1", file_path="a.md")),
        turn_entry(
            _call("edit", "c1", file_path="a.md", old_string="甲", new_string="甲甲"),
            _call("edit", "c2", file_path="a.md", old_string="甲", new_string="甲乙"),
        ),
        DONE,
    ]

    concurrent: Intervals = []
    log_a, _ = await run_session_fixture(
        tmp_path,
        "s-replay-concurrent",
        FixtureProvider(entries=entries),
        workspace=workspace_a,
        registry=_instrumented(concurrent),
        max_turns=4,
    )
    serial: Intervals = []
    log_b, _ = await run_session_fixture(
        tmp_path,
        "s-replay-serial",
        FixtureProvider(entries=entries),
        workspace=workspace_b,
        registry=_serialized(serial),
        max_turns=4,
    )

    records_a = read_events(log_a.path)
    records_b = read_events(log_b.path)
    assert isinstance(records_a, list)
    assert isinstance(records_b, list)
    expected = [("r1", "OK"), ("c1", "OK"), ("c2", "STALE_EDIT")]
    assert _outcomes(records_a) == expected
    assert _outcomes(records_b) == expected
    assert _ids(records_a, "tool/result") == _ids(records_b, "tool/result")
