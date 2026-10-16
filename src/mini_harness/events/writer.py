"""只追加的事件日志。"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from mini_harness.events.record import SCHEMA_VERSION, EventRecord


class EventLog:
    """一个 session 的 JSONL 日志：只追加，`seq` 在此单点分配。"""

    def __init__(self, path: Path, session_id: str) -> None:
        self.path = path
        self.session_id = session_id
        self._next_seq = 0

    @classmethod
    def create(cls, session_dir: Path, session_id: str) -> EventLog:
        session_dir.mkdir(parents=True, exist_ok=True)
        return cls(session_dir / f"{session_id}.jsonl", session_id)

    def append(self, event_type: str, payload: dict[str, Any]) -> EventRecord:
        record = EventRecord(
            schema_version=SCHEMA_VERSION,
            type=event_type,
            session_id=self.session_id,
            seq=self._next_seq,
            ts=datetime.now(UTC).isoformat(),
            payload=payload,
        )
        self._next_seq += 1
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record.model_dump(mode="json"), ensure_ascii=False) + "\n")
        return record
