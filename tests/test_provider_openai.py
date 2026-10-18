"""seam ⑤：OpenAI 兼容适配器。HTTP 层由测试注入，判据不跑网络。"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from typing import Any

import httpx

from mini_harness.events.fold import Message
from mini_harness.provider.contract import AssistantTurn, ProviderFailure, ToolSpec
from mini_harness.provider.openai_compat import OpenAICompatProvider

_BASE_URL = "http://127.0.0.1:9/v1"

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
