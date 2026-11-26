"""可选的 reasoning 标签解析：只给选择标签协议的 adapter 用，核心不解析。

开标签确认后立即把后续内容作为 reasoning 发出；闭标签确认后回到正文。
EOF 仍未闭合、孤立闭标签、嵌套开标签都是 `TagReasoningError`，调用方应塌成
`PROVIDER_SCHEMA_INVALID`，且不写 `model/response`。
"""

from __future__ import annotations

OPEN_TAG = "<reasoning>"
CLOSE_TAG = "</reasoning>"


class TagReasoningError(ValueError):
    """标签协议不合法（半开、半闭、嵌套、EOF 未闭合）。"""


def _partial_suffix(text: str, tag: str) -> str:
    """返回 text 末尾可能是 tag 前缀的那一段（不含完整的 tag）。"""
    for size in range(min(len(tag) - 1, len(text)), 0, -1):
        if text.endswith(tag[:size]):
            return text[-size:]
    return ""


class TagReasoningStream:
    """逐 chunk 的标签状态机；`feed` 返回 `(kind, text)` 列表。"""

    def __init__(self) -> None:
        self._buffer = ""
        self._in_reasoning = False

    def feed(self, chunk: str) -> list[tuple[str, str]]:
        self._buffer += chunk
        emitted: list[tuple[str, str]] = []
        while self._buffer:
            if self._in_reasoning:
                close = self._buffer.find(CLOSE_TAG)
                nested = self._buffer.find(OPEN_TAG)
                if nested != -1 and (close == -1 or nested < close):
                    raise TagReasoningError("reasoning 标签内出现嵌套开标签")
                if close != -1:
                    if close:
                        emitted.append(("reasoning", self._buffer[:close]))
                    self._buffer = self._buffer[close + len(CLOSE_TAG) :]
                    self._in_reasoning = False
                    continue
                partial = _partial_suffix(self._buffer, CLOSE_TAG)
                if partial:
                    content = self._buffer[: -len(partial)]
                    if content:
                        emitted.append(("reasoning", content))
                    self._buffer = partial
                else:
                    emitted.append(("reasoning", self._buffer))
                    self._buffer = ""
                break
            open_at = self._buffer.find(OPEN_TAG)
            close_at = self._buffer.find(CLOSE_TAG)
            if close_at != -1 and (open_at == -1 or close_at < open_at):
                raise TagReasoningError("reasoning 闭标签没有配对的开标签")
            if open_at != -1:
                if open_at:
                    emitted.append(("text", self._buffer[:open_at]))
                self._buffer = self._buffer[open_at + len(OPEN_TAG) :]
                self._in_reasoning = True
                continue
            partial = _partial_suffix(self._buffer, OPEN_TAG)
            if partial:
                content = self._buffer[: -len(partial)]
                if content:
                    emitted.append(("text", content))
                self._buffer = partial
            else:
                emitted.append(("text", self._buffer))
                self._buffer = ""
            break
        return emitted

    def finish(self) -> list[tuple[str, str]]:
        """流结束；未闭合的 reasoning 是协议错误，绝不默认为正文。"""
        if self._in_reasoning:
            raise TagReasoningError("reasoning 开标签在流结束时仍未闭合")
        if self._buffer:
            text = self._buffer
            self._buffer = ""
            return [("text", text)]
        return []
