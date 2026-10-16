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


async def test_mock_provider_exposes_only_generate_with_three_parameters() -> None:
    provider = load_fixture_provider(HELLO_SCENARIO)

    methods = [
        name
        for name in dir(provider)
        if not name.startswith("_") and callable(getattr(provider, name))
    ]
    assert methods == ["generate"]
    assert list(inspect.signature(provider.generate).parameters) == ["messages", "tools", "signal"]


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
            {"content": "first", "finish_reason": "tool_calls", "tool_calls": [{"id": "c1", "name": "read"}]},
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
