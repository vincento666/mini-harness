"""窗口预算的纯函数：触发线、压力预算、估算 token、预算读数、遮蔽范围。

规格锚点：`context-budget` 的「触发线由固定公式给出」「溢出判据是压力预算，触发线只决定要不要
压缩」「预算读数有两个来源」「遮蔽范围保留尾部且不拆散配对」。
估算不是真 token 数（见 ADR-0016）：harness 只用它决定要不要压缩，终止决策由 provider 的报错兜底。
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from decimal import ROUND_FLOOR, Decimal

from mini_harness.events.fold import PURPOSE_COMPACTION, Message, shadowed_seqs
from mini_harness.events.record import EventRecord

# 触发线公式里的 headroom：照 DSH `dsh-compaction-basic` 的 `headroomTokens ?? 65536`。
CONTEXT_HEADROOM_TOKENS = 65536

# 估算的换算：四个字符算一个 token，逐条向上取整再相加。
CHARS_PER_TOKEN = 4

# 触发线公式里的窗口比例：`W * 0.8`。
TRIGGER_RATIO_NUMERATOR = 4
TRIGGER_RATIO_DENOMINATOR = 5

# 遮蔽范围不覆盖的记录类型：头部与用户 prompt 来自 `session/start`，摘要链是压缩后仅存的长程记忆。
PROTECTED_EVENT_TYPES: frozenset[str] = frozenset({"session/start", "compaction/summary"})

# 折叠会产出消息的记录类型：遮蔽范围里一条都没有时，这次压缩就没有意义。
MESSAGE_PRODUCING_EVENT_TYPES: frozenset[str] = frozenset(
    {"session/start", "model/response", "tool/result"}
)

# 一组工具往返的成员。
TOOL_ROUND_EVENT_TYPES: frozenset[str] = frozenset({"tool/call", "tool/result"})

# 保留尾部的比例：照 DSH 的 `DEFAULT_RETAIN_RATIO = .16`，整数运算给出 floor。
RETAIN_RATIO_NUMERATOR = 16
RETAIN_RATIO_DENOMINATOR = 100

# 这四个默认值的唯一来源：settings / layering 从这里取，budget 的默认参数也用它。
DEFAULT_COMPACTION_THRESHOLD_RATIO = TRIGGER_RATIO_NUMERATOR / TRIGGER_RATIO_DENOMINATOR
DEFAULT_COMPACTION_HEADROOM_TOKENS = CONTEXT_HEADROOM_TOKENS
DEFAULT_COMPACTION_RETAIN_RATIO = RETAIN_RATIO_NUMERATOR / RETAIN_RATIO_DENOMINATOR
DEFAULT_COMPACTION_RETAIN_TOKENS = 0


def _floor_ratio(window: int, ratio: float) -> int:
    """按十进制字面值取 `floor(W * ratio)`，避免 0.7 的二进制 double 少 1。

    `Decimal(str(ratio))` 把配置/默认值的十进制写法当精确值；窗口是整数，乘积可精确算。
    """
    return int((Decimal(window) * Decimal(str(ratio))).to_integral_value(rounding=ROUND_FLOOR))


def trigger_line(
    window: int,
    reserve: int,
    *,
    threshold_ratio: float = DEFAULT_COMPACTION_THRESHOLD_RATIO,
    headroom_tokens: int = DEFAULT_COMPACTION_HEADROOM_TOKENS,
) -> int:
    """触发线 = `floor(min(W * threshold_ratio, W - O - headroom_tokens))`，负值取 0。

    默认参数（128000 / 8192 / 0.8 / 65536）下是 54272：`W - O - 65536` 这一支更小。
    浮点只用在比例乘法上；`int()` 向零取整，窗口与参数为正时就是 floor。
    """
    line = min(
        _floor_ratio(window, threshold_ratio),
        pressure_budget(window, reserve) - headroom_tokens,
    )
    return max(line, 0)


def pressure_budget(window: int, reserve: int) -> int:
    """压力预算 = `W - O`：上下文装不装得下问的是它。

    触发线只决定「这次装配要不要尝试压缩」，MUST NOT 被用作溢出判据：小窗口下触发线可以
    比保留预算还小，那一段读数既压不动也装得下，拿它判溢出就是在真墙之前自己撞墙。
    """
    return window - reserve


def _tokens(chars: int) -> int:
    """字符数换算成估算 token：除以 4 向上取整。"""
    return -(-chars // CHARS_PER_TOKEN)


def _tool_calls_chars(tool_calls: object) -> int:
    if not tool_calls:
        return 0
    return len(json.dumps(tool_calls, ensure_ascii=False))


def estimate_tokens(messages: Sequence[Message]) -> int:
    """逐条估算：`content` 加 `tool_calls` 的 JSON 文本长度，除以 4 向上取整，再相加。

    上下文里最贵的常是模型请求的 `write` 参数——只算 `content` 会把它算成 0。
    """
    return sum(
        _tokens(len(message.content) + _tool_calls_chars(message.tool_calls))
        for message in messages
    )


def budget_reading(events: Sequence[EventRecord], messages: Sequence[Message]) -> int:
    """预算读数 = max(本次折叠上下文的估算, 前缀里回合级回复回报的 `input_tokens` 最大值)。

    两条排除是同一条判据：校准量的是**当前表层**。`purpose` 为 `compaction` 的那次回复量的是被遮蔽的
    那一大段；落在遮蔽范围里的回复描述的那份上下文已经不存在了。留着它们，压缩永远救不回来——
    每次装配都越线，每次装配都压缩一次。
    """
    shadowed = shadowed_seqs(events)
    reported = 0
    for event in events:
        if event.type != "model/response" or event.seq in shadowed:
            continue
        if event.payload.get("purpose") == PURPOSE_COMPACTION:
            continue
        usage = event.payload.get("usage")
        if not isinstance(usage, dict):
            continue
        input_tokens = usage.get("input_tokens")
        if isinstance(input_tokens, int) and input_tokens > reported:
            reported = input_tokens
    return max(estimate_tokens(messages), reported)


def retain_line(
    window: int,
    *,
    retain_ratio: float = DEFAULT_COMPACTION_RETAIN_RATIO,
    retain_tokens: int = DEFAULT_COMPACTION_RETAIN_TOKENS,
) -> int:
    """保留尾部预算：`retain_tokens > 0` 时用它，否则 `floor(W * retain_ratio)`。"""
    if retain_tokens > 0:
        return retain_tokens
    return _floor_ratio(window, retain_ratio)


def _record_chars(event: EventRecord) -> int:
    """一条记录往上下文里贡献多少字符；不产出消息的记录是 0。"""
    if event.type == "model/response":
        if event.payload.get("purpose") == PURPOSE_COMPACTION:
            return 0
        return len(str(event.payload.get("content", ""))) + _tool_calls_chars(
            event.payload.get("tool_calls")
        )
    if event.type == "tool/result":
        content = event.payload.get("content") or str(event.payload.get("outcome", ""))
        return len(str(content))
    if event.type == "session/start":
        return len(str(event.payload.get("prompt", "")))
    return 0


def _produces_message(event: EventRecord) -> bool:
    """这条记录在折叠结果里是否产出消息（`tool/call` 与 `turn/*` 不产出）。"""
    if event.type == "model/response" and event.payload.get("purpose") == PURPOSE_COMPACTION:
        return False
    return event.type in MESSAGE_PRODUCING_EVENT_TYPES


def _call_ids(tool_calls: object) -> set[str]:
    if not isinstance(tool_calls, list):
        return set()
    return {
        call["id"]
        for call in tool_calls
        if isinstance(call, dict) and isinstance(call.get("id"), str)
    }


def _round_owner(events: Sequence[EventRecord]) -> dict[str, int]:
    """每个 `tool_call_id` 属于哪条 assistant 请求（那条记录的 `seq`）。"""
    owner: dict[str, int] = {}
    for event in events:
        if event.type != "model/response":
            continue
        for call_id in _call_ids(event.payload.get("tool_calls")):
            owner[call_id] = event.seq
    return owner


def _round_end(events: Sequence[EventRecord], owner: dict[str, int], seq: int) -> int | None:
    """`seq` 这条记录是一组工具往返的成员时，返回这组最后一条记录的 seq 加 1。

    切点落在组内时整组一起遮蔽：把一条超预算的 assistant 请求拉进尾部等于这次压缩什么都没做。
    """
    by_seq = {event.seq: event for event in events}
    event = by_seq.get(seq)
    if event is None or event.type not in TOOL_ROUND_EVENT_TYPES:
        return None
    call_id = event.payload.get("tool_call_id")
    if not isinstance(call_id, str):
        return None
    assistant_seq = owner.get(call_id)
    if assistant_seq is None or assistant_seq >= seq:
        return None
    assistant = by_seq.get(assistant_seq)
    if assistant is None:
        return None
    ids = _call_ids(assistant.payload.get("tool_calls")) or {call_id}
    members = {assistant_seq}
    for other in events:
        if other.type in TOOL_ROUND_EVENT_TYPES and other.payload.get("tool_call_id") in ids:
            members.add(other.seq)
    return max(members) + 1


def shadowed_range(
    events: Sequence[EventRecord],
    window: int,
    *,
    retain_ratio: float = DEFAULT_COMPACTION_RETAIN_RATIO,
    retain_tokens: int = DEFAULT_COMPACTION_RETAIN_TOKENS,
) -> dict[str, int] | None:
    """这次压缩遮蔽哪一段：`{start, end}` 是 seq 闭区间，`None` 表示没有可遮蔽的内容。

    从对话体末尾往前累计估算 token 选出保留尾部（默认 `floor(W * 0.16)`；`retain_tokens > 0`
    时用绝对值），遮蔽它之前那段。`session/start` 与既有的 `compaction/summary` 不进范围；
    切点落在一组工具往返里时整组一起遮蔽。
    """
    retain = retain_line(window, retain_ratio=retain_ratio, retain_tokens=retain_tokens)
    protected_after = max(
        (event.seq for event in events if event.type in PROTECTED_EVENT_TYPES),
        default=-1,
    )
    candidates = [event for event in events if event.seq > protected_after]
    if not candidates:
        return None

    # 最后一条记录总是留着，哪怕它本身就超预算。
    keep_from = candidates[-1].seq
    total = _tokens(_record_chars(candidates[-1]))
    for event in reversed(candidates[:-1]):
        cost = _tokens(_record_chars(event))
        if total + cost > retain:
            break
        total += cost
        keep_from = event.seq

    owner = _round_owner(events)
    while True:
        moved = _round_end(events, owner, keep_from)
        if moved is None:
            break
        keep_from = moved
        if keep_from > candidates[-1].seq:
            break

    shadowed = [event for event in candidates if event.seq < keep_from]
    if keep_from > candidates[-1].seq or not shadowed:
        return None
    if not any(_produces_message(event) for event in shadowed):
        return None
    return {"start": shadowed[0].seq, "end": shadowed[-1].seq}
