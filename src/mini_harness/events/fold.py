"""从事件日志折叠出「当前算数的上下文」：纯函数，不写日志。"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from typing import Any

from pydantic import BaseModel, Field

from mini_harness.events.record import EventRecord

SYSTEM_PROMPT = (
    "你是 mini-harness 的 agent。在回合里先装配上下文，再调用工具或回答；"
    "工具失败也是结果，不是异常。"
)


class Message(BaseModel):
    """进入模型的一条消息。"""

    role: str
    content: str
    tool_call_id: str | None = None
    tool_calls: list[dict[str, Any]] = Field(default_factory=list)


class AssembledContext(BaseModel):
    """一次模型调用要用的上下文。"""

    messages: list[Message]
    header_fingerprint: str


def protected_header(
    *,
    append_system_prompt: str = "",
    tool_descriptions: Sequence[str] = (),
) -> list[Message]:
    """受保护头部：内置常量在前，只能追加不能替换。"""
    parts = [SYSTEM_PROMPT]
    if tool_descriptions:
        parts.append("可用工具：\n" + "\n".join(tool_descriptions))
    if append_system_prompt:
        parts.append(append_system_prompt)
    return [Message(role="system", content="\n\n".join(parts))]


def _body_message(event: EventRecord) -> Message | None:
    if event.type == "model/response":
        return Message(
            role="assistant",
            content=str(event.payload.get("content", "")),
            tool_calls=list(event.payload.get("tool_calls", [])),
        )
    if event.type == "tool/result":
        content = event.payload.get("content") or str(event.payload.get("outcome", ""))
        return Message(
            role="tool",
            content=str(content),
            tool_call_id=event.payload.get("tool_call_id"),
        )
    return None


def fold(
    events: Sequence[EventRecord],
    *,
    append_system_prompt: str = "",
    tool_descriptions: Sequence[str] = (),
) -> AssembledContext:
    """折叠事件序列。M1 不截断、不遮蔽、不摘要。"""
    header = protected_header(
        append_system_prompt=append_system_prompt,
        tool_descriptions=tool_descriptions,
    )
    body = [message for event in events if (message := _body_message(event)) is not None]
    fingerprint = hashlib.sha256(
        "\n".join(message.content for message in header).encode("utf-8")
    ).hexdigest()
    return AssembledContext(messages=[*header, *body], header_fingerprint=fingerprint)
