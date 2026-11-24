"""1.x：日志 schema v2 与 v1 上迁（seam ④）。

这一组判据钉两件事：**旧日志读得动**（v1 行在读取时翻译成 v2），**新日志只有一种形状**
（写侧拒绝 v1 名字）。改名不是加别名——`turn/start` 在 v1 指回合、在 v2 指段，同一个
字符串两义，所以版本号是消歧的唯一依据（design D2）。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from mini_harness.events import SCHEMA_VERSION, EventLog, EventRecord
from mini_harness.events.reader import read_events
from mini_harness.events.record import SchemaUnsupported, migrate_schema
from mini_harness.events.vocabulary import (
    CONCRETE_EVENT_TYPES,
    LEGACY_EVENT_TYPES,
    is_current_type,
    is_known_type,
)

FIXTURE = Path(__file__).parent / "fixtures" / "logs" / "v1-goal-tools.jsonl"


def _v1(event_type: str, payload: dict[str, object], *, seq: int = 0) -> EventRecord:
    return EventRecord(
        schema_version=1,
        type=event_type,
        session_id="sess-v1",
        seq=seq,
        ts="2026-11-23T00:00:00+00:00",
        payload=payload,
    )


def test_schema_version_is_two() -> None:
    assert SCHEMA_VERSION == 2


def test_a_v1_segment_start_becomes_a_v2_turn_start() -> None:
    upcast = migrate_schema(_v1("segment/start", {"segment_id": "s1"}))

    assert upcast.schema_version == 2
    assert upcast.type == "turn/start"
    assert upcast.payload == {"turn_id": "s1"}


def test_a_v1_turn_start_becomes_a_v2_step_start() -> None:
    """最容易写错的一条：v1 的 `turn` 是回合，v2 的 `turn` 是段。"""
    upcast = migrate_schema(_v1("turn/start", {"turn_id": "t1"}))

    assert upcast.schema_version == 2
    assert upcast.type == "step/start"
    assert upcast.payload == {"step_id": "t1"}


def test_a_v1_segment_end_moves_the_step_count_key() -> None:
    upcast = migrate_schema(
        _v1(
            "segment/end",
            {
                "segment_id": "s1",
                "stop_reason": "MODEL_COMPLETED",
                "turns": 2,
                "tool_calls": 3,
            },
        )
    )

    assert upcast.type == "turn/end"
    assert upcast.payload == {
        "turn_id": "s1",
        "stop_reason": "MODEL_COMPLETED",
        "steps": 2,
        "tool_calls": 3,
    }


def test_a_v1_turn_end_becomes_a_v2_step_end() -> None:
    upcast = migrate_schema(_v1("turn/end", {"turn_id": "t1", "stop_reason": "MAX_TURNS"}))

    assert upcast.type == "step/end"
    # 值也不是原样保留：`MAX_TURNS` 是封闭词表里的一项，它的新名是 `MAX_STEPS`。
    assert upcast.payload == {"step_id": "t1", "stop_reason": "MAX_STEPS"}


def test_upcast_keeps_identity_and_unrelated_values() -> None:
    upcast = migrate_schema(
        _v1(
            "tool/call",
            {"turn_id": "t1", "tool_call_id": "c1", "name": "read", "arguments": {"path": "a"}},
            seq=17,
        )
    )

    # 类型没改名，但键仍然是「step 的 id」：整份日志的键要一起换。
    assert upcast.type == "tool/call"
    assert upcast.payload["step_id"] == "t1"
    assert "turn_id" not in upcast.payload
    assert upcast.payload["arguments"] == {"path": "a"}
    assert (upcast.seq, upcast.session_id, upcast.ts) == (
        17,
        "sess-v1",
        "2026-11-23T00:00:00+00:00",
    )


def test_v1_session_end_moves_the_total_step_count() -> None:
    upcast = migrate_schema(_v1("session/end", {"stop_reason": "MODEL_COMPLETED", "turns": 4}))

    assert upcast.payload == {"stop_reason": "MODEL_COMPLETED", "steps": 4}


def test_legacy_names_are_readable_but_not_writable() -> None:
    assert "segment/start" in LEGACY_EVENT_TYPES
    assert "segment/start" not in CONCRETE_EVENT_TYPES
    assert "turn/start" in CONCRETE_EVENT_TYPES
    assert is_known_type("segment/start") is True  # 读：旧名放行，交给上迁
    assert is_current_type("segment/start") is False  # 写：旧名拒绝
    assert is_current_type("turn/start") is True


def test_a_v2_record_cannot_carry_a_legacy_name() -> None:
    """v2 行带 v1 名字是坏日志：版本号说「按 v2 读」，名字却属于 v1。"""
    with pytest.raises(ValueError):
        EventRecord(
            schema_version=2,
            type="segment/start",
            session_id="sess-v1",
            seq=0,
            ts="2026-11-23T00:00:00+00:00",
            payload={},
        )


def test_writing_a_legacy_name_falls_back_to_error_internal(tmp_path: Path) -> None:
    log = EventLog.create(session_dir=tmp_path, session_id="sess-legacy-write")

    log.append("segment/start", {"segment_id": "s1"})

    written = json.loads(log.path.read_text(encoding="utf-8").splitlines()[0])
    assert written["type"] == "error/internal"
    assert written["payload"]["unrecognized_type"] == "segment/start"


def test_a_new_log_is_written_as_v2_with_current_names(tmp_path: Path) -> None:
    log = EventLog.create(session_dir=tmp_path, session_id="sess-v2-write")

    log.append("turn/start", {"turn_id": "s1"})
    log.append("step/start", {"step_id": "t1"})

    written = [json.loads(line) for line in log.path.read_text(encoding="utf-8").splitlines()]
    assert [record["schema_version"] for record in written] == [2, 2]
    assert [record["type"] for record in written] == ["turn/start", "step/start"]
    assert written[0]["payload"] == {"turn_id": "s1"}
    assert written[1]["payload"] == {"step_id": "t1"}


@pytest.mark.parametrize("version", [0, 3])
def test_non_adjacent_versions_are_rejected(version: int) -> None:
    record = _v1("turn/start", {"turn_id": "t1"}).model_copy(update={"schema_version": version})

    with pytest.raises(SchemaUnsupported):
        migrate_schema(record)


def test_the_frozen_v1_sample_reads_back_as_v2_only() -> None:
    """金样本的字节不变；读回来的每一条都已按 v2 解释。"""
    records = read_events(FIXTURE)

    assert isinstance(records, list)
    assert {record.schema_version for record in records} == {2}
    types = {record.type for record in records}
    # `segment/*` 是只属于 v1 的名字，读到它就说明上迁漏了。`turn/*` 不能这么判：
    # 它在 v2 里是段边界，是合法名字。
    assert not {event_type for event_type in types if event_type.startswith("segment/")}
    assert {"turn/start", "turn/end", "step/start", "step/end"} <= types
