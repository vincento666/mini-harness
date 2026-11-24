"""seam ①④：`user/message` 的来源字段（M13 task 1.2）。"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from mini_harness.events import read_events
from mini_harness.goals import message_source_of
from mini_harness.loop import ENTRY_RUN, end_session, run_turn, start_session
from mini_harness.provider import FixtureProvider
from mini_harness.tools import ToolRegistry
from tool_harness import build_session_env


def _env(tmp_path: Path) -> Any:
    log, env = build_session_env(
        tmp_path,
        "s-source",
        FixtureProvider(entries=[{"content": "done", "finish_reason": "stop"}]),
        registry=ToolRegistry(),
    )
    return log, env


async def test_default_source_is_human(tmp_path: Path) -> None:
    log, env = _env(tmp_path)
    assert start_session(prompt="开始", entry=ENTRY_RUN, env=env) is None
    outcome = await run_turn(
        env=env, turn_id="s1", first_step_index=1, cancel=asyncio.Event(), user_message="开始"
    )
    assert end_session(env=env, stop_reason=outcome.stop_reason, steps=outcome.steps) is None

    messages = [r for r in read_events(log.path) if r.type == "user/message"]
    assert [m.payload["source"] for m in messages] == [{"kind": "user"}]


async def test_goal_source_is_recorded_verbatim(tmp_path: Path) -> None:
    log, env = _env(tmp_path)
    assert start_session(prompt="开始", entry=ENTRY_RUN, env=env) is None
    source = {"kind": "goal", "goal_id": "g1", "revision": 1, "round": 1}
    outcome = await run_turn(
        env=env,
        turn_id="s1",
        first_step_index=1,
        cancel=asyncio.Event(),
        user_message="<goal_round>",
        message_source=source,
    )
    assert end_session(env=env, stop_reason=outcome.stop_reason, steps=outcome.steps) is None

    records = read_events(log.path)
    messages = [r for r in records if r.type == "user/message"]
    assert messages[0].payload["source"] == source
    # 段首仍在驱动消息之前。
    types = [r.type for r in records]
    assert types.index("turn/start") < types.index("user/message")


def test_old_log_without_source_reads_as_human() -> None:
    assert message_source_of({"turn_id": "s1", "content": "老输入"}) == {"kind": "user"}


def test_unknown_kind_reads_as_human() -> None:
    assert message_source_of({"content": "x", "source": {"kind": "subagent"}}) == {"kind": "user"}
