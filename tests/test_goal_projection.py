"""seam ④：`todos` 投影的清空条件——每段开头清空，含 goal 轮次（照 DSH 的 `turn/start`）。"""

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
        _rec(0, "turn/start", {"turn_id": "s1"}),
        _rec(1, "user/message", {"turn_id": "s1", "content": "开工", "source": {"kind": "user"}}),
        _rec(2, "todo/updated", {"items": _table()}),
    ]


def test_turn_start_clears_even_for_a_goal_round() -> None:
    records = [
        *_base(),
        _rec(3, "turn/end", {"turn_id": "s1", "stop_reason": "MODEL_COMPLETED", "steps": 1}),
        _rec(4, "turn/start", {"turn_id": "s2"}),
        _rec(
            5,
            "user/message",
            {
                "turn_id": "s2",
                "content": "<goal_round>",
                "source": {"kind": "goal", "goal_id": "g1", "revision": 1, "round": 1},
            },
        ),
    ]

    assert project(records, "todos")["value"] == []


def test_turn_end_keeps_the_last_table() -> None:
    records = [*_base(), _rec(3, "turn/end", {"turn_id": "s1"})]

    assert project(records, "todos")["value"] == _table()


def test_turn_start_alone_clears() -> None:
    records = [*_base(), _rec(3, "turn/start", {"turn_id": "s2"})]

    assert project(records, "todos")["value"] == []


def test_old_log_without_source_clears_the_same_way() -> None:
    records = [
        *_base(),
        _rec(3, "turn/start", {"turn_id": "s2"}),
        _rec(4, "user/message", {"turn_id": "s2", "content": "老输入"}),
    ]

    assert project(records, "todos")["value"] == []
