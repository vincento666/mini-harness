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
class Pricing:
    """每百万 token 的四类单价；缺的字段按 0 算，整表缺省时调用方给 None。"""

    input_uncached: float = 0.0
    cache_read: float = 0.0
    cache_write: float = 0.0
    output: float = 0.0

    def cost(self, usage: Usage) -> float:
        return (
            usage.input_uncached * self.input_uncached
            + usage.cache_read * self.cache_read
            + usage.cache_write * self.cache_write
            + usage.output * self.output
        ) / 1_000_000


@dataclass(frozen=True)
class TurnUsage:
    step_id: str
    usage: Usage


def _int(value: object) -> int:
    return int(value) if isinstance(value, int) and value > 0 else 0


def usage_from_payload(payload: Mapping[str, object]) -> Usage | None:
    """从 `model/response` 的 payload 取用量；没有就是 None（不猜）。"""
    raw = payload.get("usage")
    if not isinstance(raw, dict):
        return None
    cached = _int(raw.get("cache_read_tokens") or raw.get("prompt_cache_hit_tokens"))
    if isinstance(raw.get("input_tokens"), int):
        # 适配器给的 input_tokens 已经是未缓存部分，不再减。
        uncached = _int(raw.get("input_tokens"))
    else:
        uncached = max(_int(raw.get("prompt_tokens")) - cached, 0)
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
        step_id = record.payload.get("step_id")
        if not isinstance(step_id, str):
            continue
        usage = usage_from_payload(record.payload)
        if usage is None:
            continue
        if step_id not in per_turn:
            order.append(step_id)
        per_turn[step_id] = usage
    turns = tuple(TurnUsage(step_id, per_turn[step_id]) for step_id in order)
    total = Usage()
    for turn in turns:
        total = total.plus(turn.usage)
    return turns, total


def _price(value: object) -> float:
    return float(value) if isinstance(value, (int, float)) and value >= 0 else 0.0


def pricing_from(config: Mapping[str, object], model: str) -> Pricing | None:
    """从配置里取 `[pricing.<model>]`；没有这张表就返回 None（不猜价）。"""
    table = config.get("pricing")
    if not isinstance(table, dict):
        return None
    entry = table.get(model)
    if not isinstance(entry, dict):
        return None
    return Pricing(
        input_uncached=_price(entry.get("input")),
        cache_read=_price(entry.get("cache_read")),
        cache_write=_price(entry.get("cache_write")),
        output=_price(entry.get("output")),
    )
