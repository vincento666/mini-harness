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

    def __init__(self, path: Path) -> None:
        self._path = path
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
        try:
            lines = chunk[: end + 1].decode("utf-8").splitlines()
        except UnicodeDecodeError as exc:
            return LogReadFailure(path=self._path, detail=f"{self._path}: {exc}")
        return _records_from_lines(self._path, lines)
