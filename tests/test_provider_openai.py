"""seam ⑤：OpenAI 兼容适配器。HTTP 层由测试注入，判据不跑网络。"""

from __future__ import annotations

import asyncio
import inspect
import json
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx

from mini_harness.events.fold import Message
from mini_harness.loop.settings import ProviderEndpoint
from mini_harness.provider.contract import AssistantTurn, ProviderFailure, ToolSpec
from mini_harness.provider.openai_compat import OpenAICompatProvider

_BASE_URL = "http://127.0.0.1:9/v1"

# 真端点回来的东西：判据读 fixture，不读手编的桩数据（ADR-0022）。
_FIXTURE_DIR = Path(__file__).parent / "fixtures" / "real_endpoint"

_OK_BODY: dict[str, Any] = {
    "id": "chatcmpl-1",
    "choices": [
        {
            "index": 0,
            "message": {"role": "assistant", "content": "done", "tool_calls": []},
            "finish_reason": "stop",
        }
    ],
    "usage": {"prompt_tokens": 11, "completion_tokens": 5, "total_tokens": 16},
}

_READ_TOOL = ToolSpec(
    name="read",
    description="读一个文件",
    parameters={
        "type": "object",
        "properties": {"file_path": {"type": "string", "description": "目标文件"}},
        "required": ["file_path"],
    },
)


def _provider(
    *,
    handler: Callable[[httpx.Request], httpx.Response],
    api_key: str | None = None,
) -> tuple[OpenAICompatProvider, list[httpx.Request]]:
    seen: list[httpx.Request] = []

    def record(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return handler(request)

    provider = OpenAICompatProvider(
        base_url=_BASE_URL,
        model="test-model",
        api_key=api_key,
        transport=httpx.MockTransport(record),
    )
    return provider, seen


async def _generate(provider: OpenAICompatProvider) -> Any:
    return await provider.generate(
        [Message(role="user", content="任务")], [_READ_TOOL], asyncio.Event()
    )


def _body(request: httpx.Request) -> dict[str, Any]:
    return json.loads(request.content.decode("utf-8"))


async def test_openai_stream_content_deltas() -> None:
    seen_text: list[str] = []

    async def sink(text: str) -> None:
        seen_text.append(text)

    stream = (
        'data: {"choices":[{"delta":{"content":"你"},"finish_reason":null}]}\n\n'
        'data: {"choices":[{"delta":{"content":"好"},"finish_reason":null}]}\n\n'
        'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}\n\n'
        "data: [DONE]\n\n"
    )
    provider, seen = _provider(
        handler=lambda request: httpx.Response(
            200, text=stream, headers={"content-type": "text/event-stream"}
        )
    )

    turn = await provider.generate([], [], asyncio.Event(), on_delta=sink)

    assert isinstance(turn, AssistantTurn)
    assert seen_text == ["你", "好"]
    assert turn.content == "你好"
    assert turn.finish_reason == "stop"
    assert _body(seen[0])["stream"] is True


async def test_a_stream_http_error_is_a_provider_failure() -> None:
    async def sink(text: str) -> None:
        raise AssertionError("不会走到这里")

    provider, _ = _provider(
        handler=lambda request: httpx.Response(
            400,
            json={"error": {"message": "bad request"}},
            headers={"content-type": "application/json"},
        )
    )

    outcome = await provider.generate([], [], asyncio.Event(), on_delta=sink)

    assert isinstance(outcome, ProviderFailure)
    assert outcome.code == "PROVIDER_HTTP_STATUS"


async def test_a_stream_with_invalid_json_is_a_schema_failure() -> None:
    async def sink(text: str) -> None:
        raise AssertionError("不会走到这里")

    provider, _ = _provider(
        handler=lambda request: httpx.Response(
            200, text="data: not-json\n\n", headers={"content-type": "text/event-stream"}
        )
    )

    outcome = await provider.generate([], [], asyncio.Event(), on_delta=sink)

    assert isinstance(outcome, ProviderFailure)
    assert outcome.code == "PROVIDER_SCHEMA_INVALID"


async def test_a_stream_with_a_non_object_data_is_a_schema_failure() -> None:
    async def sink(text: str) -> None:
        raise AssertionError("不会走到这里")

    provider, _ = _provider(
        handler=lambda request: httpx.Response(
            200, text="data: []\n\n", headers={"content-type": "text/event-stream"}
        )
    )

    outcome = await provider.generate([], [], asyncio.Event(), on_delta=sink)

    assert isinstance(outcome, ProviderFailure)
    assert outcome.code == "PROVIDER_SCHEMA_INVALID"


async def test_a_stream_without_finish_reason_is_a_schema_failure() -> None:
    async def sink(text: str) -> None:
        return None

    provider, _ = _provider(
        handler=lambda request: httpx.Response(
            200,
            text='data: {"choices":[{"delta":{"content":"你"}}]}\n\ndata: [DONE]\n\n',
            headers={"content-type": "text/event-stream"},
        )
    )

    outcome = await provider.generate([], [], asyncio.Event(), on_delta=sink)

    assert isinstance(outcome, ProviderFailure)
    assert outcome.code == "PROVIDER_SCHEMA_INVALID"


async def test_a_stream_usage_chunk_with_empty_choices_is_accepted() -> None:
    async def sink(text: str) -> None:
        return None

    stream = (
        'data: {"choices":[{"delta":{"content":"好"},"finish_reason":null}]}\n\n'
        'data: {"choices":[],"usage":{"prompt_tokens":7,"completion_tokens":2}}\n\n'
        'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}\n\n'
        "data: [DONE]\n\n"
    )
    provider, _ = _provider(
        handler=lambda request: httpx.Response(
            200, text=stream, headers={"content-type": "text/event-stream"}
        )
    )

    turn = await provider.generate([], [], asyncio.Event(), on_delta=sink)

    assert isinstance(turn, AssistantTurn)
    assert turn.usage.input_tokens == 7
    assert turn.usage.output_tokens == 2


async def test_a_stream_with_a_non_object_choice_is_a_schema_failure() -> None:
    async def sink(text: str) -> None:
        return None

    provider, _ = _provider(
        handler=lambda request: httpx.Response(
            200,
            text='data: {"choices":[1]}\n\n',
            headers={"content-type": "text/event-stream"},
        )
    )

    outcome = await provider.generate([], [], asyncio.Event(), on_delta=sink)

    assert isinstance(outcome, ProviderFailure)
    assert outcome.code == "PROVIDER_SCHEMA_INVALID"


async def test_a_cancel_during_stream_is_provider_aborted() -> None:
    signal = asyncio.Event()

    async def sink(text: str) -> None:
        signal.set()

    stream = (
        'data: {"choices":[{"delta":{"content":"你"},"finish_reason":null}]}\n\ndata: [DONE]\n\n'
    )
    provider, _ = _provider(
        handler=lambda request: httpx.Response(
            200, text=stream, headers={"content-type": "text/event-stream"}
        )
    )

    outcome = await provider.generate([], [], signal, on_delta=sink)

    assert isinstance(outcome, ProviderFailure)
    assert outcome.code == "PROVIDER_ABORTED"


async def test_a_stream_transport_error_is_a_failure() -> None:
    async def sink(text: str) -> None:
        return None

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom", request=request)

    provider, _ = _provider(handler=handler)

    outcome = await provider.generate([], [], asyncio.Event(), on_delta=sink)

    assert isinstance(outcome, ProviderFailure)
    assert outcome.code == "PROVIDER_TRANSPORT"


async def test_a_stream_timeout_is_a_failure() -> None:
    async def sink(text: str) -> None:
        return None

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    provider, _ = _provider(handler=handler)

    outcome = await provider.generate([], [], asyncio.Event(), on_delta=sink)

    assert isinstance(outcome, ProviderFailure)
    assert outcome.code == "PROVIDER_TIMEOUT"


async def test_openai_stream_tool_calls_are_assembled_by_index() -> None:
    seen_text: list[str] = []

    async def sink(text: str) -> None:
        seen_text.append(text)

    stream = (
        'data: {"choices":[{"delta":{"tool_calls":[{"index":0,"id":"c1",'
        '"function":{"name":"read","arguments":"{\\"file_path\\":"}}]},'
        '"finish_reason":null}]}\n\n'
        'data: {"choices":[{"delta":{"tool_calls":[{"index":0,'
        '"function":{"arguments":"\\"a.md\\"}"}}]},'
        '"finish_reason":null}]}\n\n'
        'data: {"choices":[{"delta":{"tool_calls":[{"index":1,"id":"c2",'
        '"function":{"name":"bash","arguments":"{\\"command\\":\\"echo hi\\"}"}}]},'
        '"finish_reason":null}]}\n\n'
        'data: {"choices":[{"delta":{},"finish_reason":"tool_calls"}]}\n\n'
        "data: [DONE]\n\n"
    )
    provider, _ = _provider(
        handler=lambda request: httpx.Response(
            200, text=stream, headers={"content-type": "text/event-stream"}
        )
    )

    turn = await provider.generate([], [], asyncio.Event(), on_delta=sink)

    assert isinstance(turn, AssistantTurn)
    assert [(call.id, call.name, call.arguments) for call in turn.tool_calls] == [
        ("c1", "read", {"file_path": "a.md"}),
        ("c2", "bash", {"command": "echo hi"}),
    ]
    assert seen_text == []
    assert turn.finish_reason == "tool_calls"


async def test_the_request_posts_to_the_chat_completions_url() -> None:
    provider, seen = _provider(handler=lambda request: httpx.Response(200, json=_OK_BODY))

    await _generate(provider)

    assert len(seen) == 1
    assert seen[0].method == "POST"
    assert str(seen[0].url) == "http://127.0.0.1:9/v1/chat/completions"


async def test_the_request_body_carries_model_messages_and_tools_with_schemas() -> None:
    provider, seen = _provider(handler=lambda request: httpx.Response(200, json=_OK_BODY))

    await _generate(provider)

    body = _body(seen[0])
    assert body["model"] == "test-model"
    assert [message["role"] for message in body["messages"]] == ["user"]
    assert body["tools"] == [
        {
            "type": "function",
            "function": {
                "name": "read",
                "description": "读一个文件",
                "parameters": _READ_TOOL.parameters,
            },
        }
    ]


async def test_the_authorization_header_is_present_only_when_a_key_is_given() -> None:
    anonymous, seen_anonymous = _provider(
        handler=lambda request: httpx.Response(200, json=_OK_BODY)
    )
    keyed, seen_keyed = _provider(
        handler=lambda request: httpx.Response(200, json=_OK_BODY), api_key="sk-test"
    )

    await _generate(anonymous)
    await _generate(keyed)

    assert "authorization" not in seen_anonymous[0].headers
    assert seen_keyed[0].headers["authorization"] == "Bearer sk-test"


async def test_assistant_tool_calls_and_tool_results_are_mapped_to_the_wire_shape() -> None:
    provider, seen = _provider(handler=lambda request: httpx.Response(200, json=_OK_BODY))
    messages = [
        Message(role="system", content="受保护头部"),
        Message(role="user", content="读一下"),
        Message(
            role="assistant",
            content="",
            tool_calls=[{"id": "c1", "name": "read", "arguments": {"file_path": "a.md"}}],
        ),
        Message(role="tool", content="文件内容", tool_call_id="c1"),
    ]

    await provider.generate(messages, [_READ_TOOL], asyncio.Event())

    wire = _body(seen[0])["messages"]
    assert wire[0] == {"role": "system", "content": "受保护头部"}
    assert wire[1] == {"role": "user", "content": "读一下"}
    assert wire[2]["role"] == "assistant"
    assert wire[2]["tool_calls"] == [
        {
            "id": "c1",
            "type": "function",
            "function": {"name": "read", "arguments": '{"file_path": "a.md"}'},
        }
    ]
    assert json.loads(wire[2]["tool_calls"][0]["function"]["arguments"]) == {"file_path": "a.md"}
    assert wire[3] == {"role": "tool", "content": "文件内容", "tool_call_id": "c1"}


async def test_a_valid_response_becomes_an_assistant_turn() -> None:
    provider, _ = _provider(handler=lambda request: httpx.Response(200, json=_OK_BODY))

    turn = await _generate(provider)

    assert isinstance(turn, AssistantTurn)
    assert turn.content == "done"
    assert turn.finish_reason == "stop"
    assert turn.tool_calls == []
    assert turn.usage.input_tokens == 11
    assert turn.usage.output_tokens == 5


async def test_tool_calls_in_the_response_are_parsed_into_calls() -> None:
    body: dict[str, Any] = {
        "id": "chatcmpl-2",
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {
                            "id": "call_1",
                            "type": "function",
                            "function": {"name": "read", "arguments": '{"file_path": "a.md"}'},
                        },
                        {
                            "id": "call_2",
                            "type": "function",
                            "function": {"name": "grep", "arguments": '{"pattern": "x"}'},
                        },
                    ],
                },
                "finish_reason": "tool_calls",
            }
        ],
    }
    provider, _ = _provider(handler=lambda request: httpx.Response(200, json=body))

    turn = await _generate(provider)

    assert isinstance(turn, AssistantTurn)
    assert turn.finish_reason == "tool_calls"
    assert turn.content == ""
    assert [(call.id, call.name, call.arguments) for call in turn.tool_calls] == [
        ("call_1", "read", {"file_path": "a.md"}),
        ("call_2", "grep", {"pattern": "x"}),
    ]


async def test_a_200_response_without_choices_is_a_schema_failure() -> None:
    provider, _ = _provider(handler=lambda request: httpx.Response(200, json={"id": "chatcmpl-3"}))

    outcome = await _generate(provider)

    assert isinstance(outcome, ProviderFailure)
    assert outcome.code == "PROVIDER_SCHEMA_INVALID"
    assert "choices" in outcome.detail


async def test_a_200_response_that_is_not_json_is_a_schema_failure() -> None:
    provider, _ = _provider(
        handler=lambda request: httpx.Response(
            200, text="not json at all", headers={"content-type": "text/plain"}
        )
    )

    outcome = await _generate(provider)

    assert isinstance(outcome, ProviderFailure)
    assert outcome.code == "PROVIDER_SCHEMA_INVALID"


async def test_a_set_cancel_signal_sends_no_request() -> None:
    provider, seen = _provider(handler=lambda request: httpx.Response(200, json=_OK_BODY))
    signal = asyncio.Event()
    signal.set()

    outcome = await provider.generate([Message(role="user", content="任务")], [_READ_TOOL], signal)

    assert seen == []
    assert isinstance(outcome, ProviderFailure)
    assert outcome.code == "PROVIDER_ABORTED"


async def test_a_dead_endpoint_is_a_transport_result() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("端点没在监听", request=request)

    provider, _ = _provider(handler=handler)

    outcome = await _generate(provider)

    assert isinstance(outcome, ProviderFailure)
    assert outcome.code == "PROVIDER_TRANSPORT"


async def test_a_transport_failure_that_is_not_a_connect_error_is_still_a_result() -> None:
    """捕获的是传输层失败这一整类：把它收窄成 `ConnectError` 就该被这条判据打死。"""

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadError("连接被对方掐断", request=request)

    provider, _ = _provider(handler=handler)

    outcome = await _generate(provider)

    assert isinstance(outcome, ProviderFailure)
    assert outcome.code == "PROVIDER_TRANSPORT"


async def test_a_malformed_base_url_is_a_transport_result_not_a_crash() -> None:
    """形状不合法的 URL 在 httpx 构造请求时抛 `ValueError` / `httpx.InvalidURL`，
    它们不是 `httpx.HTTPError` 的子类——必须塌成结果，不得打断进程（不变量 B）。"""
    provider = OpenAICompatProvider(base_url="http://[::1", model="test-model", api_key=None)

    outcome = await _generate(provider)

    assert isinstance(outcome, ProviderFailure)
    assert outcome.code == "PROVIDER_TRANSPORT"


async def test_the_request_body_asks_for_parallel_tool_calls() -> None:
    """决策 23：显式 `parallel_tool_calls = true`。一轮多个调用不该指望模型的心情。"""
    provider, seen = _provider(handler=lambda request: httpx.Response(200, json=_OK_BODY))

    await _generate(provider)

    assert _body(seen[0])["parallel_tool_calls"] is True


async def test_a_cancel_during_a_retry_stops_the_second_request() -> None:
    """规格写「取消信号已置位时 MUST NOT 再发出新的请求」——重试也是一次新的请求。"""
    signal = asyncio.Event()

    def handler(request: httpx.Request) -> httpx.Response:
        signal.set()
        return httpx.Response(429, json={"error": "slow down"})

    provider, seen = _provider(handler=handler)

    outcome = await provider.generate([Message(role="user", content="任务")], [_READ_TOOL], signal)

    assert len(seen) == 1, "重试不得在取消之后发出"
    assert isinstance(outcome, ProviderFailure)
    assert outcome.code == "PROVIDER_ABORTED"
    assert [(attempt.attempt, attempt.status) for attempt in outcome.attempts] == [(1, 429)]


async def test_the_model_request_carries_a_120_second_timeout() -> None:
    """决策 15：模型请求的超时是 120 秒。判据看请求本身带走的超时，不看实现里的常量名。"""
    provider, seen = _provider(handler=lambda request: httpx.Response(200, json=_OK_BODY))

    await _generate(provider)

    assert seen[0].extensions["timeout"] == {
        "connect": 120.0,
        "read": 120.0,
        "write": 120.0,
        "pool": 120.0,
    }


async def test_a_400_saying_context_length_exceeded_is_a_context_overflow() -> None:
    """design D8：`error.code == "context_length_exceeded"` 命中。
    400 不是重试的理由，所以这里一次请求、零次重试。"""
    provider, seen = _provider(
        handler=lambda request: httpx.Response(
            400,
            json={"error": {"code": "context_length_exceeded", "message": "too many tokens"}},
        )
    )

    outcome = await _generate(provider)

    assert len(seen) == 1
    assert isinstance(outcome, ProviderFailure)
    assert outcome.code == "PROVIDER_CONTEXT_OVERFLOW"
    assert outcome.attempts == []


async def test_a_413_saying_context_length_exceeded_collapses_to_the_same_overflow() -> None:
    """超限的线上事实是那个 `error.code`，不是状态码：413 带同一个码也塌成溢出，
    而不是落到 `PROVIDER_HTTP_STATUS` 让退出码变成 1。"""
    provider, seen = _provider(
        handler=lambda request: httpx.Response(
            413,
            json={"error": {"code": "context_length_exceeded", "message": "payload too large"}},
        )
    )

    outcome = await _generate(provider)

    assert len(seen) == 1
    assert isinstance(outcome, ProviderFailure)
    assert outcome.code == "PROVIDER_CONTEXT_OVERFLOW"
    assert outcome.attempts == []


async def test_a_400_whose_message_says_it_leaves_no_room_is_a_context_overflow() -> None:
    """design D3：错误对象没有 `code`、只有 `message` 时也要认得出溢出。

    正文取自真端点实际回过的那次（`tests/fixtures/real_endpoint/README.md` 写明来源 session）。
    """
    provider, seen = _provider(
        handler=lambda request: httpx.Response(
            400, text=(_FIXTURE_DIR / "context_overflow_400.json").read_text(encoding="utf-8")
        )
    )

    outcome = await _generate(provider)

    assert len(seen) == 1
    assert isinstance(outcome, ProviderFailure)
    assert outcome.code == "PROVIDER_CONTEXT_OVERFLOW"
    assert outcome.attempts == []


async def test_a_500_saying_context_length_exceeded_is_not_an_overflow() -> None:
    """2026-10-23 人裁决：塌成溢出只发生在 4xx（429 除外）——5xx 说的是服务端那一刻接不住。"""
    provider, seen = _provider(
        handler=lambda request: httpx.Response(
            500,
            json={"error": {"type": "server_error", "message": "context length exceeded upstream"}},
        )
    )

    outcome = await _generate(provider)

    assert len(seen) == 2, "500 可重试一次"
    assert isinstance(outcome, ProviderFailure)
    assert outcome.code == "PROVIDER_HTTP_STATUS"


async def test_a_429_saying_prompt_is_too_long_is_not_an_overflow() -> None:
    """429 走既有的重试：它的正文里恰好出现短语表里的话也不塌成溢出。"""
    provider, seen = _provider(
        handler=lambda request: httpx.Response(
            429,
            json={"error": {"type": "rate_limit_error", "message": "prompt is too long right now"}},
        )
    )

    outcome = await _generate(provider)

    assert len(seen) == 2, "429 可重试一次"
    assert isinstance(outcome, ProviderFailure)
    assert outcome.code == "PROVIDER_HTTP_STATUS"


async def test_the_provider_sentence_goes_into_the_failure_detail() -> None:
    """design D4：失败结果不只带状态码，还带提供方说的那句话。"""
    provider, _ = _provider(
        handler=lambda request: httpx.Response(
            400,
            json={
                "error": {
                    "type": "invalid_request_error",
                    "message": "prompt leaves no room to answer",
                }
            },
        )
    )

    outcome = await _generate(provider)

    assert isinstance(outcome, ProviderFailure)
    assert outcome.detail.startswith("HTTP 400：")
    assert "prompt leaves no room to answer" in outcome.detail


async def test_a_non_json_body_goes_into_the_detail_as_itself() -> None:
    """正文不是 JSON 时取正文本身；整条 `detail` 不超过 200 字符。"""
    html = "<html><body>Bad Gateway</body></html>" * 30
    provider, _ = _provider(handler=lambda request: httpx.Response(502, text=html))

    outcome = await _generate(provider)

    assert isinstance(outcome, ProviderFailure)
    assert outcome.code == "PROVIDER_HTTP_STATUS"
    assert outcome.detail.startswith("HTTP 502：<html>")
    assert len(outcome.detail) <= 200


async def test_an_empty_body_does_not_make_an_empty_sentence() -> None:
    """正文为空时只有状态码，不制造「HTTP 400：」这种空话。"""
    provider, _ = _provider(handler=lambda request: httpx.Response(400, text=""))

    outcome = await _generate(provider)

    assert isinstance(outcome, ProviderFailure)
    assert outcome.detail == "HTTP 400"


async def test_a_400_with_any_other_error_code_is_still_an_http_status_result() -> None:
    """`error.code` 不是那个值、`message` 也不含短语表里的任何一条：沿用既有分类。"""
    provider, _ = _provider(
        handler=lambda request: httpx.Response(
            400, json={"error": {"code": "invalid_request_error", "message": "bad tools"}}
        )
    )

    outcome = await _generate(provider)

    assert isinstance(outcome, ProviderFailure)
    assert outcome.code == "PROVIDER_HTTP_STATUS"


async def test_a_400_with_an_unreadable_body_is_still_an_http_status_result() -> None:
    """读不出 JSON 不是「超限」，也不是崩溃：分类要落在既有那个码上。"""
    provider, _ = _provider(handler=lambda request: httpx.Response(400, text="not json"))

    outcome = await _generate(provider)

    assert isinstance(outcome, ProviderFailure)
    assert outcome.code == "PROVIDER_HTTP_STATUS"


async def test_the_provider_still_accepts_no_key_and_sends_no_header() -> None:
    """端点对象进设置之后 provider 契约没动：没有密钥照样发请求，`generate` 签名不变。"""
    endpoint = ProviderEndpoint(
        base_url=_BASE_URL,
        model="test-model",
        api_key_env="MINIHNS_UNSET_TEST_KEY",
    )
    provider, seen = _provider(
        handler=lambda request: httpx.Response(200, json=_OK_BODY),
        api_key=os.environ.get(endpoint.api_key_env),
    )

    outcome = await _generate(provider)

    assert os.environ.get(endpoint.api_key_env) is None
    assert len(seen) == 1
    assert seen[0].headers.get("authorization") is None
    assert not isinstance(outcome, ProviderFailure)
    assert list(inspect.signature(provider.generate).parameters) == [
        "messages",
        "tools",
        "signal",
        "on_delta",
    ]
