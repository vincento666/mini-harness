"""从日志文件读事件记录：冷启动全量重放的入口。"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import ValidationError

from mini_harness.events.record import EventRecord


class LogReadFailure:
    """日志读不动或读到坏行：失败也是结果，不是异常。"""

    def __init__(self, path: Path, detail: str, code: str = "LOG_UNREADABLE") -> None:
        self.path = path
        self.detail = detail
        self.code = code


def read_events(path: Path) -> list[EventRecord] | LogReadFailure:
    """按写入顺序读出日志里的全部事件记录。"""
    if not path.is_file():
        return []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        return LogReadFailure(path=path, detail=f"{path}: {exc}")

    records: list[EventRecord] = []
    for line in lines:
        if not line.strip():
            continue
        try:
            records.append(EventRecord.model_validate(json.loads(line)))
        except (json.JSONDecodeError, ValidationError) as exc:
            return LogReadFailure(path=path, detail=f"{path}: {exc}")
    return records
