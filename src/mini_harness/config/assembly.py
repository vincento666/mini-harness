"""工具表从装配来：内置六定义加配置白名单筛选（design D4）。"""

from __future__ import annotations

from collections.abc import Sequence

from mini_harness.config.load import ConfigFailure
from mini_harness.tools import ToolRegistry
from mini_harness.tools.bash_tools import bash_tool_definitions
from mini_harness.tools.file_tools import file_tool_definitions


def build_registry(names: Sequence[str] | None) -> ToolRegistry | ConfigFailure:
    """内置六定义（五个文件工具加 `bash`，顺序固定）；`None` 是全开，给了名单就按内置顺序筛。

    名单里的未知名是一条配置失败：工具表不会悄悄少一个，也不会悄悄多一个。
    """
    definitions = [*file_tool_definitions(), *bash_tool_definitions()]
    if names is None:
        return ToolRegistry(definitions)
    known = {tool.name for tool in definitions}
    for name in names:
        if name not in known:
            return ConfigFailure("UNKNOWN_TOOL_NAME", f"工具白名单里有未注册的名字：{name}")
    kept = set(names)
    return ToolRegistry([tool for tool in definitions if tool.name in kept])
