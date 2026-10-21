"""一次 session 的设置：`session/start.payload` 由它派生，同一事实只写一遍。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

# 围栏的两条独立轴：设置对象带着它们，围栏模块消费它们。
SandboxLevel = Literal["read-only", "workspace-write", "danger-full-access"]
ApprovalMode = Literal["ask", "auto"]

# 窗口预算的默认值只写在这里：CLI 的 `--window` / `--reserve` 默认值取自同一份。
DEFAULT_WINDOW = 128000
DEFAULT_RESERVE = 8192

# 内置默认只住在这一处：CLI 的 flag 默认是 `None` 哨兵，配置文件也没写时才落到这一份。
DEFAULT_PROVIDER = "mock"
DEFAULT_BASE_URL = "https://api.deepseek.com"
DEFAULT_MODEL = "deepseek-chat"
DEFAULT_API_KEY_ENV = "DEEPSEEK_API_KEY"
DEFAULT_MAX_TURNS = 8
DEFAULT_SANDBOX: SandboxLevel = "workspace-write"
DEFAULT_APPROVAL: ApprovalMode = "ask"
DEFAULT_APPEND_SYSTEM_PROMPT = ""


@dataclass(frozen=True)
class SessionSettings:
    """一次运行的全部设置（不含 prompt：prompt 是这一轮的内容，不是设置）。"""

    workspace: Path
    provider_name: str
    max_turns: int
    sandbox: SandboxLevel = "workspace-write"
    approval: ApprovalMode = "ask"
    append_system_prompt: str = ""
    # 窗口预算的两个参数（不变量 D）：`--window` 与 `--reserve`。
    window: int = DEFAULT_WINDOW
    reserve: int = DEFAULT_RESERVE
    # 只有 openai 路径带这三条；`api_key_env` 记的是环境变量的名字，不是它的值。
    base_url: str | None = None
    model: str | None = None
    api_key_env: str | None = None
