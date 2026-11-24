"""当前事件类型词表。词表外的事实不得临时新造类型。"""

from __future__ import annotations

# 唯一合法集：写与读都只认这些名字。`turn` 是轮，`step` 是步（C 方案）。
CONCRETE_EVENT_TYPES: frozenset[str] = frozenset(
    {
        "session/start",
        "session/end",
        "turn/start",
        "turn/end",
        "step/start",
        "step/end",
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
        "command/run",
        "command/done",
        "plan/mode",
        "goal/updated",
        "todo/updated",
        "question/asked",
        "question/answered",
        "present/artifact",
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
    """读与写共用同一个判据：只认当前名与 `error/*` 命名空间。"""
    return event_type in CONCRETE_EVENT_TYPES or event_type.startswith(ERROR_NAMESPACE)
