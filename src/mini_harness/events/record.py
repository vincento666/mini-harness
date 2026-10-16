"""事件记录信封（日志里每一行的形状）。"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

SCHEMA_VERSION = 1


class EventRecord(BaseModel):
    """日志里的一条事件记录。"""

    schema_version: int
    type: str
    session_id: str
    seq: int
    ts: str
    payload: dict[str, Any]
