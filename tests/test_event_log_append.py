"""seam ④：事件日志追加写产出的记录形状。"""

from __future__ import annotations

import json
from pathlib import Path

from mini_harness.events import EventLog


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

