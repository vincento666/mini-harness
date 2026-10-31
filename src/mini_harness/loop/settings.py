"""一次 session 的设置：`session/start.payload` 由它派生，同一事实只写一遍。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from mini_harness.context import budget as context_budget

DEFAULT_COMPACTION_THRESHOLD_RATIO = context_budget.DEFAULT_COMPACTION_THRESHOLD_RATIO
DEFAULT_COMPACTION_HEADROOM_TOKENS = context_budget.DEFAULT_COMPACTION_HEADROOM_TOKENS
DEFAULT_COMPACTION_RETAIN_RATIO = context_budget.DEFAULT_COMPACTION_RETAIN_RATIO
DEFAULT_COMPACTION_RETAIN_TOKENS = context_budget.DEFAULT_COMPACTION_RETAIN_TOKENS

# 围栏的两条独立轴：设置对象带着它们，围栏模块消费它们。
SandboxLevel = Literal["read-only", "workspace-write", "danger-full-access"]
ApprovalMode = Literal["ask", "auto"]
ReasoningEffort = Literal["off", "low", "high", "max"]

# 词表在运行期也要有一份：`--sandbox` / `--approval` 的 choices 与配置文件读进来的值都判这一份。
SANDBOX_LEVELS: tuple[SandboxLevel, ...] = ("read-only", "workspace-write", "danger-full-access")
APPROVAL_MODES: tuple[ApprovalMode, ...] = ("ask", "auto")

# 窗口预算的默认值只写在这里：CLI 的 `--window` / `--reserve` 默认值取自同一份。
DEFAULT_WINDOW = 128000
DEFAULT_RESERVE = 8192

# 内置默认只住在这一处：CLI 的 flag 默认是 `None` 哨兵，配置文件也没写时才落到这一份。
# provider 的内置默认由环境决定（ADR-0027）：`MINIHNS_API_KEY` 已设且非空时是 `openai`，
# 否则是 `mock`。
DEFAULT_PROVIDER = "mock"
DEFAULT_PROVIDER_KEY_ENV = "MINIHNS_API_KEY"
DEFAULT_MAX_TURNS = 8
DEFAULT_SANDBOX: SandboxLevel = "workspace-write"
DEFAULT_APPROVAL: ApprovalMode = "ask"
DEFAULT_APPEND_SYSTEM_PROMPT = ""
REASONING_EFFORTS: tuple[ReasoningEffort, ...] = ("off", "low", "high", "max")
DEFAULT_REASONING_EFFORT: ReasoningEffort = "high"

# provider 名字是「端点预设名」，不是适配器名（ADR-0027）：`openai` 与 `deepseek` 都由
# openai 兼容适配器执行，差别只在这三项默认。表里只有环境变量的名字，没有任何密钥的值；
# `None` 就是「这一项没有默认」，缺它要在 session 开始之前当场失败。
PROVIDER_NAMES: tuple[str, ...] = ("mock", "openai", "deepseek")


@dataclass(frozen=True)
class ProviderPreset:
    """一个 provider 名字对应的三项端点默认。"""

    base_url: str | None
    model: str | None
    api_key_env: str | None


PROVIDER_PRESETS: dict[str, ProviderPreset] = {
    "mock": ProviderPreset(None, None, None),
    "openai": ProviderPreset("https://api.openai.com/v1", None, DEFAULT_PROVIDER_KEY_ENV),
    "deepseek": ProviderPreset("https://api.deepseek.com", "deepseek-chat", "DEEPSEEK_API_KEY"),
}


@dataclass(frozen=True)
class ProviderEndpoint:
    """openai 兼容端点的三条事实：地址、模型名、密钥环境变量的名字。

    它记的是环境变量的名字，不是它的值；`None`（没有这个对象）就是「本次运行没有端点」。
    """

    base_url: str
    model: str
    api_key_env: str


@dataclass(frozen=True)
class SessionSettings:
    """一次运行的全部设置（不含 prompt：prompt 是这一轮的内容，不是设置）。"""

    workspace: Path
    provider_name: str
    max_turns: int
    sandbox: SandboxLevel = "workspace-write"
    approval: ApprovalMode = "ask"
    append_system_prompt: str = ""
    reasoning_effort: ReasoningEffort = DEFAULT_REASONING_EFFORT
    # 窗口预算的两个参数（不变量 D）：`--window` 与 `--reserve`。
    window: int = DEFAULT_WINDOW
    reserve: int = DEFAULT_RESERVE
    # 压缩参数：默认值保持 DSH 的形状；ratio/tokens 由配置给出。
    compaction_threshold_ratio: float = DEFAULT_COMPACTION_THRESHOLD_RATIO
    compaction_headroom_tokens: int = DEFAULT_COMPACTION_HEADROOM_TOKENS
    compaction_retain_ratio: float = DEFAULT_COMPACTION_RETAIN_RATIO
    compaction_retain_tokens: int = DEFAULT_COMPACTION_RETAIN_TOKENS
    # 端点三条结伴出现：payload 里那三个字段由这一个对象派生。
    endpoint: ProviderEndpoint | None = None
    # 平台事实（ADR-0029）：由入口填，`session/start` 原样写下去；`None` 就是「这次没有这份事实」。
    platform: dict[str, str] | None = None
