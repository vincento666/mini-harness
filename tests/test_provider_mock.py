"""seam ⑤：Provider 契约与 mock Provider。"""

from __future__ import annotations

import asyncio
import inspect

from mini_harness.provider import (
    AssistantTurn,
    FixtureProvider,
    ProviderFailure,
    load_fixture_provider,
)
from paths import HELLO_SCENARIO


async def test_mock_provider_exposes_only_generate_with_optional_delta_sink() -> None:
    provider = load_fixture_provider(HELLO_SCENARIO)

    methods = [
        name
        for name in dir(provider)
        if not name.startswith("_") and callable(getattr(provider, name))
    ]
    assert methods == ["generate"]
    assert list(inspect.signature(provider.generate).parameters) == [
        "messages",
        "tools",
        "signal",
        "on_delta",
    ]


async def test_generate_without_a_sink_is_unchanged() -> None:
    provider = FixtureProvider(entries=[{"content": "ok", "finish_reason": "stop"}])

    turn = await provider.generate([], [], asyncio.Event(), on_delta=None)

    assert isinstance(turn, AssistantTurn)
    assert turn.content == "ok"


async def test_mock_emits_fixture_deltas() -> None:
    seen: list[str] = []

    async def sink(text: str) -> None:
        seen.append(text)

    provider = FixtureProvider(
        entries=[
            {
                "content": "你好",
                "deltas": ["你", "好"],
                "finish_reason": "stop",
            }
        ]
    )

    turn = await provider.generate([], [], asyncio.Event(), on_delta=sink)

    assert isinstance(turn, AssistantTurn)
    assert seen == ["你", "好"]
    assert turn.content == "你好"


async def test_a_fixture_without_deltas_emits_nothing() -> None:
    seen: list[str] = []

    async def sink(text: str) -> None:
        seen.append(text)

    provider = FixtureProvider(entries=[{"content": "旧 fixture", "finish_reason": "stop"}])

    turn = await provider.generate([], [], asyncio.Event(), on_delta=sink)

    assert isinstance(turn, AssistantTurn)
    assert turn.content == "旧 fixture"
    assert seen == []


async def test_a_non_string_delta_is_a_schema_failure() -> None:
    async def sink(text: str) -> None:
        raise AssertionError("不会走到这里")

    provider = FixtureProvider(
        entries=[{"content": "x", "deltas": ["ok", 3], "finish_reason": "stop"}]
    )

    outcome = await provider.generate([], [], asyncio.Event(), on_delta=sink)

    assert isinstance(outcome, ProviderFailure)
    assert outcome.code == "PROVIDER_SCHEMA_INVALID"


async def test_generate_returns_an_assistant_turn() -> None:
    provider = load_fixture_provider(HELLO_SCENARIO)

    turn = await provider.generate([], [], asyncio.Event())

    assert isinstance(turn, AssistantTurn)
    assert turn.content == "hello from fixture"
    assert turn.finish_reason == "stop"
    assert turn.tool_calls == []


async def test_generate_replays_the_fixture_entries_in_order() -> None:
    provider = FixtureProvider(
        entries=[
            {
                "content": "first",
                "finish_reason": "tool_calls",
                "tool_calls": [{"id": "c1", "name": "read"}],
            },
            {"content": "second", "finish_reason": "stop"},
            {"content": "third", "finish_reason": "stop"},
        ]
    )

    contents = [(await provider.generate([], [], asyncio.Event())).content for _ in range(3)]

    assert contents == ["first", "second", "third"]


async def test_exhausted_fixture_is_a_provider_exhausted_failure() -> None:
    provider = FixtureProvider(entries=[{"content": "only", "finish_reason": "stop"}])
    await provider.generate([], [], asyncio.Event())

    outcome = await provider.generate([], [], asyncio.Event())

    assert isinstance(outcome, ProviderFailure)
    assert outcome.code == "PROVIDER_EXHAUSTED"


async def test_fixture_entry_missing_finish_reason_is_a_schema_failure() -> None:
    provider = FixtureProvider(entries=[{"content": "no finish reason"}])

    outcome = await provider.generate([], [], asyncio.Event())

    assert isinstance(outcome, ProviderFailure)
    assert outcome.code == "PROVIDER_SCHEMA_INVALID"
