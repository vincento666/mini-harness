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


def _records_from_lines(path: Path, lines: list[str]) -> list[EventRecord] | LogReadFailure:
    """把整行解析成记录：坏行是结果，不是异常。"""
    records: list[EventRecord] = []
    for line in lines:
        if not line.strip():
            continue
        try:
            records.append(EventRecord.model_validate(json.loads(line)))
        except (json.JSONDecodeError, ValidationError) as exc:
            return LogReadFailure(path=path, detail=f"{path}: {exc}")
    return records


def read_events(path: Path) -> list[EventRecord] | LogReadFailure:
    """按写入顺序读出日志里的全部事件记录。"""
    if not path.is_file():
        return []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        return LogReadFailure(path=path, detail=f"{path}: {exc}")
    return _records_from_lines(path, lines)


class LogTail:
    """同一份日志的增量读：记住字节偏移，只消费到最后一个换行符（design D6）。

    追加者正在写的那一行可能只落了一半：残行留在偏移之后，下一次读再看，事件流不会送出半条记录。
    """

    def __init__(self, path: Path, *, after: int = -1) -> None:
        """`after` 是续读游标：`seq` 不大于它的记录不再送出。默认 -1 是从第一条记录开始。"""
        self._path = path
        self._after = after
        self._offset = 0

    def read_new(self) -> list[EventRecord] | LogReadFailure:
        """读出偏移之后新写完的记录；没有新行就返回空列表。"""
        if not self._path.is_file():
            return []
        try:
            with self._path.open("rb") as handle:
                handle.seek(self._offset)
                chunk = handle.read()
        except OSError as exc:
            return LogReadFailure(path=self._path, detail=f"{self._path}: {exc}")

        end = chunk.rfind(b"\n")
        if end < 0:
            # 连一个换行符都没有：一个字节都不消费。
            return []
        self._offset += end + 1
        # 消费的一定是整行：残行没有换行符，不会被送进解析，所以这里不需要防拆开的多字节字符。
        records = _records_from_lines(self._path, chunk[: end + 1].decode("utf-8").splitlines())
        if isinstance(records, LogReadFailure):
            return records
        return [record for record in records if record.seq > self._after]
