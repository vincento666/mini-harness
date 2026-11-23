"""seam ②⑥：`get_todos` 读回——事实取 `todos` 投影，读一次不写事件（M14c 缺口补齐）。"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from mini_harness.config import build_registry
from mini_harness.events.projection import project
from mini_harness.events.reader import read_events
from mini_harness.loop import ENTRY_RUN, end_session, run_turn, start_session
from mini_harness.provider import FixtureProvider
from mini_harness.provider.contract import ToolCall
from mini_harness.tools.dispatch import dispatch_tool_call
from mini_harness.tools.fences import DispatchContext
from tool_harness import build_session_env

TABLE: list[dict[str, Any]] = [
    {"id": "t1", "text": "写判据", "status": "in_progress"},
    {"id": "t2", "text": "改实现", "status": "pending"},
]

_TODO_CALL = {
    "content": "",
    "finish_reason": "tool_calls",
    "tool_calls": [{"id": "c1", "name": "todo", "arguments": {"items": TABLE}}],
}
_READ_CALL = {
    "content": "",
    "finish_reason": "tool_calls",
    "tool_calls": [{"id": "c2", "name": "get_todos", "arguments": {}}],
}
_STOP = {"content": "完成", "finish_reason": "stop"}


def _result_of(records: list[Any], call_id: str) -> dict[str, Any]:
    return next(
        record.payload
        for record in records
        if record.type == "tool/result" and record.payload["tool_call_id"] == call_id
    )


async def test_read_back_returns_the_last_table_without_writing_an_event(tmp_path: Path) -> None:
    """一次 `todo` 之后读回：内容就是整表，日志里只有那一条 `todo/updated`。"""
    log, env = build_session_env(
        tmp_path,
        "s-read",
        FixtureProvider(entries=[_TODO_CALL, _READ_CALL, _STOP]),
        registry=build_registry(None),
    )
    assert start_session(prompt="两条待办", entry=ENTRY_RUN, env=env) is None
    outcome = await run_turn(env=env, turn_id="s1", first_step_index=1, cancel=asyncio.Event())
    assert end_session(env=env, stop_reason=outcome.stop_reason, turns=outcome.turns) is None

    records = read_events(log.path)
    assert isinstance(records, list)
    read = _result_of(records, "c2")

    assert read["outcome"] == "OK"
    assert "当前待办：1 待办，1 进行中，0 完成" in read["content"]
    assert "- [in_progress] t1 写判据" in read["content"]
    assert "- [pending] t2 改实现" in read["content"]
    # 读回不写表：整份日志只有提交那一次 `todo/updated`。
    assert [r.type for r in records].count("todo/updated") == 1
    # 与 `/todo`、投影接口同一个值。
    assert project(records, "todos")["value"] == TABLE


async def test_read_back_is_empty_after_a_new_segment_starts(tmp_path: Path) -> None:
    """投影的生命周期是段：新段的读回是空表，不把上一段的表当成本段的。"""
    log, env = build_session_env(
        tmp_path,
        "s-read-next-segment",
        FixtureProvider(entries=[_TODO_CALL, _STOP, _READ_CALL, _STOP]),
        registry=build_registry(None),
    )
    assert start_session(prompt="第一段提交表", entry=ENTRY_RUN, env=env) is None
    first = await run_turn(env=env, turn_id="s1", first_step_index=1, cancel=asyncio.Event())
    second = await run_turn(
        env=env, turn_id="s2", first_step_index=first.turns + 1, cancel=asyncio.Event()
    )
    assert end_session(env=env, stop_reason=second.stop_reason, turns=second.turns) is None

    records = read_events(log.path)
    assert isinstance(records, list)
    read = _result_of(records, "c2")

    assert read["outcome"] == "OK"
    assert "当前待办为空" in read["content"]
    # 上一段的表还在日志里，但投影在新段开头清空了——读回跟投影走，不跟最后一条事件走。
    assert [r.type for r in records].count("todo/updated") == 1


async def test_read_back_is_allowed_in_plan_mode(tmp_path: Path) -> None:
    """只读，不受计划模式拦截。"""

    async def never(call: Any, detail: Any) -> None:
        raise AssertionError("get_todos 不该触发审批")

    outcome = await dispatch_tool_call(
        ToolCall(id="c1", name="get_todos", arguments={}),
        build_registry(None),
        DispatchContext(
            workspace=tmp_path,
            sandbox="read-only",
            approval="ask",
            plan_active=True,
            todos=tuple(TABLE),
        ),
        never,
    )

    assert outcome.result.outcome == "OK"
    assert "- [in_progress] t1 写判据" in outcome.result.content


async def test_read_back_says_empty_without_a_table(tmp_path: Path) -> None:
    outcome = await dispatch_tool_call(
        ToolCall(id="c1", name="get_todos", arguments={}),
        build_registry(None),
        DispatchContext(workspace=tmp_path, sandbox="workspace-write", approval="auto"),
        None,  # 不需要审批门：只读工具不问人
    )

    assert outcome.result.outcome == "OK"
    assert "当前待办为空" in outcome.result.content
    assert outcome.result.meta == {"todo_read": True, "todo_count": 0}
