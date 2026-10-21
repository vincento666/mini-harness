"""配置文件读取：一份 TOML 变成设置值映射。"""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

CONFIG_FILE_NAME = "mini.config.toml"


def load_config(path: Path) -> dict[str, Any]:
    """读一份 TOML，返回顶层键到值的映射。"""
    with path.open("rb") as handle:
        return tomllib.load(handle)


def discover_config(workspace: Path, explicit: str | None) -> Path | None:
    """配置文件发现：`--config` 显式指定的路径优先，其次工作区根的 `mini.config.toml`。

    工作区用的是「`--workspace` 或当前目录」这一层：配置文件里的 `workspace` 不反过来决定
    配置文件自己在哪儿（design D7）。
    """
    if explicit is not None:
        return Path(explicit)
    candidate = workspace / CONFIG_FILE_NAME
    return candidate if candidate.is_file() else None
