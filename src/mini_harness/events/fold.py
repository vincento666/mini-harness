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
    tool_names: Sequence[str] = (),
) -> list[Message]:
    """受保护头部：内置常量在前，只能追加不能替换。"""
    parts = [SYSTEM_PROMPT]
    if tool_names:
        parts.append("可用工具：\n" + "\n".join(tool_names))
    if append_system_prompt:
        parts.append(append_system_prompt)
    return [Message(role="system", content="\n\n".join(parts))]


def _start_facts(events: Sequence[EventRecord]) -> tuple[list[str], str]:
    """头部里的工具块与追加段取自日志里的 `session/start`，不取自进程内注册表。

    这样实时装配与回放折叠的是同一份事实：注册表在回放时根本不存在。
    """
    for event in events:
        if event.type != "session/start":
            continue
        raw_tools = event.payload.get("tools")
        names: list[str] = []
        if isinstance(raw_tools, list):
            names = [name for name in raw_tools if isinstance(name, str)]
        appended = event.payload.get("append_system_prompt")
        return names, appended if isinstance(appended, str) else ""
    return [], ""


def _body_message(event: EventRecord) -> Message | None:
    if event.type == "session/start":
        prompt = event.payload.get("prompt")
        if isinstance(prompt, str) and prompt:
            return Message(role="user", content=prompt)
        return None
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


def fold(events: Sequence[EventRecord]) -> AssembledContext:
    """折叠事件序列。M1 不截断、不遮蔽、不摘要。"""
    tool_names, append_system_prompt = _start_facts(events)
    header = protected_header(
        append_system_prompt=append_system_prompt,
        tool_names=tool_names,
    )
    body = [message for event in events if (message := _body_message(event)) is not None]
    fingerprint = hashlib.sha256(
        "\n".join(message.content for message in header).encode("utf-8")
    ).hexdigest()
    return AssembledContext(messages=[*header, *body], header_fingerprint=fingerprint)


def assembled_payload(turn_id: str, context: AssembledContext) -> dict[str, Any]:
    """`context/assembled` 的 payload：所属回合的 `turn_id` 加折叠结果。"""
    return {"turn_id": turn_id, **context.model_dump(mode="json")}
