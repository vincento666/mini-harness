"""seam ①：回合循环的压缩段——越线、摘要、遮蔽、溢出。"""

from __future__ import annotations

import asyncio
from pathlib import Path

from mini_harness.events import EventRecord, read_events
from mini_harness.events.fold import TOOL_OUTCOME_UNKNOWN
from mini_harness.provider import FixtureProvider
from mini_harness.tools import ToolRegistry
from tool_harness import run_fixture_session, run_session_fixture

# 触发线 4364（`W - O - 65536` 比 `W * 0.8` 小）、保留预算 11200。
TIGHT_WINDOW = 70000
TIGHT_RESERVE = 100

# 25000 个估算 token：比保留预算大一倍，比触发线大得多。
BIG_TEXT = "x" * 100000

SUMMARY_TEXT = "那是此前的对话摘要"


def _big_turn() -> dict[str, object]:
    """一条又长又要继续跑的回合回复：长到该压缩，带调用所以循环不停下。"""
    return {
        "content": BIG_TEXT,
        "finish_reason": "tool_calls",
        "tool_calls": [{"id": "c1", "name": "read", "arguments": {"file_path": "a.md"}}],
    }


def _summary_entry(text: str = SUMMARY_TEXT) -> dict[str, object]:
    return {"content": text, "finish_reason": "stop"}


DONE_ENTRY: dict[str, object] = {"content": "收尾", "finish_reason": "stop"}


def _records_of(log_path: Path, event_type: str) -> list[EventRecord]:
    return [record for record in read_events(log_path) if record.type == event_type]


async def test_an_over_line_assembly_compacts_before_the_assembly_record(tmp_path: Path) -> None:
    log, outcome = await run_fixture_session(
        tmp_path,
        "s-compact",
        [_big_turn(), _summary_entry(), DONE_ENTRY],
        max_turns=3,
        window=TIGHT_WINDOW,
        reserve=TIGHT_RESERVE,
    )
    records = read_events(log.path)
    summaries = _records_of(log.path, "compaction/summary")

    assert len(summaries) == 1
    summary = summaries[0]
    assert summary.payload["turn_id"] == "t2"
    assert set(summary.payload) == {
        "turn_id",
        "shadowed_range",
        "summary",
        "tokens_before",
        "tokens_after",
    }
    assert summary.payload["summary"] == SUMMARY_TEXT
    assert summary.payload["tokens_before"] > summary.payload["tokens_after"]

    assembled = [record for record in records if record.type == "context/assembled"]
    assert [record.payload["turn_id"] for record in assembled] == ["t1", "t2"]
    turn_two = next(record for record in assembled if record.payload["turn_id"] == "t2")
    assert summary.seq < turn_two.seq

    contents = [message["content"] for message in turn_two.payload["messages"]]
    assert BIG_TEXT not in contents
    assert SUMMARY_TEXT in contents
    assert TOOL_OUTCOME_UNKNOWN not in contents
    assert outcome.stop_reason == "MODEL_COMPLETED"


async def test_the_summary_call_is_marked_and_gets_no_tools(tmp_path: Path) -> None:
    log, _ = await run_fixture_session(
        tmp_path,
        "s-summary-call",
        [_big_turn(), _summary_entry(), DONE_ENTRY],
        max_turns=3,
        window=TIGHT_WINDOW,
        reserve=TIGHT_RESERVE,
    )
    marked = [
        record for record in read_events(log.path) if record.payload.get("purpose") == "compaction"
    ]

    assert [record.type for record in marked] == ["model/request", "model/response"]
    assert [record.payload["turn_id"] for record in marked] == ["t2", "t2"]
    assert marked[0].payload["tools"] == []
    assert marked[1].payload["content"] == SUMMARY_TEXT


async def test_a_run_with_room_to_spare_never_compacts(tmp_path: Path) -> None:
    """默认预算（触发线 54272）下的小 run：一条 `compaction/summary` 都不该有。"""
    log, _ = await run_fixture_session(
        tmp_path,
        "s-roomy",
        [_big_turn(), DONE_ENTRY],
        max_turns=2,
    )

    assert _records_of(log.path, "compaction/summary") == []


async def test_overflow_when_nothing_can_be_shadowed(tmp_path: Path) -> None:
    """用户 prompt 本身就超线：它受保护、不能遮蔽，于是不调模型直接溢出。"""
    log, outcome = await run_session_fixture(
        tmp_path,
        "s-giant-prompt",
        provider=FixtureProvider(entries=[DONE_ENTRY]),
        prompt=BIG_TEXT,
        max_turns=1,
        registry=ToolRegistry(),
        window=TIGHT_WINDOW,
        reserve=TIGHT_RESERVE,
    )
    records = read_events(log.path)

    assert [record.type for record in records][-3:] == [
        "error/context",
        "turn/end",
        "session/end",
    ]
    assert _records_of(log.path, "model/request") == []
    assert _records_of(log.path, "tool/call") == []
    assert _records_of(log.path, "compaction/summary") == []
    error = _records_of(log.path, "error/context")[0]
    assert error.payload == {
        "turn_id": "t1",
        "code": "CONTEXT_WINDOW_EXCEEDED",
        "detail": error.payload["detail"],
    }
    closers = [
        record.payload["stop_reason"]
        for record in records
        if record.type in {"turn/end", "session/end"}
    ]
    assert closers == ["CONTEXT_WINDOW_EXCEEDED", "CONTEXT_WINDOW_EXCEEDED"]
    assert outcome.stop_reason == "CONTEXT_WINDOW_EXCEEDED"
    assert outcome.failure_code == "CONTEXT_WINDOW_EXCEEDED"


async def test_one_compaction_then_overflow_when_the_context_still_does_not_fit(
    tmp_path: Path,
) -> None:
    """摘要本身太大：压缩发生了一次，读数仍超线——不试第二次，直接溢出。"""
    log, outcome = await run_fixture_session(
        tmp_path,
        "s-big-summary",
        [_big_turn(), _summary_entry(BIG_TEXT)],
        max_turns=3,
        window=TIGHT_WINDOW,
        reserve=TIGHT_RESERVE,
    )
    records = read_events(log.path)

    assert len(_records_of(log.path, "compaction/summary")) == 1
    turn_two = [
        record
        for record in records
        if record.payload.get("turn_id") == "t2"
        and record.type in {"context/assembled", "model/request", "tool/call"}
        and record.payload.get("purpose") != "compaction"
    ]
    assert turn_two == []
    assert [record.type for record in records][-3:] == [
        "error/context",
        "turn/end",
        "session/end",
    ]
    assert outcome.stop_reason == "CONTEXT_WINDOW_EXCEEDED"


async def test_a_cancelled_run_does_not_compact(tmp_path: Path) -> None:
    """取消在场时不压缩：为压缩再调一次模型违背「取消优先到底」（ADR-0011）。"""
    cancel = asyncio.Event()
    cancel.set()
    log, outcome = await run_session_fixture(
        tmp_path,
        "s-cancel-no-compact",
        provider=FixtureProvider(entries=[DONE_ENTRY]),
        max_turns=2,
        registry=ToolRegistry(),
        window=TIGHT_WINDOW,
        reserve=TIGHT_RESERVE,
        cancel=cancel,
    )

    assert _records_of(log.path, "compaction/summary") == []
    assert _records_of(log.path, "error/context") == []
    assert outcome.stop_reason == "ABORTED"


async def test_a_failed_summary_call_is_a_provider_error(tmp_path: Path) -> None:
    """fixture 条目耗尽在摘要那次调用上：沿用 provider 失败形状，不写 `compaction/summary`。"""
    log, outcome = await run_fixture_session(
        tmp_path,
        "s-summary-fails",
        [_big_turn()],
        max_turns=3,
        window=TIGHT_WINDOW,
        reserve=TIGHT_RESERVE,
    )

    assert _records_of(log.path, "compaction/summary") == []
    errors = _records_of(log.path, "error/model")
    assert [record.payload["code"] for record in errors] == ["PROVIDER_EXHAUSTED"]
    closers = [
        record.payload["stop_reason"]
        for record in read_events(log.path)
        if record.type in {"turn/end", "session/end"}
    ]
    assert closers[-2:] == ["PROVIDER_ERROR", "PROVIDER_ERROR"]
    assert outcome.stop_reason == "PROVIDER_ERROR"
    assert outcome.failure_code == "PROVIDER_EXHAUSTED"
