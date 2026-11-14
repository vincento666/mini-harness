"""token 计量：把日志里的 provider 用量聚合成四桶（M14b）。

DSH 的 `dsh-token-meter` 求和四个不重叠 bucket；mini 的适配器目前只报
`input_tokens` / `output_tokens`，所以 `cache_*` 两桶在 provider 扩展前恒为 0。
`reasoning` 是 `output` 的细分，不再加一次。
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from mini_harness.events.record import EventRecord


@dataclass(frozen=True)
class Usage:
    input_uncached: int = 0
    cache_read: int = 0
    cache_write: int = 0
    output: int = 0

    def plus(self, other: Usage) -> Usage:
        return Usage(
            input_uncached=self.input_uncached + other.input_uncached,
            cache_read=self.cache_read + other.cache_read,
            cache_write=self.cache_write + other.cache_write,
            output=self.output + other.output,
        )

    def as_dict(self) -> dict[str, int]:
        return {
            "input_uncached": self.input_uncached,
            "cache_read": self.cache_read,
            "cache_write": self.cache_write,
            "output": self.output,
        }


@dataclass(frozen=True)
class TurnUsage:
    turn_id: str
    usage: Usage


def _int(value: object) -> int:
    return int(value) if isinstance(value, int) and value > 0 else 0


def usage_from_payload(payload: Mapping[str, object]) -> Usage | None:
    """从 `model/response` 的 payload 取用量；没有就是 None（不猜）。"""
    raw = payload.get("usage")
    if not isinstance(raw, dict):
        return None
    cached = _int(raw.get("cache_read_tokens") or raw.get("prompt_cache_hit_tokens"))
    total_in = _int(raw.get("input_tokens") or raw.get("prompt_tokens"))
    uncached = max(total_in - cached, 0) if cached else total_in
    return Usage(
        input_uncached=uncached,
        cache_read=cached,
        cache_write=_int(raw.get("cache_write_tokens")),
        output=_int(raw.get("output_tokens") or raw.get("completion_tokens")),
    )


def collect_usage(records: Sequence[EventRecord]) -> tuple[tuple[TurnUsage, ...], Usage]:
    """按回合聚合；同一回合的后一条响应替换前一条，总量是各回合之和。"""
    order: list[str] = []
    per_turn: dict[str, Usage] = {}
    for record in records:
        if record.type != "model/response":
            continue
        turn_id = record.payload.get("turn_id")
        if not isinstance(turn_id, str):
            continue
        usage = usage_from_payload(record.payload)
        if usage is None:
            continue
        if turn_id not in per_turn:
            order.append(turn_id)
        per_turn[turn_id] = usage
    turns = tuple(TurnUsage(turn_id, per_turn[turn_id]) for turn_id in order)
    total = Usage()
    for turn in turns:
        total = total.plus(turn.usage)
    return turns, total
