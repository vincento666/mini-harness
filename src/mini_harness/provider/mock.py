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
    DeltaSink,
    ProviderFailure,
    ToolSpec,
)


def _deltas_of(entry: dict[str, Any]) -> list[str] | None:
    """fixture 条目的可选 `deltas`：缺席是空列表；形状不对是 `None`（调用方塌成 schema 失败）。"""
    raw = entry.get("deltas", [])
    if not isinstance(raw, list) or not all(isinstance(item, str) for item in raw):
        return None
    return list(raw)


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
        on_delta: DeltaSink | None = None,
    ) -> AssistantTurn | ProviderFailure:
        if self._index >= len(self._entries):
            return ProviderFailure(
                "PROVIDER_EXHAUSTED",
                f"fixture 只有 {len(self._entries)} 条条目，"
                f"第 {self._index + 1} 次调用没有回复可用",
            )
        raw = self._entries[self._index]
        self._index += 1
        deltas = _deltas_of(raw)
        if deltas is None:
            return ProviderFailure("PROVIDER_SCHEMA_INVALID", "fixture 的 deltas 必须是字符串数组")
        try:
            turn = AssistantTurn.model_validate(raw)
        except ValidationError as exc:
            return ProviderFailure("PROVIDER_SCHEMA_INVALID", str(exc))
        if on_delta is not None:
            for text in deltas:
                await on_delta(text)
        # 重试事实只能由真实适配器带回：fixture 是外部输入，它写 `attempts`
        # 不得凭空造出 `model/retry`（event-log delta：没有 429 与 5xx 的 run 不得有该记录）。
        return turn.model_copy(update={"attempts": []})


def load_fixture_provider(path: Path) -> FixtureProvider | FixtureLoadFailure:
    """读 fixture 文件：必须是 JSON 数组，且每条都符合 `AssistantTurn` 形状。"""
    try:
        parsed = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        return FixtureLoadFailure(path, f"{path}: {exc}")
    if not isinstance(parsed, list) or not all(isinstance(entry, dict) for entry in parsed):
        return FixtureLoadFailure(path, f"{path}: fixture 必须是 JSON 对象数组")
    entries = [dict(entry) for entry in parsed]
    for index, entry in enumerate(entries):
        try:
            AssistantTurn.model_validate(entry)
        except ValidationError as exc:
            return FixtureLoadFailure(
                path, f"{path}: 第 {index + 1} 条不符合 AssistantTurn 形状：{exc}"
            )
        if _deltas_of(entry) is None:
            return FixtureLoadFailure(path, f"{path}: 第 {index + 1} 条的 deltas 必须是字符串数组")
    return FixtureProvider(entries)
