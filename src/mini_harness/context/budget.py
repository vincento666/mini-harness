"""窗口预算的三个纯函数：触发线、估算 token、预算读数。

规格锚点：`context-budget` 的「触发线由固定公式给出」「预算读数有两个来源」。
估算不是真 token 数（见 ADR-0016）：harness 只用它决定要不要压缩，终止决策由 provider 的报错兜底。
"""

from __future__ import annotations

import json
from collections.abc import Sequence

from mini_harness.events.fold import Message
from mini_harness.events.record import EventRecord

# 触发线公式里的 headroom：照 DSH `dsh-compaction-basic` 的 `headroomTokens ?? 65536`。
CONTEXT_HEADROOM_TOKENS = 65536

# 估算的换算：四个字符算一个 token，逐条向上取整再相加。
CHARS_PER_TOKEN = 4

# 触发线公式里的窗口比例：`W * 0.8`。
TRIGGER_RATIO_NUMERATOR = 4
TRIGGER_RATIO_DENOMINATOR = 5

# 摘要那次模型调用的标记值：它的 `usage` 不参与校准。
PURPOSE_COMPACTION = "compaction"


def trigger_line(window: int, reserve: int) -> int:
    """触发线 = `floor(min(W * 0.8, W - O - 65536))`，负值取 0。

    默认参数（128000 / 8192）下是 54272：`W - O - 65536` 这一支比 `W * 0.8` 小。
    整数运算，不用浮点，`floor` 由整除给出。
    """
    line = min(
        window * TRIGGER_RATIO_NUMERATOR // TRIGGER_RATIO_DENOMINATOR,
        window - reserve - CONTEXT_HEADROOM_TOKENS,
    )
    return max(line, 0)


def estimate_tokens(messages: Sequence[Message]) -> int:
    """逐条估算：`content` 加 `tool_calls` 的 JSON 文本长度，除以 4 向上取整，再相加。

    上下文里最贵的常是模型请求的 `write` 参数——只算 `content` 会把它算成 0。
    """
    total = 0
    for message in messages:
        chars = len(message.content)
        if message.tool_calls:
            chars += len(json.dumps(message.tool_calls, ensure_ascii=False))
        total += -(-chars // CHARS_PER_TOKEN)
    return total


def budget_reading(events: Sequence[EventRecord], messages: Sequence[Message]) -> int:
    """预算读数 = max(本次折叠上下文的估算, 前缀里回合级回复回报的 `input_tokens` 最大值)。

    `purpose` 为 `compaction` 的那次回复不参与校准：它量的是被遮蔽的那一大段，
    压缩之后还拿它当读数，下一回合立刻又越线，于是每一回合都压缩一次。
    """
    reported = 0
    for event in events:
        if event.type != "model/response" or event.payload.get("purpose") == PURPOSE_COMPACTION:
            continue
        usage = event.payload.get("usage")
        if not isinstance(usage, dict):
            continue
        input_tokens = usage.get("input_tokens")
        if isinstance(input_tokens, int) and input_tokens > reported:
            reported = input_tokens
    return max(estimate_tokens(messages), reported)
