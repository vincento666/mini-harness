"""seam ①：回合循环的压缩段——越线、摘要、遮蔽、溢出。"""

from __future__ import annotations

import asyncio
import json
import re
from collections.abc import Iterable, Sequence
from pathlib import Path

from mini_harness.events import EventRecord, read_events
from mini_harness.events.fold import (
    SYSTEM_PROMPT,
    TOOL_OUTCOME_UNKNOWN,
    Message,
    assembly_points,
    fold,
)
from mini_harness.loop import ENTRY_RUN, run_turn_segment, start_session
from mini_harness.loop.turn_loop import SUMMARY_INSTRUCTION
from mini_harness.provider import FixtureProvider, ProviderFailure
from mini_harness.provider.contract import AssistantTurn, ToolSpec
from mini_harness.tools import ToolRegistry
from tool_harness import build_session_env, run_fixture_session, run_session_fixture

# 触发线 4364（`W - O - 65536` 比 `W * 0.8` 小）、保留预算 11200。
TIGHT_WINDOW = 70000
TIGHT_RESERVE = 100

# 25000 个估算 token：比保留预算大一倍，比触发线大得多。
BIG_TEXT = "x" * 100000

# 约 6000 个估算 token：比触发线 4364 大、比保留预算 11200 小——整段对话体都装得进保留尾部。
DEAD_ZONE_TEXT = "x" * 24000

# 75000 个估算 token：比 `70000 - 100` 这个压力预算还大，装不下才是溢出。
OVERFLOW_TEXT = "x" * 300000

# 窗口 20000 / 预留 100：压力预算 19900 个 token、保留预算 3200、触发线 0。
# 100000 个字符约 25000 个估算 token：比压力预算还大的一组工具往返，裁到只剩它也装不下。
SMALL_WINDOW = 20000
SMALL_RESERVE = 100
UNTRIMMABLE_TEXT = "长" * 100000

SUMMARY_TEXT = "那是此前的对话摘要"


def _big_turn() -> dict[str, object]:
    """一条又长又要继续跑的回合回复：长到该压缩，带调用所以循环不停下。"""
    return {
        "content": BIG_TEXT,
        "finish_reason": "tool_calls",
        "tool_calls": [{"id": "c1", "name": "read", "arguments": {"file_path": "a.md"}}],
    }


def _read_big_file_turn() -> dict[str, object]:
    """让工具结果本身长：模型只说一句就去读一个大文件。"""
    return {
        "content": "",
        "finish_reason": "tool_calls",
        "tool_calls": [{"id": "c1", "name": "read", "arguments": {"file_path": "big.md"}}],
    }


def _summary_entry(text: str = SUMMARY_TEXT) -> dict[str, object]:
    return {"content": text, "finish_reason": "stop"}


DONE_ENTRY: dict[str, object] = {"content": "收尾", "finish_reason": "stop"}


class _OverflowProvider:
    """模型层自己报出上下文超限：估算没抓到，兜底由 provider 触发。"""

    async def generate(
        self,
        messages: object,
        tools: object,
        signal: asyncio.Event,
    ) -> ProviderFailure:
        return ProviderFailure(code="PROVIDER_CONTEXT_OVERFLOW", detail="HTTP 400 上下文超限")


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
    """用户 prompt 本身就超压力预算：它受保护、不能遮蔽，于是不调模型直接溢出。"""
    log, outcome = await run_session_fixture(
        tmp_path,
        "s-giant-prompt",
        provider=FixtureProvider(entries=[DONE_ENTRY]),
        prompt=OVERFLOW_TEXT,
        max_turns=1,
        registry=ToolRegistry(),
        window=TIGHT_WINDOW,
        reserve=TIGHT_RESERVE,
    )
    records = read_events(log.path)

    assert [record.type for record in records][-4:] == [
        "error/context",
        "turn/end",
        "segment/end",
        "session/end",
    ]
    assert _records_of(log.path, "model/request") == []
    assert _records_of(log.path, "tool/call") == []
    assert _records_of(log.path, "compaction/summary") == []
    error = _records_of(log.path, "error/context")[0]
    assert error.payload["code"] == "CONTEXT_WINDOW_EXCEEDED"
    assert error.payload["turn_id"] == "t1"
    # 人手验收里发现的措辞：没有发生压缩时不能说「压缩之后」。
    assert error.payload["detail"].startswith("无可遮蔽的内容")
    # 三个数并排才看得出来死区：预算读数、压力预算 69900、触发线 4364。
    assert "压力预算 69900" in error.payload["detail"]
    assert "触发线 4364" in error.payload["detail"]
    assert re.search(r"预算读数 \d+", error.payload["detail"])
    closers = [
        record.payload["stop_reason"]
        for record in records
        if record.type in {"turn/end", "segment/end", "session/end"}
    ]
    assert closers == ["CONTEXT_WINDOW_EXCEEDED"] * 3
    assert outcome.stop_reason == "CONTEXT_WINDOW_EXCEEDED"
    assert outcome.failure_code == "CONTEXT_WINDOW_EXCEEDED"


async def test_a_dead_zone_reading_that_fits_the_window_is_not_an_overflow(
    tmp_path: Path,
) -> None:
    """死区：读数超过触发线 4364，但整段对话体都装得进保留尾部 11200，于是没有可遮蔽的内容；
    而它离压力预算 69900 还远——装得下就不是溢出，照常装配、照常调模型。

    这是 M5 真实端点重新验收里 session `70fa85600d484109b2f266506ee24c42` 的形状：
    读数 5933 在 `--window 70000 --reserve 100` 下以退出码 4 收尾。
    """
    (tmp_path / "big.md").write_text(DEAD_ZONE_TEXT, encoding="utf-8")
    log, outcome = await run_fixture_session(
        tmp_path,
        "s-dead-zone",
        [_read_big_file_turn(), DONE_ENTRY],
        max_turns=2,
        window=TIGHT_WINDOW,
        reserve=TIGHT_RESERVE,
    )
    records = read_events(log.path)

    assert _records_of(log.path, "compaction/summary") == []
    assert _records_of(log.path, "error/context") == []
    assembled = [record for record in records if record.type == "context/assembled"]
    assert [record.payload["turn_id"] for record in assembled] == ["t1", "t2"]
    requests = [
        record
        for record in records
        if record.type == "model/request" and record.payload.get("purpose") != "compaction"
    ]
    assert [record.payload["turn_id"] for record in requests] == ["t1", "t2"]
    assert outcome.stop_reason == "MODEL_COMPLETED"


async def test_a_shadowed_range_too_big_to_trim_sends_no_summary_request(
    tmp_path: Path,
) -> None:
    """遮蔽范围存在、但那一组往返本身就装不进压力预算：不发摘要请求、不写 `error/model`。

    溢出仍然发生，可它发生的原因是**读数本身超过压力预算**，不是「摘要请求发不出去」——
    这两件事不该互相冒充（design D4）。措辞也不该说「无可遮蔽的内容」：这一回合有可遮蔽的
    那一段，只是它本身就装不下。
    """
    (tmp_path / "big.md").write_text(UNTRIMMABLE_TEXT, encoding="utf-8")
    log, outcome = await run_fixture_session(
        tmp_path,
        "s-untrimmable",
        [_read_big_file_turn(), DONE_ENTRY],
        max_turns=2,
        window=SMALL_WINDOW,
        reserve=SMALL_RESERVE,
    )

    assert _records_of(log.path, "compaction/summary") == []
    assert _records_of(log.path, "error/model") == []
    requests = _records_of(log.path, "model/request")
    assert [record for record in requests if record.payload.get("purpose") == "compaction"] == []
    error = _records_of(log.path, "error/context")[0]
    assert error.payload["code"] == "CONTEXT_WINDOW_EXCEEDED"
    assert error.payload["detail"].startswith("可遮蔽的那一段")
    assert "压力预算 19900" in error.payload["detail"]
    assert "触发线 0" in error.payload["detail"]
    assert outcome.stop_reason == "CONTEXT_WINDOW_EXCEEDED"


async def test_an_overflow_closes_the_segment_not_the_session(tmp_path: Path) -> None:
    """溢出是**回合**终止结果：段自己只写到 `segment/end`，会话是否结束归入口（ADR-0011）。

    一次性 run 的入口接着写 `session/end` 并映射退出码 4，那条判据在 `tests/test_cli_run.py`。

    窗口 4000 / 预留 500 的压力预算是 3500 个 token：prompt 要 20000 个字符才装不下。
    """
    log, env = build_session_env(
        tmp_path,
        "s-overflow-segment",
        FixtureProvider(entries=[DONE_ENTRY]),
        window=4000,
        reserve=500,
        max_turns=4,
    )

    assert start_session(prompt="x" * 20000, entry=ENTRY_RUN, env=env) is None
    segment = await run_turn_segment(
        env=env, segment_id="s1", first_turn_index=1, cancel=asyncio.Event()
    )

    records = read_events(log.path)
    assert segment.stop_reason == "CONTEXT_WINDOW_EXCEEDED"
    assert [record.type for record in records] == [
        "session/start",
        "segment/start",
        "turn/start",
        "error/context",
        "turn/end",
        "segment/end",
    ]
    assert records[-1].payload == {
        "segment_id": "s1",
        "stop_reason": "CONTEXT_WINDOW_EXCEEDED",
        "turns": 1,
    }


async def test_one_compaction_then_overflow_when_the_context_still_does_not_fit(
    tmp_path: Path,
) -> None:
    """摘要本身太大：压缩发生了一次，读数仍超压力预算——不试第二次，直接溢出。"""
    log, outcome = await run_fixture_session(
        tmp_path,
        "s-big-summary",
        [_big_turn(), _summary_entry(OVERFLOW_TEXT)],
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
    assert [record.type for record in records][-4:] == [
        "error/context",
        "turn/end",
        "segment/end",
        "session/end",
    ]
    # 这一条压缩真的发生过，措辞就该是「压缩之后」。
    overflow_error = _records_of(log.path, "error/context")[0]
    assert overflow_error.payload["detail"].startswith("压缩之后")
    assert "压力预算 69900" in overflow_error.payload["detail"]
    assert "触发线 4364" in overflow_error.payload["detail"]
    assert re.search(r"预算读数 \d+", overflow_error.payload["detail"])
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


async def test_a_provider_reported_overflow_collapses_into_the_same_result(tmp_path: Path) -> None:
    """两条触发路径产出同一个溢出结果：`error/context` 收尾，没有 `error/model`。"""
    log, outcome = await run_session_fixture(
        tmp_path,
        "s-provider-overflow",
        _OverflowProvider(),
        max_turns=2,
        registry=ToolRegistry(),
    )
    records = read_events(log.path)

    assert [record.type for record in records][-4:] == [
        "error/context",
        "turn/end",
        "segment/end",
        "session/end",
    ]
    assert _records_of(log.path, "error/model") == []
    assert _records_of(log.path, "compaction/summary") == []
    assert _records_of(log.path, "tool/call") == []
    assert outcome.stop_reason == "CONTEXT_WINDOW_EXCEEDED"
    assert outcome.failure_code == "CONTEXT_WINDOW_EXCEEDED"


class _OverflowOnceProvider:
    """模型层报出上下文超限：第 `fail_plain_calls` 次**带工具表**的回合调用报失败。

    摘要那次调用不带工具表（design D2），所以它照常从 fixture 取条目。
    """

    def __init__(
        self, entries: list[dict[str, object]], *, fail_plain_calls: tuple[int, ...]
    ) -> None:
        self._fixture = FixtureProvider(entries=entries)
        self._fail_plain_calls = fail_plain_calls
        self._plain_calls = 0

    async def generate(self, messages: object, tools: object, signal: asyncio.Event) -> object:
        if tools:
            self._plain_calls += 1
            if self._plain_calls in self._fail_plain_calls:
                return ProviderFailure(
                    code="PROVIDER_CONTEXT_OVERFLOW", detail="HTTP 400 上下文超限"
                )
        return await self._fixture.generate(messages, tools, signal)


async def test_a_provider_reported_overflow_is_compacted_once_and_retried(
    tmp_path: Path,
) -> None:
    """请求级压缩救回一次：压一次、重试一次，回合以正常的 `model/response` 继续（ADR-0019）。"""
    log, outcome = await run_session_fixture(
        tmp_path,
        "s-request-compaction",
        _OverflowOnceProvider([_big_turn(), _summary_entry(), DONE_ENTRY], fail_plain_calls=(2,)),
        max_turns=3,
    )
    records = read_events(log.path)
    turn_two = [record for record in records if record.payload.get("turn_id") == "t2"]

    assert outcome.stop_reason == "MODEL_COMPLETED"
    summaries = _records_of(log.path, "compaction/summary")
    assert [record.payload["turn_id"] for record in summaries] == ["t2"]
    # 压完之后重试那一次是又一次真实的调用：t2 有两条不带 purpose 的 `model/request`。
    plain_requests = [
        record
        for record in turn_two
        if record.type == "model/request" and "purpose" not in record.payload
    ]
    plain_responses = [
        record
        for record in turn_two
        if record.type == "model/response" and "purpose" not in record.payload
    ]
    assert len(plain_requests) == 2
    assert [record.payload["content"] for record in plain_responses] == ["收尾"]
    assert _records_of(log.path, "error/context") == []
    assert _records_of(log.path, "error/model") == []
    assert [record.payload["stop_reason"] for record in records if record.type == "turn/end"] == [
        "TOOL_CALLS",
        "MODEL_COMPLETED",
    ]


async def test_the_request_level_retry_records_the_context_it_actually_sent(
    tmp_path: Path,
) -> None:
    """请求级重试之前补一条 `context/assembled`：那条快照说的是重试实际发出去的那份表层。"""
    log, _outcome = await run_session_fixture(
        tmp_path,
        "s-request-retry-snapshot",
        _OverflowOnceProvider([_big_turn(), _summary_entry(), DONE_ENTRY], fail_plain_calls=(2,)),
        max_turns=3,
    )
    records = read_events(log.path)
    points = [point for point in assembly_points(records) if point.turn_id == "t2"]

    assert len(points) == 2
    for point in points:
        following = records[len(point.prefix) + 1]
        assert following.type == "model/request"
        assert "purpose" not in following.payload
    # 两条都按各自的前缀重算得出来：新形状没有给 replay 添新规则。
    for point in points:
        recomputed = fold(point.prefix).model_dump(mode="json")
        payload = {key: value for key, value in point.record.payload.items() if key != "turn_id"}
        assert recomputed == payload
    # 第二条说的是遮蔽之后那份表层：摘要在里面，第一条里没有。
    second = [str(message["content"]) for message in points[1].record.payload["messages"]]
    first = [str(message["content"]) for message in points[0].record.payload["messages"]]
    assert SUMMARY_TEXT in second
    assert SUMMARY_TEXT not in first


async def test_a_provider_reported_overflow_that_survives_the_retry_collapses(
    tmp_path: Path,
) -> None:
    """重试仍报同一失败：上限 1 次用完，塌成同一个溢出结果，没有 `error/model`。"""
    log, outcome = await run_session_fixture(
        tmp_path,
        "s-request-compaction-fails",
        _OverflowOnceProvider([_big_turn(), _summary_entry()], fail_plain_calls=(2, 3)),
        max_turns=3,
    )
    records = read_events(log.path)

    assert len(_records_of(log.path, "compaction/summary")) == 1
    assert [record.type for record in records][-4:] == [
        "error/context",
        "turn/end",
        "segment/end",
        "session/end",
    ]
    assert _records_of(log.path, "error/model") == []
    assert outcome.stop_reason == "CONTEXT_WINDOW_EXCEEDED"
    assert outcome.failure_code == "CONTEXT_WINDOW_EXCEEDED"


class _RecordingProvider:
    """记下每次调用实际收到的消息与工具：判「摘要请求装了什么」只能从这里看。"""

    def __init__(self, entries: list[dict[str, object]]) -> None:
        self.calls: list[tuple[list[Message], list[ToolSpec]]] = []
        self._inner = FixtureProvider(entries=entries)

    async def generate(
        self,
        messages: Sequence[Message],
        tools: Sequence[ToolSpec],
        signal: asyncio.Event,
    ) -> AssistantTurn | ProviderFailure:
        self.calls.append((list(messages), list(tools)))
        return await self._inner.generate(messages, tools, signal)


# 折叠会产出消息的记录类型：判「请求里装的是哪些记录」按它们取内容。
_CONTENT_TYPES = ("user/message", "model/response", "tool/result")


def _contents_of(records: Iterable[EventRecord]) -> set[str]:
    return {
        str(record.payload.get("content", ""))
        for record in records
        if record.type in _CONTENT_TYPES
    }


async def test_the_summary_request_carries_only_the_shadowed_range(tmp_path: Path) -> None:
    """seam ①：摘要请求只装本次要遮蔽的那一段——保留尾部与受保护头部不在其中。"""
    provider = _RecordingProvider([_big_turn(), _summary_entry(), DONE_ENTRY])
    log, _ = await run_session_fixture(
        tmp_path,
        "s-summary-shape",
        provider,
        max_turns=3,
        window=TIGHT_WINDOW,
        reserve=TIGHT_RESERVE,
    )
    records = read_events(log.path)
    summary = _records_of(log.path, "compaction/summary")[0]
    rng = summary.payload["shadowed_range"]
    assert isinstance(rng, dict)

    summary_call = next(messages for messages, tools in provider.calls if not tools)
    contents = [message.content for message in summary_call]
    body = contents[1:-1]

    in_range = [record for record in records if rng["start"] <= record.seq <= rng["end"]]
    tail = [record for record in records if record.seq > rng["end"]]
    range_contents = _contents_of(in_range)
    tail_contents = _contents_of(tail)

    assert contents[0].startswith(SYSTEM_PROMPT)
    assert contents[-1] == SUMMARY_INSTRUCTION
    assert BIG_TEXT in contents, "要被摘要的那段回复不在摘要请求里"
    assert tail_contents, f"保留尾部为空，这条判据没有意义：{rng}"
    assert not [content for content in body if content in tail_contents], (
        f"保留尾部进了摘要请求：rng={rng} 尾部 seq={[r.seq for r in tail]}"
    )
    assert all(content in range_contents for content in body), (
        f"摘要请求里有区间外的消息：rng={rng}"
    )


# 一条 12000 字符的回复（3000 个估算 token）与一条 268000 字符的回复（67000 个）：
# 两组工具往返都在本次遮蔽范围里，合起来超过「窗口减保留额」这条上限（70000 - 100 = 69900）。
_ROUND_ONE_TEXT = "x" * 12000
_ROUND_TWO_TEXT = "x" * 268000


def _round_turn(call_id: str, text: str) -> dict[str, object]:
    return {
        "content": text,
        "finish_reason": "tool_calls",
        "tool_calls": [{"id": call_id, "name": "read", "arguments": {"file_path": "a.md"}}],
    }


async def test_the_summary_trim_drops_whole_round_trips(tmp_path: Path) -> None:
    """seam ①：摘要请求装不下时按往返整对丢——留下的 tool 消息不能没有请求它的那条 assistant。"""
    (tmp_path / "a.md").write_text("x" * 400, encoding="utf-8")
    provider = _RecordingProvider(
        [
            _round_turn("c1", _ROUND_ONE_TEXT),
            _round_turn("c2", _ROUND_TWO_TEXT),
            _summary_entry(),
            DONE_ENTRY,
        ]
    )
    await run_session_fixture(
        tmp_path,
        "s-trim-in-pairs",
        provider,
        max_turns=4,
        window=TIGHT_WINDOW,
        reserve=TIGHT_RESERVE,
    )

    summary_call = next(messages for messages, tools in provider.calls if not tools)
    requested: set[str] = set()
    for message in summary_call:
        for call in message.tool_calls:
            requested.add(str(call["id"]))
        if message.role == "tool":
            assert message.tool_call_id in requested, (
                f"裁剪把一组工具往返拆开了：{[message.role for message in summary_call]}"
            )
    assert len(summary_call) > 2, "裁到只剩头部与指令等于这次压缩什么都没做"


# 一条 300000 字符的回复（75000 个估算 token）与一份 2000 行、每行 150 字符的文件：
# 两条都超过「窗口减保留额」这条上限（70000 - 100 = 69900）。
HUGE_TEXT = "x" * 300000
HUGE_FILE_LINES = 2000
HUGE_FILE_WIDTH = 150


def _huge_turn() -> dict[str, object]:
    return {
        "content": HUGE_TEXT,
        "finish_reason": "tool_calls",
        "tool_calls": [{"id": "c1", "name": "read", "arguments": {"file_path": "a.md"}}],
    }


async def test_a_summary_request_that_cannot_be_made_to_fit_is_never_sent(tmp_path: Path) -> None:
    """seam ①：遮蔽范围裁到只剩一条也超「窗口减保留额」时不发请求，直接塌成溢出。"""
    (tmp_path / "a.md").write_text(
        "\n".join(f"{n:04d}{'x' * (HUGE_FILE_WIDTH - 4)}" for n in range(HUGE_FILE_LINES)),
        encoding="utf-8",
    )
    log, outcome = await run_fixture_session(
        tmp_path,
        "s-summary-too-big",
        [_huge_turn(), _summary_entry(), DONE_ENTRY],
        max_turns=3,
        window=TIGHT_WINDOW,
        reserve=TIGHT_RESERVE,
    )
    records = read_events(log.path)

    assert _records_of(log.path, "compaction/summary") == []
    assert [r for r in records if r.payload.get("purpose") == "compaction"] == []
    assert _records_of(log.path, "error/model") == []
    assert [record.type for record in records][-4:] == [
        "error/context",
        "turn/end",
        "segment/end",
        "session/end",
    ]
    assert outcome.stop_reason == "CONTEXT_WINDOW_EXCEEDED"
    assert outcome.failure_code == "CONTEXT_WINDOW_EXCEEDED"


_FIXTURE_DIR = Path(__file__).parent / "fixtures" / "real_endpoint"


async def test_the_compaction_record_has_the_keys_the_real_run_wrote(tmp_path: Path) -> None:
    """seam ①：`compaction/summary` 的 payload 键与真端点那一次真写出来的那份一致。

    fixture 来自真 session（来源见 `tests/fixtures/real_endpoint/README.md`）。遮蔽反馈那一行
    （seam ⑥）只读这四个键——键名在这里钉住，实现与屏幕两边不必互相猜。
    """
    real = json.loads((_FIXTURE_DIR / "compaction_summary.json").read_text(encoding="utf-8"))
    log, _ = await run_fixture_session(
        tmp_path,
        "s-record-shape",
        [_big_turn(), _summary_entry(), DONE_ENTRY],
        max_turns=3,
        window=TIGHT_WINDOW,
        reserve=TIGHT_RESERVE,
    )

    written = _records_of(log.path, "compaction/summary")[0]
    assert set(written.payload) == set(real["payload"])
    assert set(written.payload["shadowed_range"]) == set(real["payload"]["shadowed_range"])
    assert isinstance(written.payload["tokens_before"], int)
    assert isinstance(written.payload["tokens_after"], int)
    assert isinstance(written.payload["summary"], str) and written.payload["summary"]
