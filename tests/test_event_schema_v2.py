"""日志 schema v2（seam ④）。

这一组判据钉两件事：**新日志只有 v2 形状**（词表只认当前名），**不认识的版本直接拒**
（`SCHEMA_UNSUPPORTED`，不猜迁移）。`turn/start` 在 v1 指回合、在 v2 指轮，同一个字符串两义，
所以版本号是消歧的唯一依据；v1 上迁只在改造期存在（design D4）。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from mini_harness.events import SCHEMA_VERSION, EventLog, EventRecord
from mini_harness.events.reader import LogReadFailure, read_events
from mini_harness.events.vocabulary import CONCRETE_EVENT_TYPES, is_known_type


def test_schema_version_is_two() -> None:
    assert SCHEMA_VERSION == 2


def test_the_vocabulary_holds_only_current_names() -> None:
    assert "turn/start" in CONCRETE_EVENT_TYPES
    assert "step/start" in CONCRETE_EVENT_TYPES
    assert "segment/start" not in CONCRETE_EVENT_TYPES
    assert is_known_type("turn/start") is True
    assert is_known_type("segment/start") is False


def test_a_record_cannot_carry_an_unknown_type() -> None:
    """v1 名字不在词表里：拼一条这样的记录过不了校验。"""
    with pytest.raises(ValueError):
        EventRecord(
            schema_version=2,
            type="segment/start",
            session_id="sess-v2",
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


def _v1_line() -> str:
    return json.dumps(
        {
            "schema_version": 1,
            "type": "segment/start",
            "session_id": "sess-v1",
            "seq": 0,
            "ts": "2026-11-23T00:00:00+00:00",
            "payload": {"segment_id": "s1"},
        }
    )


def test_a_v1_line_is_rejected_with_schema_unsupported(tmp_path: Path) -> None:
    """不认识的版本先于类型校验被拒：得到的是「版本不支持」，不是「行读不动」。"""
    path = tmp_path / "sess-v1.jsonl"
    path.write_text(_v1_line() + "\n", encoding="utf-8")

    result = read_events(path)

    assert isinstance(result, LogReadFailure)
    assert result.code == "SCHEMA_UNSUPPORTED"


@pytest.mark.parametrize("version", [0, 1, 3])
def test_other_schema_versions_are_rejected(version: int, tmp_path: Path) -> None:
    record = json.loads(_v1_line())
    record["schema_version"] = version
    record["type"] = "turn/start"
    record["payload"] = {"turn_id": "s1"}
    path = tmp_path / f"sess-v{version}.jsonl"
    path.write_text(json.dumps(record) + "\n", encoding="utf-8")

    result = read_events(path)

    assert isinstance(result, LogReadFailure)
    assert result.code == "SCHEMA_UNSUPPORTED"
