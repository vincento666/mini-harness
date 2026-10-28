"""窗口预算的算术：`context/budget.py` 的纯函数直接判。
seam ① 的回合循环判据在 `tests/test_turn_compaction.py`，这里不开新的缝。"""

from __future__ import annotations

from typing import Any

from mini_harness.context.budget import (
    budget_reading,
    estimate_tokens,
    pressure_budget,
    retain_line,
    shadowed_range,
    trigger_line,
)
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


def test_trigger_line_accepts_custom_ratio_and_headroom() -> None:
    assert (
        trigger_line(
            100000,
            1000,
            threshold_ratio=0.5,
            headroom_tokens=1000,
        )
        == 50000
    )


def test_retain_line_prefers_tokens_and_falls_back_to_ratio() -> None:
    assert retain_line(100000, retain_ratio=0.10, retain_tokens=3000) == 3000
    assert retain_line(100000, retain_ratio=0.10, retain_tokens=0) == 10000


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


def test_the_pressure_budget_is_the_window_minus_the_reserve() -> None:
    """溢出判据的量纲是「窗口减保留额」，不是触发线：70000 / 100 下三个数各是各的。"""
    assert pressure_budget(DEFAULT_WINDOW, DEFAULT_RESERVE) == 119808
    assert pressure_budget(70000, 100) == 69900
    assert pressure_budget(100000, 100) == 99900
    assert trigger_line(70000, 100) == 4364
    assert retain_line(70000) == 11200


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


def _big(seq: int, chars: int) -> EventRecord:
    return _rec(
        seq,
        "model/response",
        {
            "turn_id": f"t{seq}",
            "content": "x" * chars,
            "tool_calls": [],
            "finish_reason": "stop",
        },
    )


def _tool_round(
    seq: int, *, content_chars: int, call_id: str, result_chars: int
) -> list[EventRecord]:
    """一条 assistant 工具请求加它的 `tool/call` 与 `tool/result`：切点不许落在这一组里。"""
    arguments = {"file_path": "a.md"}
    return [
        _rec(
            seq,
            "model/response",
            {
                "turn_id": f"t{seq}",
                "content": "x" * content_chars,
                "tool_calls": [{"id": call_id, "name": "read", "arguments": arguments}],
                "finish_reason": "tool_calls",
            },
        ),
        _rec(
            seq + 1,
            "tool/call",
            {"turn_id": f"t{seq}", "tool_call_id": call_id, "name": "read", "arguments": arguments},
        ),
        _rec(
            seq + 2,
            "tool/result",
            {
                "turn_id": f"t{seq}",
                "tool_call_id": call_id,
                "outcome": "OK",
                "content": "y" * result_chars,
            },
        ),
    ]


def test_a_shadowed_measurement_stops_calibrating() -> None:
    """遮蔽之后，那段里的读数不再描述当前表层：它不参与校准，否则压缩永远救不回来。"""
    events = [
        _start(),
        _response(1, usage={"input_tokens": 5000, "output_tokens": 10}),
        _rec(
            2,
            "compaction/summary",
            {
                "turn_id": "t2",
                "shadowed_range": {"start": 1, "end": 1},
                "summary": "摘要",
                "tokens_before": 5000,
                "tokens_after": 20,
            },
        ),
    ]
    messages = [
        Message(role="system", content="头部"),
        Message(role="user", content="任务"),
        Message(role="system", content="摘要"),
    ]

    assert budget_reading(events, messages) == estimate_tokens(messages)


def test_the_retain_budget_is_sixteen_percent_of_the_window() -> None:
    assert retain_line(DEFAULT_WINDOW) == 20480
    assert retain_line(1000) == 160


def test_shadowed_range_follows_retain_tokens() -> None:
    events = [_start(), _big(1, 100000), _big(2, 4000)]

    assert shadowed_range(events, 100000) == {"start": 1, "end": 1}
    assert shadowed_range(events, 100000, retain_tokens=30000) is None


def test_the_shadowed_range_covers_the_oldest_body_and_keeps_the_tail() -> None:
    """遮蔽的是最老的那段对话体；`session/start`（seq 0）不在范围里。"""
    events = [
        _start(),
        _rec(1, "turn/start", {"turn_id": "t1"}),
        _big(2, 100000),
        _rec(3, "turn/end", {"turn_id": "t1", "stop_reason": "MODEL_COMPLETED"}),
        _big(4, 4000),
    ]

    assert shadowed_range(events, DEFAULT_WINDOW) == {"start": 1, "end": 2}


def test_the_cut_never_splits_an_assistant_request_from_its_tool_round() -> None:
    """朴素切点会落在 seq 3 的 `tool/call` 上，把 seq 2 那条 assistant 请求与它的结果拆开。

    整组一起遮蔽。
    """
    events = [
        _start(),
        _rec(1, "turn/start", {"turn_id": "t1"}),
        *_tool_round(2, content_chars=100000, call_id="c1", result_chars=4000),
        _rec(5, "turn/end", {"turn_id": "t1", "stop_reason": "TOOL_CALLS"}),
        _big(6, 10000),
    ]

    assert shadowed_range(events, DEFAULT_WINDOW) == {"start": 1, "end": 4}


def test_an_existing_summary_is_never_inside_the_range() -> None:
    """遮蔽既有摘要等于丢掉上一份摘要，而摘要链是压缩后仅存的长程记忆。"""
    events = [
        _start(),
        _big(1, 100000),
        _rec(
            2,
            "compaction/summary",
            {
                "turn_id": "t2",
                "shadowed_range": {"start": 1, "end": 1},
                "summary": "上一份摘要",
                "tokens_before": 25000,
                "tokens_after": 40,
            },
        ),
        _big(3, 100000),
        _big(4, 4000),
    ]

    reading = shadowed_range(events, DEFAULT_WINDOW)

    assert reading is not None
    assert reading["start"] > 2


def test_nothing_to_shadow_returns_none() -> None:
    """对话体里只剩一条本身就超预算的记录：遮蔽它之后什么都不剩。"""
    events = [
        _start(),
        _rec(1, "turn/start", {"turn_id": "t1"}),
        _big(2, 100000),
    ]

    assert shadowed_range(events, DEFAULT_WINDOW) is None


def test_a_lone_tool_round_that_does_not_fit_returns_none() -> None:
    """整组装不下时不许把组拆开，也不许把整组拉进尾部：没有可遮蔽的内容。"""
    events = [
        _start(),
        _rec(1, "turn/start", {"turn_id": "t1"}),
        *_tool_round(2, content_chars=100000, call_id="c1", result_chars=4000),
    ]

    assert shadowed_range(events, DEFAULT_WINDOW) is None


def test_shadowing_only_bookkeeping_records_is_nothing_to_shadow() -> None:
    """遮蔽范围里没有任何产出消息的记录，这次压缩就没有意义。"""
    events = [
        _start(),
        _rec(1, "turn/start", {"turn_id": "t1"}),
        _rec(2, "turn/end", {"turn_id": "t1", "stop_reason": "MODEL_COMPLETED"}),
        _big(3, 4000),
    ]

    assert shadowed_range(events, 1000) is None


def test_the_tail_budget_is_counted_in_tokens_not_characters() -> None:
    """保留预算量的是 token：尾部那条记录按 token 计，不是把它的字符数当成 token 数。

    窗口 9375 → 保留预算 1500 token。尾部两条是 4000 字符（1000 token）与 100 字符（25 token），
    合计 1025 token 装得下，于是没有可遮蔽的内容。把 4000 个字符当成 4000 token 累加，
    走到第二条就断在 1500 上，遮蔽范围会凭空冒出来。
    """
    events = [
        _start(),
        _rec(1, "turn/start", {"turn_id": "t1"}),
        _big(2, 100),
        _rec(3, "turn/end", {"turn_id": "t1", "stop_reason": "TOOL_CALLS"}),
        _rec(4, "turn/start", {"turn_id": "t2"}),
        _big(5, 4000),
    ]

    assert retain_line(9375) == 1500
    assert shadowed_range(events, 9375) is None
