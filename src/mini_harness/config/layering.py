"""取值优先级：内置默认 < 配置文件 < 命令行 flag（design D2）。

CLI 层的哨兵是 `None`：argparse 的默认值一律是 `None`，所以「显式给了 flag」与「没给」分得开——
`--max-turns 8` 与「没给 `--max-turns` 而内置默认也是 8」是两层不同的事实，前者赢。
"""

from __future__ import annotations

import argparse
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from mini_harness.loop.settings import (
    DEFAULT_API_KEY_ENV,
    DEFAULT_APPEND_SYSTEM_PROMPT,
    DEFAULT_APPROVAL,
    DEFAULT_BASE_URL,
    DEFAULT_MAX_TURNS,
    DEFAULT_MODEL,
    DEFAULT_PROVIDER,
    DEFAULT_RESERVE,
    DEFAULT_SANDBOX,
    DEFAULT_WINDOW,
    ApprovalMode,
    SandboxLevel,
)

# 每个可配字段一行：内置默认。配置文件里的键名与这里的键名逐字相同，argparse 的属性名也是。
BUILTIN_DEFAULTS: dict[str, Any] = {
    "provider": DEFAULT_PROVIDER,
    "base_url": DEFAULT_BASE_URL,
    "model": DEFAULT_MODEL,
    "api_key_env": DEFAULT_API_KEY_ENV,
    "max_turns": DEFAULT_MAX_TURNS,
    "window": DEFAULT_WINDOW,
    "reserve": DEFAULT_RESERVE,
    "append_system_prompt": DEFAULT_APPEND_SYSTEM_PROMPT,
    "sandbox": DEFAULT_SANDBOX,
    "approval": DEFAULT_APPROVAL,
    # 这三条的「没设置」本身就是有效状态：工具表全开、日志用默认位置、工作区用当前目录。
    "tools": None,
    "session_dir": None,
    "workspace": None,
}


@dataclass(frozen=True)
class EffectiveSettings:
    """层叠之后的有效值。CLI 之后只认这一份，不再回头看 argv 与配置文件。"""

    provider: str
    base_url: str
    model: str
    api_key_env: str
    max_turns: int
    window: int
    reserve: int
    append_system_prompt: str
    sandbox: SandboxLevel
    approval: ApprovalMode
    tools: list[str] | None
    session_dir: str | None
    workspace: str | None


def layer_settings(args: argparse.Namespace, config: Mapping[str, Any]) -> EffectiveSettings:
    """把三层取值塌成一份有效设置。"""
    values: dict[str, Any] = {}
    for name, builtin in BUILTIN_DEFAULTS.items():
        # 没有对应 flag 的字段（`tools` 与 `approval`）在 CLI 层就是「没给」。
        from_flag = getattr(args, name, None)
        if from_flag is not None:
            values[name] = from_flag
        elif name in config:
            values[name] = config[name]
        else:
            values[name] = builtin
    return EffectiveSettings(**values)
