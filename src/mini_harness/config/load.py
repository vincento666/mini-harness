"""配置文件读取：一份 TOML 变成设置值映射。"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, get_args

CONFIG_FILE_NAME = "mini.config.toml"

# 可配的是设置类字段全表。数字位上不接受 `bool`——它是 `int` 的子类，`max_turns = true` 是类型不对。
SETTINGS_FIELDS: dict[str, tuple[type[Any], ...]] = {
    "provider": (str,),
    "base_url": (str,),
    "model": (str,),
    "api_key_env": (str,),
    "max_turns": (int,),
    "window": (int,),
    "reserve": (int,),
    "append_system_prompt": (str,),
    "sandbox": (str,),
    "approval": (str,),
    "tools": (list,),
    "session_dir": (str,),
    "workspace": (str,),
}

# 一次运行的 prompt 与 fixture 只来自命令行；密钥只走环境变量的名字，值不进配置文件。
FORBIDDEN_FIELDS: frozenset[str] = frozenset({"prompt", "fixture", "api_key"})

# 配置层的失败码词表（ADR-0002 第 40 条在 M7 收）：词表外的码不得临时新造。
ConfigCode = Literal[
    "CONFIG_NOT_FOUND",
    "CONFIG_INVALID_TOML",
    "CONFIG_UNKNOWN_KEY",
    "CONFIG_FORBIDDEN_KEY",
    "CONFIG_INVALID_VALUE",
    "UNKNOWN_TOOL_NAME",
]
CONFIG_CODES: frozenset[str] = frozenset(get_args(ConfigCode))


@dataclass(frozen=True)
class ConfigFailure:
    """配置层失败：`code` 是给判据用的事实，`detail` 面向人。"""

    code: ConfigCode
    detail: str


def validate_config(values: dict[str, Any]) -> ConfigFailure | None:
    """按字段表校验一份配置：不合法是一条结果，合法返回 `None`。"""
    for key, value in values.items():
        if key in FORBIDDEN_FIELDS:
            return ConfigFailure(
                "CONFIG_FORBIDDEN_KEY", f"配置文件里不允许出现 {key}：它不属于设置"
            )
        allowed = SETTINGS_FIELDS.get(key)
        if allowed is None:
            return ConfigFailure("CONFIG_UNKNOWN_KEY", f"配置文件里有未知的键：{key}")
        if not isinstance(value, allowed) or (int in allowed and isinstance(value, bool)):
            return ConfigFailure(
                "CONFIG_INVALID_VALUE", f"键 {key} 的值类型不对：{type(value).__name__}"
            )
    return None


def load_config(path: Path) -> dict[str, Any] | ConfigFailure:
    """读一份 TOML 并按字段表校验它；读不成或形状不对都是一条结果，不是异常。"""
    try:
        with path.open("rb") as handle:
            values = tomllib.load(handle)
    except FileNotFoundError:
        return ConfigFailure("CONFIG_NOT_FOUND", f"找不到配置文件：{path}")
    except OSError as error:
        # 路径在但读不成（指向目录、权限不够）：同一条「读不到」，不是 traceback。
        return ConfigFailure("CONFIG_NOT_FOUND", f"读不到配置文件：{path}（{error}）")
    except tomllib.TOMLDecodeError as error:
        return ConfigFailure("CONFIG_INVALID_TOML", f"{path}: {error}")
    failure = validate_config(values)
    if failure is not None:
        return failure
    return values


def discover_config(workspace: Path, explicit: str | None) -> Path | None:
    """配置文件发现：`--config` 显式指定的路径优先，其次工作区根的 `mini.config.toml`。

    工作区用的是「`--workspace` 或当前目录」这一层：配置文件里的 `workspace` 不反过来决定
    配置文件自己在哪儿（design D7）。
    """
    if explicit is not None:
        return Path(explicit)
    candidate = workspace / CONFIG_FILE_NAME
    return candidate if candidate.is_file() else None
