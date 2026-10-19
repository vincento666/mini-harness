"""seam ④：事件类型词表——哪些类型在表内、哪些必须留在表外。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import get_args

from mini_harness.events import EventLog
from mini_harness.events.reader import LogReadFailure, read_events
from mini_harness.events.vocabulary import ERROR_EVENT_TYPES, is_known_type
from mini_harness.loop import STOP_REASONS
from mini_harness.loop.turn_loop import StopReason

M2_ERROR_TYPES = {"error/model", "error/internal", "error/abort", "error/fence"}


def test_approval_types_are_in_the_vocabulary() -> None:
    assert is_known_type("approval/request")
    assert is_known_type("approval/response")


def test_approval_types_can_be_written_to_the_log(tmp_path: Path) -> None:
    log = EventLog.create(session_dir=tmp_path, session_id="sess-v1")

    log.append("approval/request", {"turn_id": "t1", "tool_name": "write"})
    log.append("approval/response", {"turn_id": "t1", "decision": "APPROVED"})

    types = [json.loads(line)["type"] for line in log.path.read_text(encoding="utf-8").splitlines()]
    assert types == ["approval/request", "approval/response"]


def test_model_retry_and_tool_cancelled_are_in_the_vocabulary(tmp_path: Path) -> None:
    """M4 把 `model/retry` 收进词表；M3 把 `tool/cancelled` 收进词表。"""
    assert is_known_type("model/retry")
    assert is_known_type("tool/cancelled")

    log = EventLog.create(session_dir=tmp_path, session_id="sess-v2")
    log.append("tool/cancelled", {"turn_id": "t1", "tool_call_id": "call-1"})

    written = json.loads(log.path.read_text(encoding="utf-8").splitlines()[0])
    assert written["type"] == "tool/cancelled"
    assert "unrecognized_type" not in written["payload"]


def test_error_fence_is_a_declared_error_type() -> None:
    assert ERROR_EVENT_TYPES == M2_ERROR_TYPES
    assert is_known_type("error/fence")


def test_a_record_type_outside_the_vocabulary_is_a_read_failure(tmp_path: Path) -> None:
    path = tmp_path / "sess-v3.jsonl"
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "type": "widget/frobnicate",
                "session_id": "sess-v3",
                "seq": 0,
                "ts": "2026-10-17T00:00:00+00:00",
                "payload": {},
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    outcome = read_events(path)

    assert isinstance(outcome, LogReadFailure)
    assert outcome.code == "LOG_UNREADABLE"


def test_stop_reason_constant_and_literal_are_one_source() -> None:
    assert set(STOP_REASONS) == set(get_args(StopReason))
