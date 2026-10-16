"""从日志文件读事件记录：冷启动全量重放的入口。"""

from __future__ import annotations

import json
from pathlib import Path

from mini_harness.events.record import EventRecord


def read_events(path: Path) -> list[EventRecord]:
    """按写入顺序读出日志里的全部事件记录。"""
    if not path.is_file():
        return []
    records: list[EventRecord] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        records.append(EventRecord.model_validate(json.loads(line)))
    return records
