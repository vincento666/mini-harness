"""seam ⑤：assistant content blocks 与旧投影。"""

from __future__ import annotations

import asyncio

from mini_harness.provider import (
    AssistantTurn,
    FixtureProvider,
    ReasoningBlock,
    TextBlock,
    ToolCallBlock,
)


async def test_mock_fixture_can_emit_reasoning_deltas() -> None:
    provider = FixtureProvider(
        [
            {
                "content": "答案",
                "finish_reason": "stop",
                "reasoning_deltas": ["先想", "再答"],
            }
        ]
    )
    reasoning: list[tuple[str, int, str]] = []

    async def sink(turn_id: str, index: int, text: str) -> None:
        reasoning.append((turn_id, index, text))

    turn = await provider.generate([], [], asyncio.Event(), on_reasoning=sink)

    assert isinstance(turn, AssistantTurn)
    assert [item[2] for item in reasoning] == ["先想", "再答"]


def test_assistant_turn_keeps_block_order() -> None:
    turn = AssistantTurn(
        finish_reason="stop",
        blocks=[
            ReasoningBlock(text="先看 note.md"),
            ToolCallBlock(id="c1", name="read", arguments={"file_path": "note.md"}),
            ReasoningBlock(text="读到了 alpha"),
            TextBlock(text="note.md 里是 alpha。"),
        ],
    )

    assert [block.type for block in turn.blocks] == [
        "reasoning",
        "tool-call",
        "reasoning",
        "text",
    ]
    assert turn.content == "note.md 里是 alpha。"
    assert turn.tool_calls[0].id == "c1"


def test_old_content_projection_becomes_one_text_block() -> None:
    turn = AssistantTurn(content="你好", finish_reason="stop")

    assert [block.type for block in turn.blocks] == ["text"]
    assert turn.content == "你好"


def test_usage_reasoning_tokens_default_to_zero() -> None:
    turn = AssistantTurn(content="好", finish_reason="stop")

    assert turn.usage.reasoning_tokens == 0
