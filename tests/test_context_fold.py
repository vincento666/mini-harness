"""seam ④：从事件日志折叠出当前上下文。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from mini_harness.config import build_registry
from mini_harness.events import EventLog, EventRecord
from mini_harness.events.fold import (
    SYSTEM_PROMPT,
    TOOL_OUTCOME_UNKNOWN,
    AssembledContext,
    assembly_points,
    fold,
    fold_range,
)
from mini_harness.events.reader import read_events
from tool_harness import DONE, run_fixture_session

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


def test_a_user_message_folds_into_the_conversation_in_seq_order() -> None:
    """REPL 的输入是一条 `user/message` 记录：折成 `role: user` 消息，按 `seq` 进对话体。"""
    events = [
        _rec(0, "session/start", {"append_system_prompt": "", "tools": [], "prompt": ""}),
        _rec(1, "segment/start", {"segment_id": "s1"}),
        _rec(2, "user/message", {"segment_id": "s1", "content": "第一条输入"}),
        _rec(3, "turn/start", {"turn_id": "t1"}),
        _rec(
            4,
            "model/response",
            {"turn_id": "t1", "content": "回答一", "tool_calls": [], "finish_reason": "stop"},
        ),
        _rec(5, "turn/end", {"turn_id": "t1", "stop_reason": "MODEL_COMPLETED"}),
        _rec(6, "segment/end", {"segment_id": "s1", "stop_reason": "MODEL_COMPLETED", "turns": 1}),
        _rec(7, "segment/start", {"segment_id": "s2"}),
        _rec(8, "user/message", {"segment_id": "s2", "content": "第二条输入"}),
        _rec(9, "turn/start", {"turn_id": "t2"}),
        _rec(
            10,
            "model/response",
            {"turn_id": "t2", "content": "回答二", "tool_calls": [], "finish_reason": "stop"},
        ),
        _rec(11, "turn/end", {"turn_id": "t2", "stop_reason": "MODEL_COMPLETED"}),
        _rec(12, "segment/end", {"segment_id": "s2", "stop_reason": "MODEL_COMPLETED", "turns": 1}),
    ]

    context = fold(events)

    assert context.messages[0].role == "system"
    assert [(message.role, message.content) for message in context.messages[1:]] == [
        ("user", "第一条输入"),
        ("assistant", "回答一"),
        ("user", "第二条输入"),
        ("assistant", "回答二"),
    ]


def _one_turn_with_segments() -> list[EventRecord]:
    """同一个回合，外面套一段：段的边界是记账记录。"""
    return [
        _rec(0, "session/start", {"append_system_prompt": "", "tools": []}),
        _rec(1, "segment/start", {"segment_id": "s1"}),
        _rec(2, "turn/start", {"turn_id": "t1"}),
        _rec(
            3,
            "model/response",
            {"turn_id": "t1", "content": "hi", "tool_calls": [], "finish_reason": "stop"},
        ),
        _rec(4, "turn/end", {"turn_id": "t1", "stop_reason": "MODEL_COMPLETED"}),
        _rec(5, "segment/end", {"segment_id": "s1", "stop_reason": "MODEL_COMPLETED", "turns": 1}),
    ]


def test_segment_records_produce_no_messages() -> None:
    """`segment/start` 与 `segment/end` 与 `turn/*` 一样不产出消息：加与不加，折叠结果相同。"""
    without = fold(_one_turn_events())
    with_segments = fold(_one_turn_with_segments())

    assert [message.role for message in with_segments.messages] == [
        message.role for message in without.messages
    ]
    assert with_segments.messages == without.messages
    assert with_segments.header_fingerprint == without.header_fingerprint


def test_a_shadowed_user_message_does_not_enter_the_conversation() -> None:
    """被遮蔽的输入不进对话体；遮蔽段的边界对折叠结果没有效果。"""
    shadowed = [
        _rec(0, "session/start", {"append_system_prompt": "", "tools": [], "prompt": ""}),
        _rec(1, "segment/start", {"segment_id": "s1"}),
        _rec(2, "user/message", {"segment_id": "s1", "content": "第一条输入"}),
        _rec(3, "turn/start", {"turn_id": "t1"}),
        _rec(
            4,
            "model/response",
            {"turn_id": "t1", "content": "回答一", "tool_calls": [], "finish_reason": "stop"},
        ),
        _rec(5, "turn/end", {"turn_id": "t1", "stop_reason": "MODEL_COMPLETED"}),
        _rec(6, "segment/end", {"segment_id": "s1", "stop_reason": "MODEL_COMPLETED", "turns": 1}),
        _rec(
            7,
            "compaction/summary",
            {
                "turn_id": "t2",
                "shadowed_range": {"start": 1, "end": 6},
                "summary": "第一段已被摘要",
                "tokens_before": 900,
                "tokens_after": 300,
            },
        ),
        _rec(8, "segment/start", {"segment_id": "s2"}),
        _rec(9, "user/message", {"segment_id": "s2", "content": "第二条输入"}),
        _rec(10, "turn/start", {"turn_id": "t2"}),
        _rec(
            11,
            "model/response",
            {"turn_id": "t2", "content": "回答二", "tool_calls": [], "finish_reason": "stop"},
        ),
        _rec(12, "turn/end", {"turn_id": "t2", "stop_reason": "MODEL_COMPLETED"}),
    ]

    context = fold(shadowed)
    # 遮蔽范围只盖正文（不盖段的边界）时，折叠结果必须一模一样。
    body_only = [
        record.model_copy(
            update={"payload": {**record.payload, "shadowed_range": {"start": 2, "end": 5}}}
        )
        if record.type == "compaction/summary"
        else record
        for record in shadowed
    ]

    assert [(message.role, message.content) for message in context.messages[1:]] == [
        ("user", "第二条输入"),
        ("system", "第一段已被摘要"),
        ("assistant", "回答二"),
    ]
    assert fold(body_only).messages == context.messages


def test_folding_the_same_events_twice_gives_identical_results() -> None:
    events = _one_turn_events()

    first = fold(events)
    second = fold([record.model_copy(deep=True) for record in events])

    assert first == second
    assert first.header_fingerprint == second.header_fingerprint


def _half_log_events() -> list[EventRecord]:
    """构造的半截日志：`call-2` 的 `tool/call` 落了盘却没有结果，之后还有既有消息。"""
    return [
        _rec(0, "turn/start", {"turn_id": "t1"}),
        _rec(
            1,
            "model/response",
            {
                "turn_id": "t1",
                "content": "读两个文件",
                "tool_calls": [
                    {"id": "call-1", "name": "read", "arguments": {"file_path": "a.md"}},
                    {"id": "call-2", "name": "read", "arguments": {"file_path": "b.md"}},
                ],
                "finish_reason": "tool_calls",
            },
        ),
        _rec(2, "tool/call", {"turn_id": "t1", "tool_call_id": "call-1", "name": "read"}),
        _rec(
            3,
            "tool/result",
            {"turn_id": "t1", "tool_call_id": "call-1", "outcome": "OK", "content": "甲\n"},
        ),
        _rec(4, "tool/call", {"turn_id": "t1", "tool_call_id": "call-2", "name": "read"}),
        _rec(5, "turn/end", {"turn_id": "t1", "stop_reason": "ABORTED"}),
        _rec(
            6,
            "model/response",
            {"turn_id": "t2", "content": "接着说", "tool_calls": [], "finish_reason": "stop"},
        ),
    ]


def test_an_unpaired_tool_call_folds_into_a_derived_closer() -> None:
    """规格 scenario「半截日志折叠补出闭合」：有 `tool/call` 没 `tool/result` 时折叠补一条。

    闭合消息排在它该在的位置——assistant 请求之后、该点之后的既有消息之前，不追加到末尾。
    """
    context = fold(_half_log_events())

    assert [message.role for message in context.messages[1:]] == [
        "assistant",
        "tool",
        "tool",
        "assistant",
    ]
    closer = context.messages[3]
    assert closer.tool_call_id == "call-2"
    assert closer.content == "TOOL_OUTCOME_UNKNOWN"
    assert context.messages[4].content == "接着说"


def test_a_complete_log_derives_no_closer() -> None:
    """规格 scenario「完整日志不派生闭合」：配平的日志折叠出来没有一条 `TOOL_OUTCOME_UNKNOWN`。"""
    events = [
        *_half_log_events()[:5],
        _rec(
            5,
            "tool/result",
            {"turn_id": "t1", "tool_call_id": "call-2", "outcome": "OK", "content": "乙\n"},
        ),
        _rec(6, "turn/end", {"turn_id": "t1", "stop_reason": "MODEL_COMPLETED"}),
        _rec(
            7,
            "model/response",
            {"turn_id": "t2", "content": "接着说", "tool_calls": [], "finish_reason": "stop"},
        ),
    ]

    context = fold(events)

    assert [message.role for message in context.messages[1:]] == [
        "assistant",
        "tool",
        "tool",
        "assistant",
    ]
    assert [message.content for message in context.messages].count("TOOL_OUTCOME_UNKNOWN") == 0


def test_the_derived_closer_is_deterministic() -> None:
    """规格 scenario「派生闭合是确定性的」：同一份半截日志折叠两次逐字段相等。

    两份形状都要判：闭合被后面的消息冲掉的那一份，以及**以未配对的 `tool/call` 结尾**的那一份。
    后者的 pending 只能靠折叠收尾清掉——折叠要是把它存在进程里，第二次折叠就多一条闭合。
    """
    for events in (_half_log_events(), _half_log_events()[:-1]):
        first = fold(events).model_dump(mode="json")
        second = fold([record.model_copy(deep=True) for record in events]).model_dump(mode="json")
        assert first == second


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


async def test_a_fold_with_no_tools_still_matches_replay(tmp_path: Path) -> None:
    """工具表为空的一次 run：头部没有工具块，逐点重放仍与当时记录的上下文逐字段相等。"""
    log, _ = await run_fixture_session(
        tmp_path, "s-fold-notools", [DONE], registry=build_registry([])
    )
    records = read_events(log.path)

    assert next(r for r in records if r.type == "session/start").payload["tools"] == []
    points = 0
    for index, record in enumerate(records):
        if record.type != "context/assembled":
            continue
        points += 1
        # 记录里多带一个 `turn_id`：那是「哪一回合记录的」，不是上下文的一部分。
        recorded = {key: value for key, value in record.payload.items() if key != "turn_id"}
        assert fold(records[:index]).model_dump(mode="json") == recorded
    assert points == 1


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


# ---- M5：折叠 honor 遮蔽、摘要进表层、`purpose` 标记跳过 ----


def _compacted_events() -> list[EventRecord]:
    """一份压缩过的日志：seq 1 到 5 被遮蔽，保留尾部从 seq 7 起。"""
    return [
        _rec(0, "session/start", {"prompt": "写一份报告", "tools": ["read"]}),
        _rec(1, "turn/start", {"turn_id": "t1"}),
        _rec(
            2,
            "model/response",
            {"turn_id": "t1", "content": "第一段", "tool_calls": [], "finish_reason": "stop"},
        ),
        _rec(
            3,
            "tool/call",
            {
                "turn_id": "t1",
                "tool_call_id": "c1",
                "name": "read",
                "arguments": {"file_path": "a.md"},
            },
        ),
        _rec(
            4,
            "tool/result",
            {"turn_id": "t1", "tool_call_id": "c1", "outcome": "OK", "content": "结果一"},
        ),
        _rec(
            5,
            "model/response",
            {
                "turn_id": "t2",
                "content": "摘要文本",
                "tool_calls": [],
                "finish_reason": "stop",
                "purpose": "compaction",
            },
        ),
        _rec(
            6,
            "compaction/summary",
            {
                "turn_id": "t2",
                "shadowed_range": {"start": 1, "end": 5},
                "summary": "摘要文本",
                "tokens_before": 900,
                "tokens_after": 30,
            },
        ),
        _rec(
            7,
            "model/response",
            {"turn_id": "t2", "content": "第二段", "tool_calls": [], "finish_reason": "stop"},
        ),
    ]


def _contents(context: AssembledContext) -> list[str]:
    return [message.content for message in context.messages]


def test_shadowed_records_produce_no_messages() -> None:
    contents = _contents(fold(_compacted_events()))

    assert "第一段" not in contents
    assert "结果一" not in contents
    assert "第二段" in contents


def test_a_shadowed_tool_call_does_not_derive_a_closer() -> None:
    """被遮蔽的 `tool/call` 不进 pending：压缩不制造 `TOOL_OUTCOME_UNKNOWN`。"""
    contents = _contents(fold(_compacted_events()))

    assert TOOL_OUTCOME_UNKNOWN not in contents


def test_the_summary_sits_after_the_user_prompt() -> None:
    messages = fold(_compacted_events()).messages

    assert messages[0].role == "system"
    assert messages[1].role == "user"
    assert messages[1].content == "写一份报告"
    assert messages[2].role == "system"
    assert messages[2].content == "摘要文本"
    assert messages[3].role == "assistant"
    assert messages[3].content == "第二段"


def test_two_summaries_are_ordered_by_their_seq() -> None:
    events = [
        *_compacted_events(),
        _rec(
            8,
            "model/response",
            {
                "turn_id": "t3",
                "content": "第二份摘要正文",
                "tool_calls": [],
                "finish_reason": "stop",
                "purpose": "compaction",
            },
        ),
        _rec(
            9,
            "compaction/summary",
            {
                "turn_id": "t3",
                "shadowed_range": {"start": 7, "end": 8},
                "summary": "第二份摘要",
                "tokens_before": 800,
                "tokens_after": 40,
            },
        ),
    ]

    systems = [message.content for message in fold(events).messages if message.role == "system"]

    assert systems[1:] == ["摘要文本", "第二份摘要"]
    assert "第二段" not in [message.content for message in fold(events).messages]


def test_a_compaction_purpose_response_produces_no_assistant_message() -> None:
    messages = fold(_compacted_events()).messages

    assert [m.content for m in messages if m.role == "assistant"] == ["第二段"]
    assert sum(1 for m in messages if m.content == "摘要文本") == 1


def test_an_unmarked_response_still_produces_an_assistant_message() -> None:
    """同一份日志里既有普通回合回复又有压缩回复：只有带标记的那条不产出消息。"""
    events = [
        _rec(0, "session/start", {"prompt": "写一份报告", "tools": ["read"]}),
        _rec(
            1,
            "model/response",
            {"turn_id": "t1", "content": "普通回复", "tool_calls": [], "finish_reason": "stop"},
        ),
        _rec(
            2,
            "model/response",
            {
                "turn_id": "t2",
                "content": "摘要文本",
                "tool_calls": [],
                "finish_reason": "stop",
                "purpose": "compaction",
            },
        ),
    ]

    assert [m.content for m in fold(events).messages if m.role == "assistant"] == ["普通回复"]


def test_folding_a_compacted_log_is_deterministic_and_leaves_the_log_untouched() -> None:
    events = _compacted_events()
    before = [record.model_dump() for record in events]

    first = fold(events)
    second = fold([EventRecord(**payload) for payload in before])

    assert first == second
    assert [record.model_dump() for record in events] == before


def test_the_fold_at_each_point_sees_only_its_prefix() -> None:
    """遮蔽只来自该点之前已落盘的 `compaction/summary`：压缩之前的每个点折叠出完整对话。"""
    events = _compacted_events()

    before_compaction = fold(events[:6])
    after_compaction = fold(events)

    assert "第一段" in _contents(before_compaction)
    assert "结果一" in _contents(before_compaction)
    assert "第一段" not in _contents(after_compaction)


def test_assembly_points_carry_their_own_prefix_and_turn_id() -> None:
    """读方 API：装配点序列由事件层给出，每个点带着它自己的前缀与所属回合。

    重放方要的是「这条 `context/assembled` 之前发生过什么」，不是整份日志加下标——
    自己扫 `records`、按下标切前缀是摸事件层的内部形状（ADR-0002 第 3 条）。
    """
    records = [
        _rec(0, "session/start", {"prompt": "任务", "tools": []}),
        _rec(1, "segment/start", {"segment_id": "s1"}),
        _rec(2, "turn/start", {"turn_id": "t1"}),
        _rec(3, "context/assembled", {"turn_id": "t1", "messages": []}),
        _rec(4, "model/request", {"turn_id": "t1", "tools": []}),
        _rec(5, "model/response", {"turn_id": "t1", "content": "hi", "tool_calls": []}),
        _rec(6, "turn/end", {"turn_id": "t1", "stop_reason": "TOOL_CALLS"}),
        _rec(7, "turn/start", {"turn_id": "t2"}),
        _rec(8, "context/assembled", {"turn_id": "t2", "messages": []}),
        _rec(9, "turn/end", {"turn_id": "t2", "stop_reason": "MODEL_COMPLETED"}),
    ]

    points = assembly_points(records)

    assert [point.record.seq for point in points] == [3, 8]
    assert [point.turn_id for point in points] == ["t1", "t2"]
    # 前缀止于该点之前：该点自己与它之后的事件都不算进来。
    assert [record.seq for record in points[0].prefix] == [0, 1, 2]
    assert [record.seq for record in points[1].prefix] == [0, 1, 2, 3, 4, 5, 6, 7]


def test_an_assembly_point_without_a_turn_start_carries_an_empty_turn_id() -> None:
    """手写日志里装配点之前没有 `turn/start`：回合 id 是空串，不猜、不报错。"""
    records = [
        _rec(0, "session/start", {"prompt": "任务", "tools": []}),
        _rec(1, "context/assembled", {"turn_id": "", "messages": []}),
    ]

    assert [point.turn_id for point in assembly_points(records)] == [""]


def _range_events() -> list[EventRecord]:
    """一段够长的对话：seq 3 与 4 是本次要遮蔽的那一段，seq 6 是保留尾部。"""
    return [
        _rec(0, "session/start", {"prompt": "最早的那条人话", "tools": ["read"]}),
        _rec(1, "turn/start", {"turn_id": "t1"}),
        _rec(
            2,
            "model/response",
            {"turn_id": "t1", "content": "遮蔽区之前的回复", "tool_calls": []},
        ),
        _rec(3, "user/message", {"content": "要进摘要的那条输入"}),
        _rec(
            4,
            "model/response",
            {"turn_id": "t2", "content": "要进摘要的那段回复", "tool_calls": []},
        ),
        _rec(
            5,
            "tool/result",
            {
                "turn_id": "t2",
                "tool_call_id": "c1",
                "outcome": "OK",
                "content": "要进摘要的工具结果",
            },
        ),
        _rec(6, "user/message", {"content": "保留尾部的那条输入"}),
    ]


def test_folding_a_seq_range_yields_only_that_ranges_conversation() -> None:
    """seam ④：按 seq 闭区间折出对话——区间外的记录一条都不进来。"""
    messages = fold_range(_range_events(), start=3, end=5)

    assert [(message.role, message.content) for message in messages] == [
        ("user", "要进摘要的那条输入"),
        ("assistant", "要进摘要的那段回复"),
        ("tool", "要进摘要的工具结果"),
    ]


def test_a_seq_range_excludes_the_protected_events_it_covers() -> None:
    """区间把 `session/start` 与既有 `compaction/summary` 盖住时，它们不折成消息。"""
    records = [
        _rec(0, "session/start", {"prompt": "最早的那条人话", "tools": []}),
        _rec(1, "model/response", {"turn_id": "t1", "content": "第一段回复", "tool_calls": []}),
        _rec(
            2,
            "compaction/summary",
            {
                "turn_id": "t1",
                "shadowed_range": {"start": 1, "end": 1},
                "summary": "上一轮的摘要",
                "tokens_before": 40,
                "tokens_after": 10,
            },
        ),
        _rec(3, "model/response", {"turn_id": "t2", "content": "第二段回复", "tool_calls": []}),
    ]

    messages = fold_range(records, start=0, end=3)

    assert [message.content for message in messages] == ["第一段回复", "第二段回复"]
    assert [message.role for message in messages] == ["assistant", "assistant"]


def test_an_empty_seq_range_folds_to_no_messages() -> None:
    """起点大于终点的区间折出空对话，不报错也不猜。"""
    assert fold_range(_range_events(), start=5, end=4) == []
