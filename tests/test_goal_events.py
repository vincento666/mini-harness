"""seam ④：`goal/updated` 的词表、快照形状与折叠（M13 task 1.1）。"""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from mini_harness.events import EventRecord
from mini_harness.events.vocabulary import is_known_type
from mini_harness.goals import GoalSnapshot, fold_goal

_SESSION_ID = "s-goal"


def _rec(seq: int, event_type: str, payload: dict[str, Any]) -> EventRecord:
    return EventRecord(
        schema_version=1,
        type=event_type,
        session_id=_SESSION_ID,
        seq=seq,
        ts=f"2026-11-17T00:00:{seq:02d}+00:00",
        payload=payload,
    )


def _snapshot(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "id": "g1",
        "revision": 1,
        "objective": "修好 tests/ 里那条失败的用例",
        "phase": "active",
        "max_rounds": 3,
        "rounds_started": 0,
    }
    base.update(overrides)
    return base


def test_goal_updated_is_in_the_vocabulary() -> None:
    assert is_known_type("goal/updated")


def test_fold_takes_the_last_snapshot() -> None:
    events = [
        _rec(1, "goal/updated", {"goal": _snapshot(revision=1, rounds_started=0)}),
        _rec(2, "goal/updated", {"goal": _snapshot(revision=2, rounds_started=1)}),
    ]

    folded = fold_goal(events)

    assert folded is not None
    assert folded.revision == 2
    assert folded.rounds_started == 1


def test_null_payload_clears_the_goal() -> None:
    events = [
        _rec(1, "goal/updated", {"goal": _snapshot()}),
        _rec(2, "goal/updated", {"goal": None}),
    ]

    assert fold_goal(events) is None


def test_no_event_means_no_goal() -> None:
    assert fold_goal([]) is None


def test_blocked_snapshot_requires_a_reason() -> None:
    with pytest.raises(ValidationError):
        GoalSnapshot.model_validate(_snapshot(phase="blocked"))


def test_blocked_reason_message_must_not_be_blank() -> None:
    with pytest.raises(ValidationError):
        GoalSnapshot.model_validate(
            _snapshot(phase="blocked", blocked_reason={"code": "round-limit", "message": "  "})
        )


def test_non_blocked_snapshot_rejects_a_reason() -> None:
    with pytest.raises(ValidationError):
        GoalSnapshot.model_validate(
            _snapshot(phase="active", blocked_reason={"code": "model-reported", "message": "x"})
        )


def test_revision_and_round_caps_are_positive() -> None:
    with pytest.raises(ValidationError):
        GoalSnapshot.model_validate(_snapshot(revision=0))
    with pytest.raises(ValidationError):
        GoalSnapshot.model_validate(_snapshot(max_rounds=0))


def test_objective_must_not_be_blank() -> None:
    with pytest.raises(ValidationError):
        GoalSnapshot.model_validate(_snapshot(objective="   "))
