"""当前事件类型词表。词表外的事实不得临时新造类型。"""

from __future__ import annotations

CONCRETE_EVENT_TYPES: frozenset[str] = frozenset(
    {
        "session/start",
        "session/end",
        "segment/start",
        "segment/end",
        "turn/start",
        "turn/end",
        "context/assembled",
        "model/request",
        "model/retry",
        "model/response",
        "user/message",
        "tool/call",
        "tool/result",
        "tool/cancelled",
        "approval/request",
        "approval/response",
        "compaction/summary",
    }
)

ERROR_NAMESPACE = "error/"

# `error/*` 作为命名空间是开放的（无法归类的内部故障照走它），但本词表声明的具体错误类型只有这五个。
ERROR_EVENT_TYPES: frozenset[str] = frozenset(
    {
        "error/model",
        "error/internal",
        "error/abort",
        "error/fence",
        "error/context",
    }
)


def is_known_type(event_type: str) -> bool:
    """事件类型是否在当前词表内（`error/*` 是整个命名空间）。"""
    return event_type in CONCRETE_EVENT_TYPES or event_type.startswith(ERROR_NAMESPACE)
