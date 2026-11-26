"""模型层：单方法契约与 mock 适配器。"""

from mini_harness.provider.contract import (
    AssistantTurn,
    Block,
    Provider,
    ProviderFailure,
    ReasoningBlock,
    ReasoningSink,
    TextBlock,
    ToolCall,
    ToolCallBlock,
    ToolSpec,
    Usage,
)
from mini_harness.provider.mock import FixtureLoadFailure, FixtureProvider, load_fixture_provider

__all__ = [
    "AssistantTurn",
    "Block",
    "FixtureLoadFailure",
    "FixtureProvider",
    "Provider",
    "ProviderFailure",
    "ReasoningBlock",
    "ReasoningSink",
    "TextBlock",
    "ToolCall",
    "ToolCallBlock",
    "ToolSpec",
    "Usage",
    "load_fixture_provider",
]
