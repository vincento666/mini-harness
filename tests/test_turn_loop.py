"""seam ①：显式回合主循环。"""

from __future__ import annotations

import asyncio
import os
import stat
from pathlib import Path

from mini_harness.events import EventLog, read_events
from mini_harness.loop import SessionSettings, run_session
from mini_harness.provider import AssistantTurn, FixtureProvider
from mini_harness.tools import ToolRegistry


def _settings(workspace: Path, max_turns: int = 8) -> SessionSettings:
    return SessionSettings(workspace=workspace, provider_name="mock", max_turns=max_turns)


async def test_single_turn_writes_the_expected_event_sequence(tmp_path: Path) -> None:
    log = EventLog.create(session_dir=tmp_path, session_id="s-loop")

    outcome = await run_session(
        prompt="任务",
        provider=FixtureProvider(entries=[{"content": "done", "finish_reason": "stop"}]),
        log=log,
        registry=ToolRegistry(),
        settings=_settings(tmp_path, max_turns=8),
        cancel=asyncio.Event(),
    )

    types = [record.type for record in read_events(log.path)]
    assert types == [
        "session/start",
        "turn/start",
        "context/assembled",
        "model/request",
        "model/response",
        "turn/end",
        "session/end",
    ]
    assert outcome.stop_reason == "MODEL_COMPLETED"
    assert outcome.turns == 1


def _tool_call_entries(count: int) -> list[dict[str, object]]:
    return [
        {
            "content": f"step {index}",
            "finish_reason": "tool_calls",
            "tool_calls": [{"id": f"c{index}", "name": "read", "arguments": {"file_path": "a.md"}}],
        }
        for index in range(1, count + 1)
    ]


async def test_each_turn_is_closed_before_the_next_one_starts(tmp_path: Path) -> None:
    log = EventLog.create(session_dir=tmp_path, session_id="s-multi")

    await run_session(
        prompt="任务",
        provider=FixtureProvider(entries=_tool_call_entries(3)),
        log=log,
        registry=ToolRegistry(),
        settings=_settings(tmp_path, max_turns=3),
        cancel=asyncio.Event(),
    )

    records = read_events(log.path)
    starts = [index for index, record in enumerate(records) if record.type == "turn/start"]
    ends = [index for index, record in enumerate(records) if record.type == "turn/end"]
    assert len(starts) == 3
    assert len(ends) == 3
    assert all(ends[index] < starts[index + 1] for index in range(2))
    turn_ids = [record.payload["turn_id"] for record in records if record.type == "turn/start"]
    assert len(set(turn_ids)) == 3


async def test_a_log_that_becomes_unwritable_ends_the_run_as_a_failure_result(
    tmp_path: Path,
) -> None:
    log = EventLog.create(session_dir=tmp_path, session_id="s-logfail")
    os.chmod(log.path, stat.S_IREAD)
    try:
        outcome = await run_session(
            prompt="任务",
            provider=FixtureProvider(entries=[{"content": "done", "finish_reason": "stop"}]),
            log=log,
            registry=ToolRegistry(),
            settings=_settings(tmp_path, max_turns=8),
            cancel=asyncio.Event(),
        )
    finally:
        os.chmod(log.path, stat.S_IREAD | stat.S_IWRITE)

    assert outcome.stop_reason == "LOG_WRITE_FAILED"
    assert outcome.failure_code == "LOG_WRITE_FAILED"
    assert log.path.read_text(encoding="utf-8") == ""


async def test_context_assembled_carries_the_turn_id_it_belongs_to(tmp_path: Path) -> None:
    log = EventLog.create(session_dir=tmp_path, session_id="s-turnid")

    await run_session(
        prompt="任务",
        provider=FixtureProvider(entries=_tool_call_entries(2)),
        log=log,
        registry=ToolRegistry(),
        settings=_settings(tmp_path, max_turns=2),
        cancel=asyncio.Event(),
    )

    assembled = [record for record in read_events(log.path) if record.type == "context/assembled"]
    assert len(assembled) == 2
    assert [record.payload["turn_id"] for record in assembled] == ["t1", "t2"]


async def test_empty_tool_calls_ends_the_loop_with_model_completed(tmp_path: Path) -> None:
    log = EventLog.create(session_dir=tmp_path, session_id="s-stop")

    outcome = await run_session(
        prompt="任务",
        provider=FixtureProvider(entries=[{"content": "done", "finish_reason": "stop"}]),
        log=log,
        registry=ToolRegistry(),
        settings=_settings(tmp_path, max_turns=8),
        cancel=asyncio.Event(),
    )

    records = read_events(log.path)
    turn_end = [record for record in records if record.type == "turn/end"]
    assert len(turn_end) == 1
    assert turn_end[0].payload["stop_reason"] == "MODEL_COMPLETED"
    assert outcome.stop_reason == "MODEL_COMPLETED"


async def test_reaching_max_turns_stops_with_max_turns_and_no_failure(tmp_path: Path) -> None:
    log = EventLog.create(session_dir=tmp_path, session_id="s-max")

    outcome = await run_session(
        prompt="任务",
        provider=FixtureProvider(entries=_tool_call_entries(5)),
        log=log,
        registry=ToolRegistry(),
        settings=_settings(tmp_path, max_turns=2),
        cancel=asyncio.Event(),
    )

    records = read_events(log.path)
    last_turn_end = [record for record in records if record.type == "turn/end"][-1]
    assert last_turn_end.payload["stop_reason"] == "MAX_TURNS"
    assert outcome.stop_reason == "MAX_TURNS"
    assert outcome.failure_code is None
    assert outcome.turns == 2


async def test_turn_that_requests_tool_calls_closes_with_tool_calls(tmp_path: Path) -> None:
    log = EventLog.create(session_dir=tmp_path, session_id="s-toolcalls")

    outcome = await run_session(
        prompt="任务",
        provider=FixtureProvider(
            entries=[*_tool_call_entries(1), {"content": "done", "finish_reason": "stop"}]
        ),
        log=log,
        registry=ToolRegistry(),
        settings=_settings(tmp_path, max_turns=8),
        cancel=asyncio.Event(),
    )

    records = read_events(log.path)
    turn_ends = [record.payload["stop_reason"] for record in records if record.type == "turn/end"]
    assert turn_ends == ["TOOL_CALLS", "MODEL_COMPLETED"]
    assert outcome.stop_reason == "MODEL_COMPLETED"


class _CancelDuringGenerate:
    """模拟回合中途取消：`generate` 期间把取消信号置起。"""

    def __init__(self, cancel: asyncio.Event) -> None:
        self._cancel = cancel

    async def generate(
        self,
        messages: object,
        tools: object,
        signal: asyncio.Event,
    ) -> AssistantTurn:
        self._cancel.set()
        return AssistantTurn(content="部分回复", finish_reason="stop")


async def test_cancel_signal_ends_the_turn_with_aborted(tmp_path: Path) -> None:
    log = EventLog.create(session_dir=tmp_path, session_id="s-cancel")
    cancel = asyncio.Event()

    outcome = await run_session(
        prompt="任务",
        provider=_CancelDuringGenerate(cancel),
        log=log,
        registry=ToolRegistry(),
        settings=_settings(tmp_path, max_turns=8),
        cancel=cancel,
    )

    records = read_events(log.path)
    turn_end = [record for record in records if record.type == "turn/end"][-1]
    assert turn_end.payload["stop_reason"] == "ABORTED"
    assert records[-1].type == "session/end"
    assert records[-1].payload["stop_reason"] == "ABORTED"
    assert outcome.stop_reason == "ABORTED"


async def test_a_cancelled_turn_writes_an_error_abort_event(tmp_path: Path) -> None:
    log = EventLog.create(session_dir=tmp_path, session_id="s-abort")
    cancel = asyncio.Event()

    outcome = await run_session(
        prompt="任务",
        provider=_CancelDuringGenerate(cancel),
        log=log,
        registry=ToolRegistry(),
        settings=_settings(tmp_path, max_turns=8),
        cancel=cancel,
    )

    records = read_events(log.path)
    aborts = [record for record in records if record.type == "error/abort"]
    assert len(aborts) == 1
    assert aborts[0].payload["turn_id"] == "t1"
    assert aborts[0].payload["code"] == "ABORTED"
    assert [record.type for record in records][-3:] == ["error/abort", "turn/end", "session/end"]
    assert outcome.stop_reason == "ABORTED"


async def test_provider_failure_is_recorded_as_error_model_and_provider_error(
    tmp_path: Path,
) -> None:
    log = EventLog.create(session_dir=tmp_path, session_id="s-fail")

    outcome = await run_session(
        prompt="任务",
        provider=FixtureProvider(entries=[]),
        log=log,
        registry=ToolRegistry(),
        settings=_settings(tmp_path, max_turns=8),
        cancel=asyncio.Event(),
    )

    records = read_events(log.path)
    errors = [record for record in records if record.type == "error/model"]
    assert len(errors) == 1
    assert errors[0].payload["code"] == "PROVIDER_EXHAUSTED"
    assert [record.payload["stop_reason"] for record in records if record.type == "turn/end"] == [
        "PROVIDER_ERROR"
    ]
    assert outcome.stop_reason == "PROVIDER_ERROR"
    assert outcome.failure_code == "PROVIDER_EXHAUSTED"


class _SpyProvider:
    """记录循环对 Provider 的每一次调用。"""

    def __init__(self) -> None:
        self.calls: list[tuple[str, int]] = []
        self.signals: list[object] = []

    async def generate(self, *args: object, **kwargs: object) -> AssistantTurn:
        self.calls.append(("generate", len(args) + len(kwargs)))
        self.signals.append(args[2] if len(args) == 3 else None)
        return AssistantTurn(content="done", finish_reason="stop")


async def test_loop_only_calls_generate_with_three_positional_parameters(tmp_path: Path) -> None:
    log = EventLog.create(session_dir=tmp_path, session_id="s-spy")
    cancel = asyncio.Event()
    spy = _SpyProvider()

    await run_session(
        prompt="任务",
        provider=spy,
        log=log,
        registry=ToolRegistry(),
        settings=_settings(tmp_path, max_turns=8),
        cancel=cancel,
    )

    assert spy.calls == [("generate", 3)]
    assert spy.signals[0] is cancel
