"""seam ④：fold 从 blocks 重建 assistant 消息，旧日志不变。"""

from __future__ import annotations

from mini_harness.events import EventRecord
from mini_harness.events.fold import fold


def _record(payload: dict[str, object]) -> EventRecord:
    return EventRecord(
        schema_version=1,
        type="model/response",
        session_id="s1",
        seq=1,
        ts="2026-10-31T00:00:00+00:00",
        payload=payload,
    )


def _event(seq: int, event_type: str, payload: dict[str, object]) -> EventRecord:
    return EventRecord(
        schema_version=1,
        type=event_type,
        session_id="s1",
        seq=seq,
        ts=f"2026-10-31T00:00:{seq:02d}+00:00",
        payload=payload,
    )


def test_fold_rebuilds_ordered_blocks() -> None:
    message = fold(
        [
            _record(
                {
                    "turn_id": "t1",
                    "content": "答案",
                    "tool_calls": [],
                    "blocks": [
                        {"type": "reasoning", "text": "先想"},
                        {"type": "text", "text": "答案"},
                    ],
                    "finish_reason": "stop",
                }
            )
        ]
    ).messages[-1]

    assert [block["type"] for block in message.blocks] == ["reasoning", "text"]


def test_fold_without_blocks_keeps_the_old_projection() -> None:
    message = fold(
        [
            _record(
                {
                    "turn_id": "t1",
                    "content": "答案",
                    "tool_calls": [],
                    "finish_reason": "stop",
                }
            )
        ]
    ).messages[-1]

    assert message.content == "答案"
    assert message.blocks == []


def test_fold_includes_interrupted_anchor_but_ignores_attempt() -> None:
    messages = fold(
        [
            _event(
                1,
                "model/response",
                {
                    "turn_id": "t1",
                    "content": "完整",
                    "blocks": [{"type": "text", "text": "完整"}],
                    "tool_calls": [],
                    "finish_reason": "stop",
                },
            ),
            _event(
                2,
                "model/response",
                {
                    "turn_id": "t2",
                    "content": "半截",
                    "blocks": [{"type": "text", "text": "半截"}],
                    "tool_calls": [],
                    "finish_reason": "interrupted",
                    "interrupted": True,
                },
            ),
            _event(
                3,
                "model/attempt",
                {
                    "turn_id": "t3",
                    "status": "error",
                    "error_code": "PROVIDER_SCHEMA_INVALID",
                    "partial_blocks": [{"type": "text", "text": "坏"}],
                },
            ),
        ]
    ).messages

    assert [message.content for message in messages if message.role == "assistant"] == [
        "完整",
        "半截",
    ]
