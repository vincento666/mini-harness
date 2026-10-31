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
