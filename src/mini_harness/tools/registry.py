"""工具注册表：定义与执行分离，M1 的注册表为空。"""

from __future__ import annotations

from collections.abc import Sequence

from pydantic import BaseModel

from mini_harness.provider.contract import ToolSpec


class ToolDefinition(BaseModel):
    """一个工具的定义（M1 不注册任何工具）。"""

    name: str
    description: str


class ToolRegistry:
    """按名字查工具定义。"""

    def __init__(self, tools: Sequence[ToolDefinition] = ()) -> None:
        self._tools: dict[str, ToolDefinition] = {tool.name: tool for tool in tools}

    def lookup(self, name: str) -> ToolDefinition | None:
        return self._tools.get(name)

    def specs(self) -> list[ToolSpec]:
        return [ToolSpec(name=tool.name, description=tool.description) for tool in self._tools.values()]
