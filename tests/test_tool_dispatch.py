"""seam ②：工具派发与空注册表。"""

from __future__ import annotations

from pathlib import Path

from mini_harness.events import read_events
from mini_harness.tools import ToolRegistry
from tool_harness import run_fixture_session

_TOOL_ENTRY = {
    "content": "需要读文件",
    "finish_reason": "tool_calls",
    "tool_calls": [{"id": "c1", "name": "read", "arguments": {"file_path": "a.md"}}],
}


async def test_unregistered_tool_call_is_a_paired_unknown_tool_result(tmp_path: Path) -> None:
    log, _ = await run_fixture_session(
        tmp_path,
        "s-tool",
        [_TOOL_ENTRY, {"content": "算了", "finish_reason": "stop"}],
        registry=ToolRegistry(),
        max_turns=8,
    )

    records = read_events(log.path)
    calls = [record for record in records if record.type == "tool/call"]
    results = [record for record in records if record.type == "tool/result"]
    assert len(calls) == 1
    assert len(results) == 1
    assert calls[0].payload["tool_call_id"] == results[0].payload["tool_call_id"]
    assert calls[0].payload["name"] == "read"
    assert results[0].payload["outcome"] == "UNKNOWN_TOOL"
    turn_end = [record for record in records if record.type == "turn/end"]
    assert len(turn_end) == 2
    assert turn_end[0].payload["stop_reason"] == "TOOL_CALLS"


async def test_previous_tool_result_is_folded_into_the_next_context(tmp_path: Path) -> None:
    log, _ = await run_fixture_session(
        tmp_path,
        "s-fold-tool",
        [_TOOL_ENTRY, {"content": "算了", "finish_reason": "stop"}],
        registry=ToolRegistry(),
        max_turns=8,
    )

    records = read_events(log.path)
    assembled = [record for record in records if record.type == "context/assembled"]
    assert len(assembled) == 2
    second_context = assembled[1].payload["messages"]
    tool_messages = [message for message in second_context if message["role"] == "tool"]
    assert len(tool_messages) == 1
    assert tool_messages[0]["content"] == "未注册的工具：read"
    assert tool_messages[0]["tool_call_id"] == "c1"


async def test_session_start_records_the_run_settings(tmp_path: Path) -> None:
    log, _ = await run_fixture_session(
        tmp_path,
        "s-start",
        [{"content": "done", "finish_reason": "stop"}],
        registry=ToolRegistry(),
        max_turns=8,
    )

    records = read_events(log.path)
    payload = records[0].payload
    assert payload["provider"] == "mock"
    assert payload["max_turns"] == 8
    assert payload["append_system_prompt"] == ""
    assert payload["prompt"] == "任务"
    assert "schema_version" not in payload
    assert Path(payload["workspace"]).is_absolute()
    assert Path(payload["workspace"]) == Path(tmp_path).resolve()
