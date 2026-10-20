"""seam ①：窗口预算——触发线公式、估算 token、预算读数的两个来源。"""

from __future__ import annotations

from typing import Any

from mini_harness.context.budget import budget_reading, estimate_tokens, trigger_line
from mini_harness.events import EventRecord
from mini_harness.events.fold import Message

_SESSION_ID = "s-budget"

# 规格里写死的数值：默认窗口 128000、默认预留 8192、headroom 常量 65536。
DEFAULT_WINDOW = 128000
DEFAULT_RESERVE = 8192
HEADROOM = 65536


def _rec(seq: int, event_type: str, payload: dict[str, Any]) -> EventRecord:
    return EventRecord(
        schema_version=1,
        type=event_type,
        session_id=_SESSION_ID,
        seq=seq,
        ts=f"2026-10-21T00:00:{seq:02d}+00:00",
        payload=payload,
    )


def _start() -> EventRecord:
    return _rec(0, "session/start", {"prompt": "任务", "provider": "mock", "max_turns": 8})


def _response(seq: int, *, usage: dict[str, int], purpose: str | None = None) -> EventRecord:
    payload: dict[str, Any] = {
        "turn_id": "t1",
        "content": "回复",
        "tool_calls": [],
        "finish_reason": "stop",
        "usage": usage,
    }
    if purpose is not None:
        payload["purpose"] = purpose
    return _rec(seq, "model/response", payload)


def test_the_trigger_line_is_the_formula_with_the_locked_constants() -> None:
    """默认参数下触发线是 54272：`W - O - 65536` 这一支比 `W * 0.8` 小。"""
    assert trigger_line(DEFAULT_WINDOW, DEFAULT_RESERVE) == 54272
    assert int(DEFAULT_WINDOW * 0.8) > DEFAULT_WINDOW - DEFAULT_RESERVE - HEADROOM


def test_the_trigger_line_takes_the_smaller_of_the_two_branches() -> None:
    """窗口大到 `W * 0.8` 反而更小时取它，且 `floor` 生效（320000.8 → 320000）。"""
    assert trigger_line(400000, DEFAULT_RESERVE) == 320000
    assert trigger_line(400001, 1) == 320000


def test_the_trigger_line_is_never_negative() -> None:
    """小窗口下 `W - O - 65536` 为负：触发线是 0，每一次装配都算越线。"""
    assert trigger_line(2000, DEFAULT_RESERVE) == 0
    assert trigger_line(1, 1) == 0


def test_estimation_counts_content_and_tool_call_arguments() -> None:
    """上下文里最贵的常是模型请求的 `write` 参数：只算 `content` 会把它算成 0。"""
    big_arguments = Message(
        role="assistant",
        content="",
        tool_calls=[{"id": "c1", "name": "write", "arguments": {"content": "x" * 400}}],
    )

    assert estimate_tokens([Message(role="assistant", content="")]) == 0
    assert estimate_tokens([big_arguments]) >= 100


def test_estimation_rounds_each_message_up_then_adds() -> None:
    """逐条除以 4 向上取整再相加，不是把总字符数一次性除以 4。"""
    assert estimate_tokens([Message(role="user", content="abcd")]) == 1
    assert estimate_tokens([Message(role="user", content="")]) == 0
    assert (
        estimate_tokens([Message(role="user", content="a"), Message(role="user", content="b")]) == 2
    )


def test_a_reported_input_token_count_is_a_floor_for_the_reading() -> None:
    events = [_start(), _response(1, usage={"input_tokens": 900, "output_tokens": 10})]
    messages = [Message(role="system", content="头部"), Message(role="user", content="任务")]

    assert estimate_tokens(messages) < 900
    assert budget_reading(events, messages) == 900


def test_the_summary_call_report_does_not_calibrate_later_turns() -> None:
    """摘要那次调用量的是被遮蔽的那一大段：拿它当读数会让压缩之后每一回合都再压缩。"""
    events = [
        _start(),
        _response(1, usage={"input_tokens": 900, "output_tokens": 10}),
        _response(2, usage={"input_tokens": 5000, "output_tokens": 20}, purpose="compaction"),
    ]
    messages = [Message(role="system", content="头部"), Message(role="user", content="任务")]

    assert budget_reading(events, messages) == 900


def test_without_any_report_the_reading_is_the_estimate() -> None:
    events = [_start()]
    messages = [Message(role="system", content="头部"), Message(role="user", content="任务")]

    assert budget_reading(events, messages) == estimate_tokens(messages)


def test_the_reading_over_the_same_prefix_is_the_same_twice() -> None:
    events = [
        _start(),
        _response(1, usage={"input_tokens": 700, "output_tokens": 10}),
        _response(2, usage={"input_tokens": 800, "output_tokens": 10}),
    ]
    messages = [Message(role="system", content="头部"), Message(role="user", content="任务")]

    first = budget_reading(events, messages)
    second = budget_reading([record.model_copy(deep=True) for record in events], messages)

    assert first == second == 800


def test_the_reading_ignores_events_after_the_assembly_point() -> None:
    """读数只取自该装配点之前的前缀：测试用「前缀切片」表达这条边界。"""
    events = [_start(), _response(1, usage={"input_tokens": 900, "output_tokens": 10})]
    messages = [Message(role="system", content="头部"), Message(role="user", content="任务")]

    assert budget_reading(events[:1], messages) == estimate_tokens(messages)
    assert budget_reading(events, messages) == 900
