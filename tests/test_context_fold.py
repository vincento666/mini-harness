"""seam ④：从事件日志折叠出当前上下文。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from mini_harness.events import EventLog, EventRecord
from mini_harness.events.fold import SYSTEM_PROMPT, fold
from mini_harness.events.reader import read_events

_SESSION_ID = "s-fold"


def _rec(seq: int, event_type: str, payload: dict[str, Any]) -> EventRecord:
    return EventRecord(
        schema_version=1,
        type=event_type,
        session_id=_SESSION_ID,
        seq=seq,
        ts=f"2026-10-15T00:00:{seq:02d}+00:00",
        payload=payload,
    )


def _one_turn_events(
    *,
    append_system_prompt: str = "",
    tools: tuple[str, ...] = (),
) -> list[EventRecord]:
    start_payload = {"append_system_prompt": append_system_prompt, "tools": list(tools)}
    return [
        _rec(0, "session/start", start_payload),
        _rec(1, "turn/start", {"turn_id": "t1"}),
        _rec(
            2,
            "model/response",
            {"turn_id": "t1", "content": "hi", "tool_calls": [], "finish_reason": "stop"},
        ),
        _rec(3, "turn/end", {"turn_id": "t1", "stop_reason": "MODEL_COMPLETED"}),
    ]


def test_the_tool_block_in_the_header_comes_from_session_start() -> None:
    from_log = fold(_one_turn_events(tools=("read", "grep")))
    without = fold(_one_turn_events())

    assert "可用工具" in from_log.messages[0].content
    assert "read" in from_log.messages[0].content
    assert "grep" in from_log.messages[0].content
    assert "可用工具" not in without.messages[0].content
    assert from_log.header_fingerprint != without.header_fingerprint


def test_header_fingerprint_tracks_the_header_not_the_conversation() -> None:
    events = _one_turn_events()

    plain = fold(events)
    with_extra = fold(_one_turn_events(append_system_prompt="额外规则"))
    longer = fold(
        [
            *events,
            _rec(
                4,
                "model/response",
                {"turn_id": "t2", "content": "再说一句", "tool_calls": [], "finish_reason": "stop"},
            ),
        ]
    )

    assert plain.header_fingerprint != with_extra.header_fingerprint
    assert longer.header_fingerprint == plain.header_fingerprint
    assert len(longer.messages) > len(plain.messages)


def test_user_prompt_is_the_first_body_message_after_the_header() -> None:
    events = [
        _rec(
            0,
            "session/start",
            {"prompt": "写一份报告", "provider": "mock", "max_turns": 8, "workspace": "C:/ws"},
        ),
        *_one_turn_events()[1:],
    ]

    context = fold(events)

    assert context.messages[0].role == "system"
    assert context.messages[1].role == "user"
    assert context.messages[1].content == "写一份报告"


def test_folding_the_same_events_twice_gives_identical_results() -> None:
    events = _one_turn_events()

    first = fold(events)
    second = fold([record.model_copy(deep=True) for record in events])

    assert first == second
    assert first.header_fingerprint == second.header_fingerprint


def test_fold_puts_the_system_prompt_first_and_keeps_the_body_in_order() -> None:
    events = [
        _rec(0, "turn/start", {"turn_id": "t1"}),
        _rec(
            1,
            "model/response",
            {
                "turn_id": "t1",
                "content": "thinking",
                "tool_calls": [
                    {"id": "call-1", "name": "read", "arguments": {"file_path": "a.md"}}
                ],
                "finish_reason": "tool_calls",
            },
        ),
        _rec(2, "tool/call", {"turn_id": "t1", "tool_call_id": "call-1", "name": "read"}),
        _rec(
            3, "tool/result", {"turn_id": "t1", "tool_call_id": "call-1", "outcome": "UNKNOWN_TOOL"}
        ),
        _rec(
            4,
            "model/response",
            {"turn_id": "t1", "content": "done", "tool_calls": [], "finish_reason": "stop"},
        ),
        _rec(5, "turn/end", {"turn_id": "t1", "stop_reason": "MODEL_COMPLETED"}),
    ]

    context = fold(events)

    assert context.messages[0].role == "system"
    assert context.messages[0].content == SYSTEM_PROMPT
    assert [message.role for message in context.messages[1:]] == ["assistant", "tool", "assistant"]
    assert context.messages[1].tool_calls[0]["name"] == "read"
    assert context.messages[2].tool_call_id == "call-1"
    assert context.messages[2].content == "UNKNOWN_TOOL"
    assert context.messages[3].content == "done"


def test_header_cannot_be_replaced_by_conversation_content() -> None:
    events = [
        _rec(
            0,
            "model/response",
            {"turn_id": "t1", "content": SYSTEM_PROMPT, "tool_calls": [], "finish_reason": "stop"},
        ),
    ]

    context = fold(events)

    assert context.messages[0].role == "system"
    assert context.messages[0].content == SYSTEM_PROMPT
    assert context.messages[1].role == "assistant"
    assert context.messages[1].content == SYSTEM_PROMPT


def test_append_system_prompt_is_appended_after_the_builtin_constant() -> None:
    context = fold(_one_turn_events(append_system_prompt="额外规则"))

    assert context.messages[0].role == "system"
    assert context.messages[0].content.startswith(SYSTEM_PROMPT)
    assert context.messages[0].content.endswith("额外规则")


def test_long_conversation_is_folded_without_truncation() -> None:
    events = [
        _rec(
            index,
            "model/response",
            {
                "turn_id": f"t{index}",
                "content": f"m{index}",
                "tool_calls": [],
                "finish_reason": "stop",
            },
        )
        for index in range(50)
    ]

    context = fold(events)

    assert [message.content for message in context.messages[1:]] == [
        f"m{index}" for index in range(50)
    ]
    assert "CONTEXT_WINDOW_EXCEEDED" not in context.model_dump_json()


def test_cold_start_fold_matches_the_recorded_context_assembled(tmp_path: Path) -> None:
    log = EventLog.create(session_dir=tmp_path, session_id="s-cold")
    log.append("session/start", {})
    log.append("turn/start", {"turn_id": "t1"})
    log.append(
        "model/response",
        {"turn_id": "t1", "content": "hi", "tool_calls": [], "finish_reason": "stop"},
    )
    assembled = fold(read_events(log.path))
    log.append("context/assembled", assembled.model_dump(mode="json"))
    log.append("model/request", {"turn_id": "t1"})
    log.append("turn/end", {"turn_id": "t1", "stop_reason": "MODEL_COMPLETED"})
    log.append("session/end", {"stop_reason": "MODEL_COMPLETED"})

    replayed = fold(read_events(log.path))

    recorded = next(
        json.loads(line)["payload"]
        for line in log.path.read_text(encoding="utf-8").splitlines()
        if json.loads(line)["type"] == "context/assembled"
    )
    assert replayed.model_dump(mode="json") == recorded


def test_model_retry_is_a_fact_that_does_not_enter_the_context(tmp_path: Path) -> None:
    """`model/retry` 进词表、进日志，但不进上下文：重算前缀必须逐字段相等。"""
    log = EventLog.create(session_dir=tmp_path, session_id="s-retry-fold")
    log.append("session/start", {})
    log.append("turn/start", {"turn_id": "t1"})
    prefix = fold(read_events(log.path))
    log.append("context/assembled", prefix.model_dump(mode="json"))
    log.append("model/request", {"turn_id": "t1"})
    log.append("model/retry", {"turn_id": "t1", "attempt": 1, "status": 429})
    log.append(
        "model/response",
        {"turn_id": "t1", "content": "hi", "tool_calls": [], "finish_reason": "stop"},
    )
    log.append("turn/end", {"turn_id": "t1", "stop_reason": "MODEL_COMPLETED"})
    log.append("session/end", {"stop_reason": "MODEL_COMPLETED"})

    records = read_events(log.path)
    assert isinstance(records, list)
    index = next(i for i, record in enumerate(records) if record.type == "context/assembled")

    recomputed = fold(records[:index])
    assert recomputed.model_dump(mode="json") == records[index].payload

    without_retry = [record for record in records if record.type != "model/retry"]
    assert fold(without_retry).model_dump(mode="json") == fold(records).model_dump(mode="json")


def test_an_unanswered_approval_request_leaves_the_fold_unchanged() -> None:
    """半对（有 `approval/request`、没有 `approval/response`）只允许出现在取消收尾的 session 里。

    折叠读的是结果、不是问答：缺一条结论不改变上下文，也不让折叠崩。
    """
    arguments = {"file_path": "a.md"}
    asked = [
        _rec(0, "session/start", {}),
        _rec(1, "turn/start", {"turn_id": "t1"}),
        _rec(
            2,
            "tool/call",
            {"turn_id": "t1", "tool_call_id": "c1", "name": "write", "arguments": arguments},
        ),
        _rec(
            3,
            "approval/request",
            {"turn_id": "t1", "tool_call_id": "c1", "name": "write", "arguments": arguments},
        ),
        _rec(
            4, "approval/response", {"turn_id": "t1", "tool_call_id": "c1", "decision": "APPROVED"}
        ),
        _rec(
            5,
            "tool/result",
            {"turn_id": "t1", "tool_call_id": "c1", "outcome": "OK", "content": "写了"},
        ),
        _rec(6, "turn/end", {"turn_id": "t1", "stop_reason": "TOOL_CALLS"}),
    ]
    half_pair = [record for record in asked if record.type != "approval/response"]

    assert fold(half_pair).model_dump(mode="json") == fold(asked).model_dump(mode="json")
