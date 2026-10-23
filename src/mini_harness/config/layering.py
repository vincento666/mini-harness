"""取值优先级：内置默认 < 配置文件 < 命令行 flag（design D2）。

CLI 层的哨兵是 `None`：argparse 的默认值一律是 `None`，所以「显式给了 flag」与「没给」分得开——
`--max-turns 8` 与「没给 `--max-turns` 而内置默认也是 8」是两层不同的事实，前者赢。
"""

from __future__ import annotations

import argparse
import os
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from mini_harness.loop.settings import (
    DEFAULT_APPEND_SYSTEM_PROMPT,
    DEFAULT_APPROVAL,
    DEFAULT_MAX_TURNS,
    DEFAULT_PROVIDER,
    DEFAULT_PROVIDER_KEY_ENV,
    DEFAULT_RESERVE,
    DEFAULT_SANDBOX,
    DEFAULT_WINDOW,
    PROVIDER_PRESETS,
    ApprovalMode,
    SandboxLevel,
)

# 每个可配字段一行：内置默认。配置文件里的键名与这里的键名逐字相同，argparse 的属性名也是。
# `provider` 与端点三项不在这张表里：它们的内置默认取决于 provider 名字（预设表）与
# `MINIHNS_API_KEY` 是否在场，见下面 `_provider_of` 与 `_endpoint_of`。
BUILTIN_DEFAULTS: dict[str, Any] = {
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

# 端点三项结伴：预设表填的就是这三项里没被给的那几项。
_ENDPOINT_FIELDS: tuple[str, ...] = ("base_url", "model", "api_key_env")


@dataclass(frozen=True)
class EffectiveSettings:
    """层叠之后的有效值。CLI 之后只认这一份，不再回头看 argv 与配置文件。

    端点三项可以是 `None`：`None` 是「这一项没有默认」，不是「空字符串」——缺它由 CLI 在
    session 开始之前当场判掉（`config-layering` 的「端点必需项缺失当场失败」）。
    """

    provider: str
    base_url: str | None
    model: str | None
    api_key_env: str | None
    max_turns: int
    window: int
    reserve: int
    append_system_prompt: str
    sandbox: SandboxLevel
    approval: ApprovalMode
    tools: list[str] | None
    session_dir: str | None
    workspace: str | None


def _from_layers(args: argparse.Namespace, config: Mapping[str, Any], name: str) -> Any:
    """这一项在 CLI 层或配置文件层给过；没给返回 `None`。"""
    from_flag = getattr(args, name, None)
    if from_flag is not None:
        return from_flag
    if name in config:
        return config[name]
    return None


def _provider_of(
    args: argparse.Namespace, config: Mapping[str, Any], env: Mapping[str, str]
) -> str:
    """`provider` 的内置默认这一层：CLI 与配置文件都没给时才看密钥在场（ADR-0027）。"""
    given = _from_layers(args, config, "provider")
    if given is not None:
        return str(given)
    return "openai" if env.get(DEFAULT_PROVIDER_KEY_ENV) else DEFAULT_PROVIDER


def layer_settings(
    args: argparse.Namespace,
    config: Mapping[str, Any],
    env: Mapping[str, str] | None = None,
) -> EffectiveSettings:
    """把三层取值塌成一份有效设置。"""
    source_env: Mapping[str, str] = os.environ if env is None else env
    values: dict[str, Any] = {}
    for name, builtin in BUILTIN_DEFAULTS.items():
        # 没有对应 flag 的字段（`tools` 与 `approval`）在 CLI 层就是「没给」。
        from_layer = _from_layers(args, config, name)
        values[name] = builtin if from_layer is None else from_layer

    provider = _provider_of(args, config, source_env)
    values["provider"] = provider
    # 预设只填没被给的那几项，MUST NOT 覆盖已给出的那一项。未知的 provider 名字没有预设，
    # 它的三项一律 `None`：CLI 在那之前就以 `UNKNOWN_PROVIDER` 拒掉了。
    preset = PROVIDER_PRESETS.get(provider)
    if preset is None:
        defaults: tuple[str | None, ...] = (None, None, None)
    else:
        defaults = (preset.base_url, preset.model, preset.api_key_env)
    for name, fallback in zip(_ENDPOINT_FIELDS, defaults, strict=True):
        from_layer = _from_layers(args, config, name)
        values[name] = fallback if from_layer is None else from_layer

    return EffectiveSettings(**values)
