"""只追加的事件日志。"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from mini_harness.events.record import SCHEMA_VERSION, EventRecord
from mini_harness.events.vocabulary import is_known_type


class LogWriteFailure:
    """日志无法创建或写入的结果：失败也是结果，不是异常。"""

    def __init__(self, path: Path, detail: str, code: str = "LOG_WRITE_FAILED") -> None:
        self.path = path
        self.detail = detail
        self.code = code


class EventLog:
    """一个 session 的 JSONL 日志：只追加，`seq` 在此单点分配。"""

    def __init__(self, path: Path, session_id: str, *, next_seq: int = 0) -> None:
        self.path = path
        self.session_id = session_id
        self._next_seq = next_seq

    @property
    def last_seq(self) -> int:
        """已经写出的最后一条记录的 `seq`；还没写过是 -1。"""
        return self._next_seq - 1

    @classmethod
    def start(cls, session_dir: Path) -> EventLog | LogWriteFailure:
        """为新 session 生成唯一 session id 并打开它的日志。"""
        return cls.create(session_dir=session_dir, session_id=uuid.uuid4().hex)

    @classmethod
    def open(cls, session_dir: Path, session_id: str) -> EventLog | LogWriteFailure:
        """打开已有日志并从最后一条记录续写；缺失或坏日志是失败结果。"""
        from mini_harness.events.reader import LogReadFailure, read_events

        path = session_dir / f"{session_id}.jsonl"
        if not path.is_file():
            return LogWriteFailure(path=path, detail=f"{path}: 日志不存在", code="LOG_NOT_FOUND")
        records = read_events(path)
        if isinstance(records, LogReadFailure):
            return LogWriteFailure(path=path, detail=records.detail, code=records.code)
        next_seq = records[-1].seq + 1 if records else 0
        return cls(path, session_id, next_seq=next_seq)

    @classmethod
    def create(cls, session_dir: Path, session_id: str) -> EventLog | LogWriteFailure:
        path = session_dir / f"{session_id}.jsonl"
        try:
            session_dir.mkdir(parents=True, exist_ok=True)
            path.touch()
        except OSError as exc:
            return LogWriteFailure(path=path, detail=f"{session_dir}: {exc}")
        return cls.open(session_dir, session_id)

    def append(self, event_type: str, payload: dict[str, Any]) -> EventRecord | LogWriteFailure:
        if not is_known_type(event_type):
            payload = {"unrecognized_type": event_type, **payload}
            event_type = "error/internal"
        record = EventRecord(
            schema_version=SCHEMA_VERSION,
            type=event_type,
            session_id=self.session_id,
            seq=self._next_seq,
            ts=datetime.now(UTC).isoformat(),
            payload=payload,
        )
        try:
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record.model_dump(mode="json"), ensure_ascii=False) + "\n")
        except OSError as exc:
            return LogWriteFailure(path=self.path, detail=f"{self.path}: {exc}")
        self._next_seq += 1
        return record
