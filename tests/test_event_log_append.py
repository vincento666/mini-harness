"""seam ④：事件日志追加写产出的记录形状。"""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path

from mini_harness.events import EventLog, LogReadFailure, LogWriteFailure, read_events


def test_appended_record_carries_the_six_envelope_fields(tmp_path: Path) -> None:
    log = EventLog.create(session_dir=tmp_path, session_id="sess-1")
    log.append("session/start", {"workspace": str(tmp_path)})

    lines = log.path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1, "一次追加应产出一行 JSONL"

    record = json.loads(lines[0])
    assert record["schema_version"] == 1
    assert record["type"] == "session/start"
    assert record["session_id"] == "sess-1"
    assert isinstance(record["seq"], int)
    assert isinstance(record["ts"], str)
    assert record["payload"] == {"workspace": str(tmp_path)}


def test_seq_starts_at_zero_and_increments_by_one(tmp_path: Path) -> None:
    log = EventLog.create(session_dir=tmp_path, session_id="sess-2")
    log.append("session/start", {})
    log.append("turn/start", {"turn_id": "t1"})
    log.append("turn/end", {"turn_id": "t1"})

    seqs = [
        json.loads(line)["seq"]
        for line in log.path.read_text(encoding="utf-8").splitlines()
    ]
    assert seqs == [0, 1, 2]


def test_log_is_append_only(tmp_path: Path) -> None:
    log = EventLog.create(session_dir=tmp_path, session_id="sess-3")
    log.append("session/start", {})
    log.append("turn/start", {"turn_id": "t1"})
    written_so_far = log.path.read_bytes()

    log.append("turn/end", {"turn_id": "t1"})
    final = log.path.read_bytes()

    assert final.startswith(written_so_far), "已写入的字节必须是最终文件的严格前缀"
    assert final.startswith(written_so_far), "已写入的字节必须是最终文件的严格前缀"
    assert len(final) > len(written_so_far)


def test_missing_session_dir_is_created_and_each_run_gets_its_own_file(tmp_path: Path) -> None:
    session_dir = tmp_path / "nested" / "sessions"
    first = EventLog.start(session_dir=session_dir)
    second = EventLog.start(session_dir=session_dir)

    assert first.session_id != second.session_id
    assert first.path == session_dir / f"{first.session_id}.jsonl"
    assert second.path == session_dir / f"{second.session_id}.jsonl"
    assert first.path.is_file() and second.path.is_file()


def test_types_outside_the_vocabulary_are_written_as_error_internal(tmp_path: Path) -> None:
    log = EventLog.create(session_dir=tmp_path, session_id="sess-5")
    log.append("session/start", {})
    log.append("widget/frobnicate", {"detail": "boom"})

    lines = log.path.read_text(encoding="utf-8").splitlines()
    types = [json.loads(line)["type"] for line in lines]
    assert types == ["session/start", "error/internal"]

    payload = json.loads(lines[1])["payload"]
    assert payload["unrecognized_type"] == "widget/frobnicate"
    payload = json.loads(lines[1])["payload"]
    assert payload["unrecognized_type"] == "widget/frobnicate"
    assert payload["detail"] == "boom"


def test_a_corrupt_line_is_a_log_read_failure(tmp_path: Path) -> None:
    log = EventLog.create(session_dir=tmp_path, session_id="sess-7")
    log.append("session/start", {})
    with log.path.open("a", encoding="utf-8") as handle:
        handle.write("{not json}\n")

    outcome = read_events(log.path)

    assert isinstance(outcome, LogReadFailure)
    assert outcome.code == "LOG_UNREADABLE"
    assert str(log.path) in outcome.detail


def test_a_log_that_becomes_unwritable_mid_session_is_a_log_write_failure(tmp_path: Path) -> None:
    log = EventLog.create(session_dir=tmp_path, session_id="sess-6")
    log.append("session/start", {})
    written_so_far = log.path.read_bytes()
    os.chmod(log.path, stat.S_IREAD)
    try:
        outcome = log.append("turn/start", {"turn_id": "t1"})
    finally:
        os.chmod(log.path, stat.S_IREAD | stat.S_IWRITE)

    assert isinstance(outcome, LogWriteFailure)
    assert outcome.code == "LOG_WRITE_FAILED"
    assert outcome.path == log.path
    assert log.path.read_bytes() == written_so_far


def test_unwritable_session_dir_is_a_log_write_failure(tmp_path: Path) -> None:
    blocker = tmp_path / "blocker"
    blocker.write_text("not a directory", encoding="utf-8")

    outcome = EventLog.start(session_dir=blocker / "sessions")

    assert isinstance(outcome, LogWriteFailure)
    assert outcome.code == "LOG_WRITE_FAILED"
    assert str(blocker / "sessions") in outcome.detail





