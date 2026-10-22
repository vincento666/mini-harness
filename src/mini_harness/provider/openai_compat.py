"""OpenAI 兼容 provider：把 `generate` 契约翻译成一次非流式 chat completions 请求。

**httpx 只允许出现在这个模块**（design D1）：其它模块 import httpx 就是把外部依赖漏进内核。
HTTP 层由构造入参注入，seam ⑤ 的判据因此不跑网络、不需要密钥。
重试事实（429 / 5xx）随结果回到回合循环——provider 不写日志（不变量 A）。
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Sequence
from typing import Any, Literal, get_args
from urllib.parse import urlsplit

import httpx

from mini_harness.events.fold import Message
from mini_harness.provider.contract import (
    AssistantTurn,
    ProviderAttempt,
    ProviderFailure,
    ToolCall,
    ToolSpec,
    Usage,
)

# 决策 15：模型请求的超时是实现常量 120 秒，`minihns run` 没有改变它的开关。
_TIMEOUT_S = 120.0

# 上下文超限在 OpenAI 兼容协议里的错误码；它加下面那张短语表塌成 `PROVIDER_CONTEXT_OVERFLOW`。
CONTEXT_OVERFLOW_ERROR_CODE = "context_length_exceeded"

# 各家兼容端点报「提示词装不进上下文」的措辞不一样：本机真端点给的是 `type:
# invalid_request_error` 加一句 `leaves no room to answer in the context`，没有 `error.code`
# （ADR-0022）。短语表由适配层维护——照 DSH「分类由适配器维护」的口径，猜正文的代价记在那里。
ContextOverflowPhrase = Literal[
    "leaves no room to answer",
    "maximum context length",
    "context length exceeded",
    "prompt is too long",
]

CONTEXT_OVERFLOW_PHRASES: frozenset[str] = frozenset(get_args(ContextOverflowPhrase))


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


def _retryable(status: int) -> bool:
    """429 与 5xx 可重试一次；其余 4xx（含 401）不是重试的理由。"""
    return status == 429 or status >= 500


def validate_base_url(value: str) -> str | None:
    """`--base-url` 的形状检查：返回 `None` 表示可用，否则返回一句说明哪里不对。

    放在本模块而不是 CLI 里：httpx 只允许出现在这里（design D1）。形状不合法的 URL
    在 httpx 构造请求时抛 `ValueError` / `httpx.InvalidURL`，后者不是 `httpx.HTTPError`
    的子类——先在这里挡住，CLI 才能把它当参数错误（退出码 2）处理。
    """
    try:
        parts = urlsplit(value)
    except ValueError as error:
        return f"--base-url {value!r} 不是合法 URL：{error}"
    if parts.scheme not in ("http", "https"):
        return f"--base-url {value!r} 必须以 http:// 或 https:// 开头"
    if parts.hostname is None:
        return f"--base-url {value!r} 没有主机名"
    return None


async def _post(
    client: httpx.AsyncClient,
    base_url: str,
    body: dict[str, Any],
    headers: dict[str, str],
    attempts: Sequence[ProviderAttempt],
) -> httpx.Response | ProviderFailure:
    try:
        return await client.post(f"{base_url}/chat/completions", json=body, headers=headers)
    except httpx.TimeoutException:
        return ProviderFailure(
            code="PROVIDER_TIMEOUT", detail=f"{base_url} 超时", attempts=attempts
        )
    except httpx.HTTPError as error:
        return ProviderFailure(code="PROVIDER_TRANSPORT", detail=str(error), attempts=attempts)
    except (httpx.InvalidURL, ValueError) as error:
        # URL 构造阶段的失败：不在 httpx.HTTPError 那一族里，不捕就是未捕获异常（不变量 B）。
        return ProviderFailure(code="PROVIDER_TRANSPORT", detail=str(error), attempts=attempts)


def _schema_failure(detail: str, attempts: Sequence[ProviderAttempt]) -> ProviderFailure:
    return ProviderFailure(code="PROVIDER_SCHEMA_INVALID", detail=detail, attempts=attempts)


def _reports_context_overflow(response: httpx.Response) -> bool:
    """design D8 与 D3：错误对象的 `code` 命中，或 `message` 命中短语表里的某一条。

    短语表大小写不敏感、整句里找子串；不解析消息里的 token 数、也不按状态码猜。
    读不出 body、错误对象不是对象、`message` 不是字符串，都当不是。
    """
    try:
        payload = response.json()
    except ValueError:
        return False
    if not isinstance(payload, dict):
        return False
    error = payload.get("error")
    if not isinstance(error, dict):
        return False
    if error.get("code") == CONTEXT_OVERFLOW_ERROR_CODE:
        return True
    message = error.get("message")
    if not isinstance(message, str):
        return False
    lowered = message.lower()
    return any(phrase in lowered for phrase in CONTEXT_OVERFLOW_PHRASES)


def _parse_response(
    response: httpx.Response, attempts: Sequence[ProviderAttempt]
) -> AssistantTurn | ProviderFailure:
    try:
        payload = response.json()
    except ValueError:
        return _schema_failure("响应体不是合法 JSON", attempts)
    if not isinstance(payload, dict):
        return _schema_failure("响应体不是对象", attempts)

    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        return _schema_failure("响应缺少 choices", attempts)
    first = choices[0]
    message = first.get("message")
    if not isinstance(message, dict):
        return _schema_failure("choices[0] 缺少 message", attempts)
    finish_reason = first.get("finish_reason")
    if not isinstance(finish_reason, str):
        return _schema_failure("响应缺少 finish_reason", attempts)

    raw_calls = message.get("tool_calls") or []
    if not isinstance(raw_calls, list):
        return _schema_failure("message.tool_calls 不是数组", attempts)
    tool_calls: list[ToolCall] = []
    for raw in raw_calls:
        if not isinstance(raw, dict):
            return _schema_failure("tool_calls 里有一条不是对象", attempts)
        function = raw.get("function")
        if not isinstance(function, dict):
            return _schema_failure("tool_calls 里有一条缺少 function", attempts)
        arguments = function.get("arguments", "{}")
        if isinstance(arguments, str):
            try:
                parsed = json.loads(arguments)
            except json.JSONDecodeError:
                return _schema_failure("tool_calls 的 arguments 不是合法 JSON", attempts)
        else:
            parsed = arguments
        if not isinstance(parsed, dict):
            return _schema_failure("tool_calls 的 arguments 不是对象", attempts)
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
        attempts=list(attempts),
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
            # 决策 23：显式要求允许一轮多个调用，不指望模型的心情。
            "parallel_tool_calls": True,
        }
        attempts: list[ProviderAttempt] = []

        # trust_env=False：不继承 HTTP_PROXY / NO_PROXY / netrc。
        # 本机实测 `NO_PROXY=localhost,127.0.0.1,::1,[::1]` 会让 httpx 在构造客户端时抛
        # `InvalidURL: Invalid port: ':1]'`——它不是 `httpx.HTTPError` 的子类，会绕过下面
        # 的失败捕获、直接打断进程（违反不变量 B）。见 ADR-0006 的简化清单。
        async with httpx.AsyncClient(
            transport=self._transport, timeout=self._timeout_s, trust_env=False
        ) as client:
            first = await _post(client, self._base_url, body, headers, attempts)
            if isinstance(first, ProviderFailure):
                return first
            response = first
            if _retryable(response.status_code):
                attempts.append(ProviderAttempt(attempt=1, status=response.status_code))
                if signal.is_set():
                    # 规格：取消信号已置位时不得再发出新的请求——重试也是一次新的请求。
                    return ProviderFailure(
                        code="PROVIDER_ABORTED",
                        detail="取消信号已置位，重试未发出",
                        attempts=attempts,
                    )
                second = await _post(client, self._base_url, body, headers, attempts)
                if isinstance(second, ProviderFailure):
                    return second
                response = second
                if _retryable(response.status_code):
                    return ProviderFailure(
                        code="PROVIDER_HTTP_STATUS",
                        detail=f"HTTP {response.status_code}",
                        attempts=attempts,
                    )

        if response.status_code >= 400:
            if _reports_context_overflow(response):
                return ProviderFailure(
                    code="PROVIDER_CONTEXT_OVERFLOW",
                    detail=f"HTTP {response.status_code}：上下文超出窗口",
                    attempts=attempts,
                )
            return ProviderFailure(
                code="PROVIDER_HTTP_STATUS",
                detail=f"HTTP {response.status_code}",
                attempts=attempts,
            )
        return _parse_response(response, attempts)
