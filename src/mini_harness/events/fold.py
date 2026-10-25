"""从事件日志折叠出「当前算数的上下文」：纯函数，不写日志。"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, Field

from mini_harness.events.record import EventRecord

SYSTEM_PROMPT = (
    "你是 mini-harness 的 agent。在回合里先装配上下文，再调用工具或回答；"
    "工具失败也是结果，不是异常。"
)

# 读方闭合的结果词：只出现在折叠出来的消息里，不在日志里。
# 名字与值一致，且与 `tools.registry.ToolOutcome` 里那个词是同一个字符串——
# 这里不 import 它，因为 `events` 不依赖 `tools`（依赖方向是工具读事件）。
TOOL_OUTCOME_UNKNOWN = "TOOL_OUTCOME_UNKNOWN"

# 摘要那次模型调用的标记值：它的回复不产出 assistant 消息，它的 `usage` 不参与预算校准。
PURPOSE_COMPACTION = "compaction"

# 不进遮蔽范围、也不进按 seq 区间折出的对话的两类事件（规格）。
PROTECTED_EVENT_TYPES: frozenset[str] = frozenset({"session/start", "compaction/summary"})

# 运行环境块（ADR-0029）：事实、本平台的命令建议、一句关于解码的说明。
# 建议只由记下来的 `shell` 推出，不看折叠那一刻所在机器的平台——否则同一份日志在两台机器上重放
# 会产出不同的头部，M5 的逐点重放判据就守不住了。
# 建议先给原生工具、再给这个平台的 shell 命令：2026-10-25 的 UAT 里，
# 模型先按描述用了 glob、又按这句用了 dir，然后自己把这一步撤回。
# 同一件事不能有两处说法（ADR-0030）。
_NATIVE_ADVICE = "列文件用 glob、搜内容用 grep、读文件用 read。"
_WINDOWS_SHELL_ADVICE = "真要跑 shell 命令时，用 dir / findstr / Get-Content。"
_POSIX_SHELL_ADVICE = "真要跑 shell 命令时，用 ls -R / tail。"
_DECODE_NOTE = "命令输出按 UTF-8 解码，不是合法 UTF-8 的字节会显示为替换字符。"


def _environment_block(os_name: str, shell: str) -> str:
    shell_advice = _WINDOWS_SHELL_ADVICE if "cmd.exe" in shell else _POSIX_SHELL_ADVICE
    head = f"运行环境：os={os_name}，bash 经 {shell} 执行。"
    return f"{head}{_NATIVE_ADVICE}{shell_advice}{_DECODE_NOTE}"


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
    platform: Mapping[str, str] | None = None,
) -> list[Message]:
    """受保护头部：内置常量在前，只能追加不能替换。"""
    parts = [SYSTEM_PROMPT]
    if tool_names:
        parts.append("可用工具：\n" + "\n".join(tool_names))
    if platform is not None:
        parts.append(
            _environment_block(str(platform.get("os", "")), str(platform.get("shell", "")))
        )
    if append_system_prompt:
        parts.append(append_system_prompt)
    return [Message(role="system", content="\n\n".join(parts))]


def _start_facts(
    events: Sequence[EventRecord],
) -> tuple[list[str], str, dict[str, str] | None]:
    """头部里的工具块、追加段与平台事实取自日志里的 `session/start`，不取自进程内注册表。

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
        raw_platform = event.payload.get("platform")
        platform = (
            {str(key): str(value) for key, value in raw_platform.items()}
            if isinstance(raw_platform, Mapping)
            else None
        )
        return names, appended if isinstance(appended, str) else "", platform
    return [], "", None


def _body_message(event: EventRecord) -> Message | None:
    if event.type == "session/start":
        prompt = event.payload.get("prompt")
        if isinstance(prompt, str) and prompt:
            return Message(role="user", content=prompt)
        return None
    if event.type == "user/message":
        # REPL 的一条输入：`entry` 为 `chat` 的会话里，人话只住在 `user/message` 里。
        return Message(role="user", content=str(event.payload.get("content", "")))
    if event.type == "model/response":
        if event.payload.get("purpose") == PURPOSE_COMPACTION:
            # 摘要那次调用的记账，不是对话：它的内容已经作为 `system` 摘要在表层里了。
            return None
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


def _closer(tool_call_id: str) -> Message:
    """读方派生的闭合：不落盘、不新造事件类型、不自动重试（design D1）。"""
    return Message(role="tool", content=TOOL_OUTCOME_UNKNOWN, tool_call_id=tool_call_id)


def _call_id_of(event: EventRecord) -> str | None:
    tool_call_id = event.payload.get("tool_call_id")
    return tool_call_id if isinstance(tool_call_id, str) else None


def shadowed_seqs(events: Sequence[EventRecord]) -> set[int]:
    """既有 `compaction/summary` 遮蔽了哪些 `seq`（闭区间的并集）。

    遮蔽是一条替换记录：日志不删，读方跳过。摘要记录自己与 `session/start` 不进遮蔽（规格）。
    """
    shadowed: set[int] = set()
    for event in events:
        if event.type != "compaction/summary":
            continue
        raw = event.payload.get("shadowed_range")
        if not isinstance(raw, dict):
            continue
        start, end = raw.get("start"), raw.get("end")
        if isinstance(start, int) and isinstance(end, int):
            shadowed.update(range(start, end + 1))
    return shadowed


def _summary_message(event: EventRecord) -> Message | None:
    """一条 `compaction/summary` 折成的那条 `system` 消息（不落盘，只在表层里）。"""
    summary = event.payload.get("summary")
    if not isinstance(summary, str) or not summary:
        return None
    return Message(role="system", content=summary)


def fold(events: Sequence[EventRecord]) -> AssembledContext:
    """折叠事件序列：不截断、不新造遮蔽、不自己摘要。

    既有的遮蔽由 `compaction/summary` 定义，落在范围内的记录不产出消息，也不进配对队列——压缩不制造
    `TOOL_OUTCOME_UNKNOWN`。每条摘要作为 `system` 消息进表层，位置在受保护头部与用户 prompt 之后。

    闭合排在它该在的位置：未配对的调用先闭合，再轮到它之后的那条消息。于是半截日志折叠出来的
    上下文仍然配平——assistant 的工具请求后面跟着工具结果，之后才是既有消息。
    """
    tool_names, append_system_prompt, platform = _start_facts(events)
    header = protected_header(
        append_system_prompt=append_system_prompt,
        tool_names=tool_names,
        platform=platform,
    )
    shadowed = shadowed_seqs(events)
    body: list[Message] = []
    summaries: list[Message] = []
    pending: list[str] = []
    for event in events:
        if event.type == "compaction/summary":
            summary = _summary_message(event)
            if summary is not None:
                summaries.append(summary)
            continue
        if event.seq in shadowed and event.type != "session/start":
            continue
        if event.type == "tool/call":
            call_id = _call_id_of(event)
            if call_id is not None:
                pending.append(call_id)
            continue
        message = _body_message(event)
        if message is None:
            continue
        if event.type == "tool/result":
            call_id = _call_id_of(event)
            if call_id is not None and call_id in pending:
                pending.remove(call_id)
        else:
            body.extend(_closer(call_id) for call_id in pending)
            pending.clear()
        body.append(message)
    body.extend(_closer(call_id) for call_id in pending)
    insert_at = 1 if body and body[0].role == "user" else 0
    body = [*body[:insert_at], *summaries, *body[insert_at:]]
    fingerprint = hashlib.sha256(
        "\n".join(message.content for message in header).encode("utf-8")
    ).hexdigest()
    return AssembledContext(messages=[*header, *body], header_fingerprint=fingerprint)


def fold_range(events: Sequence[EventRecord], *, start: int, end: int) -> list[Message]:
    """按 seq 闭区间折出对话体：受保护头部不进来，区间外的记录一条都不算。

    给「摘要只装本次要遮蔽的那一段」用（ADR-0023）。区间盖住 `session/start` 或既有
    `compaction/summary` 时它们不产出消息——它们不进范围（规格）。起点大于终点折出空对话。
    """
    window = [
        event
        for event in events
        if start <= event.seq <= end and event.type not in PROTECTED_EVENT_TYPES
    ]
    if not window:
        return []
    context = fold(window)
    # `fold` 的头部恒为一条 `system`；调用方自己带头部，这里只要对话体。
    return context.messages[len(protected_header()) :]


def assembled_payload(turn_id: str, context: AssembledContext) -> dict[str, Any]:
    """`context/assembled` 的 payload：所属回合的 `turn_id` 加折叠结果。"""
    return {"turn_id": turn_id, **context.model_dump(mode="json")}


@dataclass(frozen=True)
class AssemblyPoint:
    """一个装配点：那条 `context/assembled`、它之前的记录前缀、它所属的回合。"""

    record: EventRecord
    prefix: tuple[EventRecord, ...]
    turn_id: str


def assembly_points(events: Sequence[EventRecord]) -> list[AssemblyPoint]:
    """按写入顺序给出日志里的每个装配点。

    前缀止于该点之前——该点自己与它之后的事件都不算进来；`turn_id` 取自它之前最近的
    `turn/start`，没有就是空串。重放方据此重算，不必自己扫记录、按下标切前缀。
    """
    points: list[AssemblyPoint] = []
    turn_id = ""
    for index, event in enumerate(events):
        if event.type == "turn/start":
            turn_id = str(event.payload.get("turn_id", ""))
        elif event.type == "context/assembled":
            points.append(
                AssemblyPoint(record=event, prefix=tuple(events[:index]), turn_id=turn_id)
            )
    return points
