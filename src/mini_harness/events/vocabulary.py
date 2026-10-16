"""M1 事件类型词表。词表外的事实不得临时新造类型。"""

from __future__ import annotations

CONCRETE_EVENT_TYPES: frozenset[str] = frozenset(
    {
        "session/start",
        "session/end",
        "turn/start",
        "turn/end",
        "context/assembled",
        "model/request",
        "model/response",
        "tool/call",
        "tool/result",
    }
)

ERROR_NAMESPACE = "error/"


def is_known_type(event_type: str) -> bool:
    """事件类型是否在 M1 词表内（`error/*` 是整个命名空间）。"""
    return event_type in CONCRETE_EVENT_TYPES or event_type.startswith(ERROR_NAMESPACE)
