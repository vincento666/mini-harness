"""seam ①：同一回合的派发批次——只读并发、会改动串行、并发有上限。

判据测的是调度器，不是工具本身：注册表用真实文件工具的 `name` / `args_model` / `mutates`，
只把 `run` 包一层记录执行区间，于是「并发」是可观察的时间区间重叠，不是日志条数。
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from mini_harness.events import read_events
from mini_harness.events.fold import fold
from mini_harness.provider import FixtureProvider
from tool_harness import (
    DONE,
    Intervals,
    call_ids,
    result_outcomes,
    run_session_fixture,
    serialized_registry,
    timed_registry,
    tool_call,
    turn_entry,
)


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
                    tool_call("read", "c1", file_path="a.md"),
                    tool_call("read", "c2", file_path="b.md"),
                ),
                DONE,
            ]
        ),
        registry=timed_registry(observed),
        max_turns=4,
    )

    spans = _spans(observed)
    assert set(spans) == {"a.md", "b.md"}
    first = spans["a.md"]
    second = spans["b.md"]
    assert second[0] < first[1], "第二个 read 在第一个结束之后才开始：没有并发"

    records = read_events(log.path)
    assert isinstance(records, list)
    assert call_ids(records, "tool/call") == ["c1", "c2"]
    assert call_ids(records, "tool/result") == ["c1", "c2"]
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
                    tool_call("read", "r1", file_path="a.md"),
                    tool_call("read", "r2", file_path="b.md"),
                ),
                turn_entry(
                    tool_call("edit", "c1", file_path="a.md", old_string="甲", new_string="甲甲"),
                    tool_call("edit", "c2", file_path="b.md", old_string="乙", new_string="乙乙"),
                ),
                DONE,
            ]
        ),
        registry=timed_registry(observed),
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
    reads = [tool_call("read", f"c{index}", file_path=f"f{index}.md") for index in range(1, 11)]
    batch = turn_entry(*reads)

    log, _ = await run_session_fixture(
        tmp_path,
        "s-limit",
        FixtureProvider(entries=[batch, DONE]),
        registry=timed_registry(observed),
        max_turns=4,
    )

    assert len(observed) == 10
    peak = _peak(observed)
    assert peak == 8, f"同时在跑的调用有 {peak} 个，上限是 8"

    records = read_events(log.path)
    assert isinstance(records, list)
    calls = call_ids(records, "tool/call")
    assert len(calls) == 10
    assert call_ids(records, "tool/result") == calls


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
                    tool_call("read", "c1", file_path="a.md"),
                    tool_call("write", "c2", file_path="a.md", content="改写\n"),
                ),
                DONE,
            ]
        ),
        registry=timed_registry(observed),
        max_turns=4,
    )

    records = read_events(log.path)
    assert isinstance(records, list)
    assert result_outcomes(records) == [("c1", "OK"), ("c2", "WRITE_WITHOUT_READ")]
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
                    tool_call("read", "c1", file_path="a.md"),
                    tool_call("read", "c2", file_path="b.md"),
                ),
                DONE,
            ]
        ),
        registry=timed_registry(observed, delays={"a.md": 0.2, "b.md": 0.02}),
        max_turns=4,
    )

    records = read_events(log.path)
    assert isinstance(records, list)
    spans = _spans(observed)
    assert spans["b.md"][1] < spans["a.md"][1], "第二个没有先完成：这个场景没构造出来"
    assert call_ids(records, "tool/result") == ["c1", "c2"]
    assert fold(records).model_dump(mode="json") == fold(
        [record.model_copy(deep=True) for record in records]
    ).model_dump(mode="json")


async def test_a_fence_denial_does_not_swallow_the_calls_dispatched_before_it(
    tmp_path: Path,
) -> None:
    """规格 scenario「终止不吞掉已经派发过的调用」：被拒之前派发过的每一条都有配对结果。

    形状要说清：落地的调度规则（只读并发、会改动串行）让「拒绝时另一个调用还在跑」在同一批里
    不可达——`c2` 要改动，它 MUST 等 `c1` 跑完才轮到。所以这条判据钉的是配对与落盘顺序，不是并发；
    「还在跑就被打断」那一半由取消路径判（`tests/test_turn_cancel.py`）。
    `c3` 声明在被拒之后，连 `tool/call` 都不写。
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
                    tool_call("read", "c1", file_path="a.md"),
                    tool_call("write", "c2", file_path="a.md", content="改写\n"),
                    tool_call("read", "c3", file_path="b.md"),
                ),
                DONE,
            ]
        ),
        registry=timed_registry(observed),
        sandbox="read-only",
        max_turns=4,
    )

    records = read_events(log.path)
    assert isinstance(records, list)
    assert call_ids(records, "tool/call") == ["c1", "c2"]
    assert result_outcomes(records) == [("c1", "OK"), ("c2", "DENIED_BY_FENCE")]
    fences = [record for record in records if record.type == "error/fence"]
    assert len(fences) == 1
    assert fences[0].payload["code"] == "SANDBOX_DENIES_WRITE"
    assert fences[0].payload["tool_call_id"] == "c2"
    # 档位轴先拒：没有「解析后键」可用，`path` 是 null；`raw_path` 仍是调用里写的写法。
    assert fences[0].payload["path"] is None
    assert fences[0].payload["raw_path"] == "a.md"
    fence_at = next(index for index, record in enumerate(records) if record.type == "error/fence")
    result_at = next(
        index
        for index, record in enumerate(records)
        if record.type == "tool/result" and record.payload["tool_call_id"] == "c1"
    )
    assert result_at < fence_at
    # 被拒的那一条没进执行段：`observed` 里只有 `c1`，它跑完之后才轮到 `c2`。
    assert [key for key, _, _ in observed] == ["a.md"]
    assert records[-1].type == "session/end"
    assert outcome.stop_reason == "FENCE_DENIED"
    assert outcome.failure_code == "SANDBOX_DENIES_WRITE"


async def test_calls_declared_after_a_denied_one_are_all_skipped(tmp_path: Path) -> None:
    """围栏拒绝之后声明的调用一个都不派发，包括排在「不会开始的调用」后面的那几个。

    「前一个已经开始」这条链在有人放弃派发时也必须传下去，否则后面的调用永远等下去。
    """
    (tmp_path / "a.md").write_text("甲\n", encoding="utf-8")
    observed: Intervals = []

    log, outcome = await asyncio.wait_for(
        run_session_fixture(
            tmp_path,
            "s-chain-after-denial",
            FixtureProvider(
                entries=[
                    turn_entry(
                        tool_call("write", "c1", file_path="a.md", content="改写\n"),
                        tool_call("write", "c2", file_path="b.md", content="新\n"),
                        tool_call("write", "c3", file_path="c.md", content="新\n"),
                    ),
                    DONE,
                ]
            ),
            registry=timed_registry(observed),
            sandbox="read-only",
            max_turns=4,
        ),
        timeout=10,
    )

    records = read_events(log.path)
    assert isinstance(records, list)
    assert call_ids(records, "tool/call") == ["c1"]
    assert result_outcomes(records) == [("c1", "DENIED_BY_FENCE")]
    assert outcome.stop_reason == "FENCE_DENIED"


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
        turn_entry(tool_call("read", "r1", file_path="a.md")),
        turn_entry(
            tool_call("edit", "c1", file_path="a.md", old_string="甲", new_string="甲甲"),
            tool_call("edit", "c2", file_path="a.md", old_string="甲", new_string="甲乙"),
        ),
        DONE,
    ]

    concurrent: Intervals = []
    log_a, _ = await run_session_fixture(
        tmp_path,
        "s-replay-concurrent",
        FixtureProvider(entries=entries),
        workspace=workspace_a,
        registry=timed_registry(concurrent),
        max_turns=4,
    )
    serial: Intervals = []
    log_b, _ = await run_session_fixture(
        tmp_path,
        "s-replay-serial",
        FixtureProvider(entries=entries),
        workspace=workspace_b,
        registry=serialized_registry(serial),
        max_turns=4,
    )

    records_a = read_events(log_a.path)
    records_b = read_events(log_b.path)
    assert isinstance(records_a, list)
    assert isinstance(records_b, list)
    expected = [("r1", "OK"), ("c1", "OK"), ("c2", "STALE_EDIT")]
    assert result_outcomes(records_a) == expected
    assert result_outcomes(records_b) == expected
    assert call_ids(records_a, "tool/result") == call_ids(records_b, "tool/result")
