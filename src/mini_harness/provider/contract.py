"""Provider 契约：回合循环只依赖 `generate` 这一个方法。"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from typing import Any, Protocol

from pydantic import BaseModel, Field

from mini_harness.events.fold import Message


class ToolCall(BaseModel):
    """模型请求的一次工具调用。"""

    id: str
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class Usage(BaseModel):
    """一次模型调用的用量。"""

    input_tokens: int = 0
    output_tokens: int = 0


class ProviderAttempt(BaseModel):
    """一次被重试掉的失败尝试。重试事实随结果回到回合循环，由循环写进日志。"""

    attempt: int
    status: int


class AssistantTurn(BaseModel):
    """Provider 成功时的返回值。"""

    content: str
    finish_reason: str
    tool_calls: list[ToolCall] = Field(default_factory=list)
    usage: Usage = Field(default_factory=Usage)
    attempts: list[ProviderAttempt] = Field(default_factory=list)


class ToolSpec(BaseModel):
    """给模型看的工具描述。`parameters` 是参数 JSON Schema，由注册表从派发侧的参数模型派生。"""

    name: str
    description: str
    parameters: dict[str, Any] = Field(default_factory=dict)


class ProviderFailure:
    """Provider 失败也是结果：`PROVIDER_EXHAUSTED` / `PROVIDER_SCHEMA_INVALID` /
    `PROVIDER_HTTP_STATUS` / `PROVIDER_CONTEXT_OVERFLOW` / `PROVIDER_TIMEOUT` /
    `PROVIDER_TRANSPORT` / `PROVIDER_ABORTED`。"""

    def __init__(
        self,
        code: str,
        detail: str = "",
        attempts: Sequence[ProviderAttempt] = (),
    ) -> None:
        self.code = code
        self.detail = detail
        self.attempts = list(attempts)


class Provider(Protocol):
    """模型层唯一入口。"""

    async def generate(
        self,
        messages: Sequence[Message],
        tools: Sequence[ToolSpec],
        signal: asyncio.Event,
    ) -> AssistantTurn | ProviderFailure: ...
