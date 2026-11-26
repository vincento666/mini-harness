"""seam ⑤：可选 reasoning 标签 adapter 的状态机。"""

from __future__ import annotations

import pytest

from mini_harness.provider.reasoning_tags import (
    TagReasoningError,
    TagReasoningStream,
)


def test_no_tags_is_all_text() -> None:
    stream = TagReasoningStream()

    assert stream.feed("你好") == [("text", "你好")]
    assert stream.finish() == []


def test_open_emits_reasoning_optimistically_and_close_returns_to_text() -> None:
    stream = TagReasoningStream()

    assert stream.feed("<reasoning>先想") == [("reasoning", "先想")]
    assert stream.feed("一下</reasoning>答") == [("reasoning", "一下"), ("text", "答")]
    assert stream.finish() == []


def test_tag_split_across_chunks_is_buffered() -> None:
    stream = TagReasoningStream()

    assert stream.feed("<rea") == []
    assert stream.feed("soning>想</rea") == [("reasoning", "想")]
    assert stream.feed("soning>答") == [("text", "答")]


def test_unclosed_reasoning_is_an_error() -> None:
    stream = TagReasoningStream()
    stream.feed("<reasoning>半")

    with pytest.raises(TagReasoningError):
        stream.finish()


def test_orphan_close_is_an_error() -> None:
    stream = TagReasoningStream()

    with pytest.raises(TagReasoningError):
        stream.feed("</reasoning>")


def test_nested_open_is_an_error() -> None:
    stream = TagReasoningStream()
    stream.feed("<reasoning>")

    with pytest.raises(TagReasoningError):
        stream.feed("<reasoning>")
