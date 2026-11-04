"""事件记录信封（日志里每一行的形状）。"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, field_validator

from mini_harness.events.vocabulary import is_known_type

SCHEMA_VERSION = 1


class SchemaUnsupported(ValueError):
    """日志 schema_version 不是当前或相邻旧版：拒绝，不猜迁移。"""


class EventRecord(BaseModel):
    """日志里的一条事件记录。"""

    schema_version: int
    type: str
    session_id: str
    seq: int
    ts: str
    payload: dict[str, Any]

    @field_validator("type")
    @classmethod
    def _type_is_in_the_vocabulary(cls, value: str) -> str:
        """词表外的类型过不了校验：读回这样的行是日志层失败。"""
        if not is_known_type(value):
            raise ValueError(f"事件类型不在词表内：{value}")
        return value


def migrate_schema(record: EventRecord) -> EventRecord:
    """当前版本原样返回；只接受 N-1 → N，其余版本拒绝。"""
    if record.schema_version == SCHEMA_VERSION:
        return record
    if record.schema_version == SCHEMA_VERSION - 1:
        return record.model_copy(update={"schema_version": SCHEMA_VERSION})
    raise SchemaUnsupported(
        f"不支持的 schema_version {record.schema_version}（当前 {SCHEMA_VERSION}）"
    )
