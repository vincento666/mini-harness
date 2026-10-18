"""OpenAI 兼容 provider：把 `generate` 契约翻译成一次非流式 chat completions 请求。

**httpx 只允许出现在这个模块**（design D1）：其它模块 import httpx 就是把外部依赖漏进内核。
HTTP 层由构造入参注入，seam ⑤ 的判据因此不跑网络、不需要密钥。
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Sequence
from typing import Any

import httpx

from mini_harness.events.fold import Message
from mini_harness.provider.contract import (
    AssistantTurn,
    ProviderFailure,
    ToolCall,
    ToolSpec,
    Usage,
)

_TIMEOUT_S = 30.0


def _wire_messages(messages: Sequence[Message]) -> list[dict[str, Any]]:
    """内核的消息形状 → chat completions 的消息形状（`arguments` 在协议里是 JSON 字符串）。"""
    wire: list[dict[str, Any]] = []
    for message in messages:
        entry: dict[str, Any] = {"role": message.role, "content": message.content}
        if message.tool_call_id is not None:
            entry["tool_call_id"] = message.tool_call_id
        if message.tool_calls:
            entry["tool_calls"] = [
                {
                    "id": str(call.get("id", "")),
                    "type": "function",
                    "function": {
                        "name": str(call.get("name", "")),
                        "arguments": json.dumps(call.get("arguments", {}), ensure_ascii=False),
                    },
                }
                for call in message.tool_calls
            ]
        wire.append(entry)
    return wire


def _wire_tools(tools: Sequence[ToolSpec]) -> list[dict[str, Any]]:
    return [
        {
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.parameters,
            },
        }
        for tool in tools
    ]


def _schema_failure(detail: str) -> ProviderFailure:
    return ProviderFailure(code="PROVIDER_SCHEMA_INVALID", detail=detail)


def _parse_response(response: httpx.Response) -> AssistantTurn | ProviderFailure:
    try:
        payload = response.json()
    except ValueError:
        return _schema_failure("响应体不是合法 JSON")
    if not isinstance(payload, dict):
        return _schema_failure("响应体不是对象")

    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        return _schema_failure("响应缺少 choices")
    first = choices[0]
    message = first.get("message")
    if not isinstance(message, dict):
        return _schema_failure("choices[0] 缺少 message")
    finish_reason = first.get("finish_reason")
    if not isinstance(finish_reason, str):
        return _schema_failure("响应缺少 finish_reason")

    raw_calls = message.get("tool_calls") or []
    if not isinstance(raw_calls, list):
        return _schema_failure("message.tool_calls 不是数组")
    tool_calls: list[ToolCall] = []
    for raw in raw_calls:
        if not isinstance(raw, dict):
            return _schema_failure("tool_calls 里有一条不是对象")
        function = raw.get("function")
        if not isinstance(function, dict):
            return _schema_failure("tool_calls 里有一条缺少 function")
        arguments = function.get("arguments", "{}")
        if isinstance(arguments, str):
            try:
                parsed = json.loads(arguments)
            except json.JSONDecodeError:
                return _schema_failure("tool_calls 的 arguments 不是合法 JSON")
        else:
            parsed = arguments
        if not isinstance(parsed, dict):
            return _schema_failure("tool_calls 的 arguments 不是对象")
        tool_calls.append(
            ToolCall(
                id=str(raw.get("id", "")),
                name=str(function.get("name", "")),
                arguments=parsed,
            )
        )

    usage = payload.get("usage")
    usage = usage if isinstance(usage, dict) else {}
    return AssistantTurn(
        content=str(message.get("content") or ""),
        finish_reason=finish_reason,
        tool_calls=tool_calls,
        usage=Usage(
            input_tokens=int(usage.get("prompt_tokens", 0) or 0),
            output_tokens=int(usage.get("completion_tokens", 0) or 0),
        ),
    )


class OpenAICompatProvider:
    """模型层的第二个实现：与 mock 同一个 `generate` 契约，回合循环不得因 provider 而改变。"""

    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        api_key: str | None,
        transport: httpx.AsyncBaseTransport | None = None,
        timeout_s: float = _TIMEOUT_S,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._api_key = api_key
        self._transport = transport
        self._timeout_s = timeout_s

    async def generate(
        self,
        messages: Sequence[Message],
        tools: Sequence[ToolSpec],
        signal: asyncio.Event,
    ) -> AssistantTurn | ProviderFailure:
        if signal.is_set():
            return ProviderFailure(code="PROVIDER_ABORTED", detail="取消信号已置位，未发出请求")

        headers: dict[str, str] = {}
        if self._api_key:
            headers["authorization"] = f"Bearer {self._api_key}"
        body = {
            "model": self._model,
            "messages": _wire_messages(messages),
            "tools": _wire_tools(tools),
        }

        async with httpx.AsyncClient(transport=self._transport, timeout=self._timeout_s) as client:
            try:
                response = await client.post(
                    f"{self._base_url}/chat/completions", json=body, headers=headers
                )
            except httpx.TimeoutException:
                return ProviderFailure(code="PROVIDER_TIMEOUT", detail=f"{self._base_url} 超时")
            except httpx.HTTPError as error:
                return ProviderFailure(code="PROVIDER_TRANSPORT", detail=str(error))

        return _parse_response(response)
