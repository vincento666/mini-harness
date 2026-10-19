"""工具契约：定义、入参模型、结果。`ToolDefinition` 是内核侧定义，`ToolSpec` 是给模型的窄契约。"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel

from mini_harness.provider.contract import ToolSpec
from mini_harness.tools.fences import DispatchContext


class ToolArgs(BaseModel):
    """工具入参基类。`target_path` 回答「这次要动哪个路径」，没有路径的工具返回 None。"""

    def target_path(self) -> str | None:
        return None


ToolOutcome = Literal[
    "OK",
    "UNKNOWN_TOOL",
    "TOOL_ARGS_INVALID",
    "PATH_NOT_FOUND",
    "IS_A_DIRECTORY",
    "NOT_A_DIRECTORY",
    "NOT_UTF8_TEXT",
    "WRITE_WITHOUT_READ",
    "STALE_EDIT",
    "EDIT_TARGET_NOT_FOUND",
    "EDIT_TARGET_AMBIGUOUS",
    "TOOL_IO_FAILED",
    "TOOL_TIMEOUT",
    "TOOL_CANCELLED",
    "DENIED_BY_FENCE",
    "DENIED_BY_APPROVAL",
]


@dataclass(frozen=True)
class ToolResult:
    """一次工具派发的结果。失败也是结果，不是异常。"""

    outcome: ToolOutcome
    content: str


ToolExecutor = Callable[[Any, DispatchContext], Awaitable[ToolResult]]


@dataclass(frozen=True)
class ToolDefinition:
    """一个工具：给模型的说明、入参校验模型、会不会改动（决定要不要问人）、执行入口。"""

    name: str
    description: str
    args_model: type[ToolArgs]
    mutates: bool
    run: ToolExecutor


class ToolRegistry:
    """按名字查工具定义。"""

    def __init__(self, tools: Sequence[ToolDefinition] = ()) -> None:
        self._tools: dict[str, ToolDefinition] = {tool.name: tool for tool in tools}

    def lookup(self, name: str) -> ToolDefinition | None:
        return self._tools.get(name)

    def specs(self) -> list[ToolSpec]:
        return [
            ToolSpec(
                name=tool.name,
                description=tool.description,
                parameters=tool.args_model.model_json_schema(),
            )
            for tool in self._tools.values()
        ]
