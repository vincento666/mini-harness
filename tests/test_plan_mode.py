"""seam ④：`plan/mode` 事件与折叠（M14c 切片 1）。"""

from __future__ import annotations

from mini_harness.events.fold import fold_plan_mode
from mini_harness.events.record import EventRecord


def _rec(seq: int, event_type: str, payload: dict[str, object]) -> EventRecord:
    return EventRecord(
        schema_version=1,
        session_id="s-plan",
        seq=seq,
        ts=f"2026-11-16T00:00:{seq:02d}+00:00",
        type=event_type,
        payload=payload,
    )


def test_plan_mode_defaults_to_false() -> None:
    records = [_rec(0, "session/start", {"prompt": "任务"})]

    assert fold_plan_mode(records) is False


def test_plan_mode_takes_the_last_value() -> None:
    records = [
        _rec(1, "plan/mode", {"active": True}),
        _rec(2, "plan/mode", {"active": False}),
        _rec(3, "plan/mode", {"active": True}),
    ]

    assert fold_plan_mode(records) is True
