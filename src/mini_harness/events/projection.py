"""会话投影（M14c）：从日志派生 UI 需要的当前值。

投影是**可丢弃的派生结果**：事实在日志里，重新 fold 一次就能得到同样的值。
首个单元是 `todos`；生命周期按 mini 的 segment（一个用户请求），不是 turn（一次模型调用）。
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from mini_harness.events.record import EventRecord


class ProjectionUnit(Protocol):
    """一个投影单元：初始化、逐事件推进、对外视图。"""

    name: str
    state_version: int

    def init(self) -> Any: ...

    def apply(self, state: Any, event: EventRecord) -> Any: ...

    def view(self, state: Any) -> Any: ...


@dataclass(frozen=True)
class TodoProjection:
    """待办表：`todo/updated` 整表替换；`segment/start` 清空；`segment/end` 保留。"""

    name: str = "todos"
    state_version: int = 1

    def init(self) -> list[dict[str, Any]]:
        return []

    def apply(self, state: Any, event: EventRecord) -> Any:
        if event.type == "todo/updated":
            items = event.payload.get("items")
            return list(items) if isinstance(items, list) else state
        if event.type == "segment/start":
            return []
        return state

    def view(self, state: Any) -> Any:
        return state


UNITS: dict[str, ProjectionUnit] = {"todos": TodoProjection()}


def project(records: Sequence[EventRecord], name: str) -> dict[str, Any]:
    """从日志算出某个投影的当前值；未注册的名字是 KeyError。"""
    unit = UNITS[name]
    state = unit.init()
    for event in records:
        state = unit.apply(state, event)
    return {"name": name, "state_version": unit.state_version, "value": unit.view(state)}
