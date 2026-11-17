"""seam ④：`todos` 投影的清空条件（M13 task 2.1）。"""

from __future__ import annotations

from typing import Any

from mini_harness.events import EventRecord
from mini_harness.events.projection import project

_SESSION_ID = "s-proj"


def _rec(seq: int, event_type: str, payload: dict[str, Any]) -> EventRecord:
    return EventRecord(
        schema_version=1,
        type=event_type,
        session_id=_SESSION_ID,
        seq=seq,
        ts=f"2026-11-17T00:01:{seq:02d}+00:00",
        payload=payload,
    )


def _table() -> list[dict[str, Any]]:
    return [
        {"id": "t1", "text": "写判据", "status": "in_progress"},
        {"id": "t2", "text": "改实现", "status": "pending"},
    ]


def _base() -> list[EventRecord]:
    return [
        _rec(0, "segment/start", {"segment_id": "s1"}),
        _rec(
            1, "user/message", {"segment_id": "s1", "content": "开工", "source": {"kind": "user"}}
        ),
        _rec(2, "todo/updated", {"items": _table()}),
        _rec(3, "segment/end", {"segment_id": "s1", "stop_reason": "MODEL_COMPLETED", "turns": 1}),
    ]


def test_human_segment_keeps_the_old_clearing_behaviour() -> None:
    records = [
        *_base(),
        _rec(4, "segment/start", {"segment_id": "s2"}),
        _rec(
            5, "user/message", {"segment_id": "s2", "content": "新问题", "source": {"kind": "user"}}
        ),
    ]

    assert project(records, "todos")["value"] == []


def test_goal_segment_keeps_the_table() -> None:
    records = [
        *_base(),
        _rec(4, "segment/start", {"segment_id": "s2"}),
        _rec(
            5,
            "user/message",
            {
                "segment_id": "s2",
                "content": "<goal_round>",
                "source": {"kind": "goal", "goal_id": "g1", "revision": 1, "round": 1},
            },
        ),
    ]

    assert project(records, "todos")["value"] == _table()


def test_old_log_without_source_still_clears() -> None:
    records = [
        *_base(),
        _rec(4, "segment/start", {"segment_id": "s2"}),
        _rec(5, "user/message", {"segment_id": "s2", "content": "老输入"}),
    ]

    assert project(records, "todos")["value"] == []


def test_segment_end_keeps_the_last_table() -> None:
    assert project(_base(), "todos")["value"] == _table()


def test_segment_start_alone_does_not_clear() -> None:
    records = [*_base(), _rec(4, "segment/start", {"segment_id": "s2"})]

    assert project(records, "todos")["value"] == _table()
