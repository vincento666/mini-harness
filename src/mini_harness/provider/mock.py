"""mock Provider：由 JSON fixture 序列驱动。"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from mini_harness.events.fold import Message
from mini_harness.provider.contract import (
    AssistantTurn,
    ProviderFailure,
    ToolSpec,
)


class FixtureLoadFailure:
    """fixture 文件本身不合法：CLI 层映射成退出码 2。"""

    def __init__(self, path: Path, detail: str, code: str = "FIXTURE_INVALID") -> None:
        self.path = path
        self.detail = detail
        self.code = code


class FixtureProvider:
    """第 i 次 `generate` 返回 fixture 的第 i 条条目。"""

    def __init__(self, entries: list[dict[str, Any]]) -> None:
        self._entries = entries
        self._index = 0

    async def generate(
        self,
        messages: Sequence[Message],
        tools: Sequence[ToolSpec],
        signal: asyncio.Event,
    ) -> AssistantTurn | ProviderFailure:
        if self._index >= len(self._entries):
            return ProviderFailure(
                "PROVIDER_EXHAUSTED",
                f"fixture 只有 {len(self._entries)} 条条目，第 {self._index + 1} 次调用没有回复可用",
            )
        raw = self._entries[self._index]
        self._index += 1
        try:
            return AssistantTurn.model_validate(raw)
        except ValidationError as exc:
            return ProviderFailure("PROVIDER_SCHEMA_INVALID", str(exc))


def load_fixture_provider(path: Path) -> FixtureProvider | FixtureLoadFailure:
    """读 fixture 文件：必须是 JSON 数组，每条是对象。"""
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return FixtureLoadFailure(path, f"{path}: {exc}")
    if not isinstance(parsed, list) or not all(isinstance(entry, dict) for entry in parsed):
        return FixtureLoadFailure(path, f"{path}: fixture 必须是 JSON 对象数组")
    return FixtureProvider([dict(entry) for entry in parsed])
