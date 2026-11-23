"""当前事件类型词表。词表外的事实不得临时新造类型。"""

from __future__ import annotations

# v2 名字：只放当前形状，新写入的唯一合法集。`turn` 是段，`step` 是回合（C 方案）。
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

# v1 名字：只允许读，交给 `migrate_schema` 上迁；MUST NOT 出现在新写入里。
# 注意 `turn/start` 在两版里意思相反（v1=回合，v2=段），所以不能当同义词长期保留。
LEGACY_EVENT_TYPES: frozenset[str] = frozenset(
    {
        "segment/start",
        "segment/end",
        "turn/start",
        "turn/end",
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
    """读侧：当前名与 v1 旧名都放行（旧名由 `migrate_schema` 翻译）。"""
    return (
        event_type in CONCRETE_EVENT_TYPES
        or event_type in LEGACY_EVENT_TYPES
        or event_type.startswith(ERROR_NAMESPACE)
    )


def is_current_type(event_type: str) -> bool:
    """写侧：只认 v2 名字；旧名写出去会被记成 `error/internal`。"""
    return event_type in CONCRETE_EVENT_TYPES or event_type.startswith(ERROR_NAMESPACE)
