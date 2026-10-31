"""seam ①：显式回合主循环。"""

from __future__ import annotations

import asyncio
import os
import stat
from pathlib import Path

import httpx

from mini_harness.config import build_registry
from mini_harness.events import EventLog, EventRecord, read_events
from mini_harness.events.fold import fold
from mini_harness.loop import (
    ENTRY_RUN,
    ENTRY_SERVE,
    ProviderEndpoint,
    RunOutcome,
    SessionSettings,
    end_session,
    run_session,
    run_turn_segment,
    start_session,
)
from mini_harness.provider import AssistantTurn, FixtureProvider, Provider, ProviderFailure
from mini_harness.provider.openai_compat import OpenAICompatProvider
from mini_harness.tools import ToolArgs, ToolDefinition, ToolRegistry, ToolResult
from mini_harness.tools.fences import DispatchContext, path_key
from tool_harness import (
    DONE,
    build_session_env,
    call_ids,
    result_outcomes,
    run_session_fixture,
    tool_call,
    turn_entry,
)


async def test_single_turn_writes_the_expected_event_sequence(tmp_path: Path) -> None:
    log, outcome = await run_session_fixture(
        tmp_path,
        "s-loop",
        FixtureProvider(entries=[{"content": "done", "finish_reason": "stop"}]),
        registry=ToolRegistry(),
        max_turns=8,
    )

    types = [record.type for record in read_events(log.path)]
    assert types == [
        "session/start",
        "segment/start",
        "turn/start",
        "context/assembled",
        "model/request",
        "model/response",
        "turn/end",
        "segment/end",
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


async def test_two_segments_number_segments_and_turns_continuously(tmp_path: Path) -> None:
    """一条输入一个段：段用完上限会话照继续，编号在会话内连续（design D3）。"""
    log, env = build_session_env(
        tmp_path,
        "s-segments",
        FixtureProvider(
            entries=[
                *_tool_call_entries(4),
                {"content": "done", "finish_reason": "stop"},
            ],
        ),
        registry=ToolRegistry(),
        max_turns=3,
    )

    assert start_session(prompt="第一条输入", entry=ENTRY_RUN, env=env) is None
    first = await run_turn_segment(
        env=env, segment_id="s1", first_turn_index=1, cancel=asyncio.Event()
    )
    second = await run_turn_segment(
        env=env, segment_id="s2", first_turn_index=first.turns + 1, cancel=asyncio.Event()
    )
    assert end_session(env=env, stop_reason=second.stop_reason, turns=second.turns) is None

    records = read_events(log.path)
    assert first.stop_reason == "MAX_TURNS"
    assert second.stop_reason == "MODEL_COMPLETED"
    assert [record.type for record in records if record.type.startswith("segment/")] == [
        "segment/start",
        "segment/end",
        "segment/start",
        "segment/end",
    ]
    assert [r.payload for r in records if r.type == "segment/end"] == [
        {"segment_id": "s1", "stop_reason": "MAX_TURNS", "turns": 3},
        {"segment_id": "s2", "stop_reason": "MODEL_COMPLETED", "turns": 2},
    ]
    assert [r.payload["turn_id"] for r in records if r.type == "turn/start"] == [
        "t1",
        "t2",
        "t3",
        "t4",
        "t5",
    ]
    assert [record.type for record in records][-1:] == ["session/end"]


async def test_a_serve_entry_session_is_one_segment_closed_on_disk(tmp_path: Path) -> None:
    """内核不知道入口存在：`entry: "serve"` 的会话与 run 同形——恰一个段、`session/end` 在盘上。"""
    log, env = build_session_env(
        tmp_path,
        "s-serve-entry",
        FixtureProvider(entries=[DONE]),
        registry=ToolRegistry(),
    )

    assert start_session(prompt="第一条输入", entry=ENTRY_SERVE, env=env) is None
    segment = await run_turn_segment(
        env=env, segment_id="seg-1", first_turn_index=1, cancel=asyncio.Event()
    )
    assert end_session(env=env, stop_reason=segment.stop_reason, turns=segment.turns) is None

    records = read_events(log.path)
    assert records[0].type == "session/start"
    assert records[0].payload["entry"] == "serve"
    assert [record.type for record in records if record.type.startswith("segment/")] == [
        "segment/start",
        "segment/end",
    ]
    assert records[-1].type == "session/end"


async def test_each_turn_is_closed_before_the_next_one_starts(tmp_path: Path) -> None:
    log, _ = await run_session_fixture(
        tmp_path,
        "s-multi",
        FixtureProvider(entries=_tool_call_entries(3)),
        registry=ToolRegistry(),
        max_turns=3,
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
            entry=ENTRY_RUN,
            provider=FixtureProvider(entries=[{"content": "done", "finish_reason": "stop"}]),
            log=log,
            registry=ToolRegistry(),
            settings=SessionSettings(workspace=tmp_path, provider_name="mock", max_turns=8),
            cancel=asyncio.Event(),
        )
    finally:
        os.chmod(log.path, stat.S_IREAD | stat.S_IWRITE)

    assert outcome.stop_reason == "LOG_WRITE_FAILED"
    assert outcome.failure_code == "LOG_WRITE_FAILED"
    assert log.path.read_text(encoding="utf-8") == ""


class _BoomArgs(ToolArgs):
    """没有参数：这条判据只关心执行段里逃出来的异常。"""


async def _boom(_: _BoomArgs, __: DispatchContext) -> ToolResult:
    raise RuntimeError("执行段里逃出来的内核 bug")


_BUGGY_REGISTRY = ToolRegistry(
    [
        ToolDefinition(
            name="boom",
            description="执行段里抛出一个不属于任何异常族的异常",
            args_model=_BoomArgs,
            mutates=False,
            run=_boom,
        )
    ]
)


async def test_an_escaped_exception_is_not_renamed_to_a_cancellation(tmp_path: Path) -> None:
    """执行段逃出来的异常走 `error/internal`，run 以内部错误收尾。

    不变量 F：日志说的是真相。把真 bug 改名成 `TOOL_CANCELLED`，读日志的人会去找一次
    没有发生过的取消。规格里那条「无法归类的内部故障仍走 error 命名空间」在 seam ① 也得成立。
    """
    log, outcome = await run_session_fixture(
        tmp_path,
        "s-escaped-exception",
        FixtureProvider(entries=[turn_entry(tool_call("boom", "c1")), DONE]),
        registry=_BUGGY_REGISTRY,
        max_turns=4,
    )

    records = read_events(log.path)
    internal = [record for record in records if record.type == "error/internal"]
    assert len(internal) == 1
    assert internal[0].payload["tool_call_id"] == "c1"
    assert "RuntimeError" in internal[0].payload["detail"]
    assert "tool/cancelled" not in [record.type for record in records]
    assert ("c1", "TOOL_CANCELLED") not in result_outcomes(records)
    assert outcome.stop_reason == "INTERNAL_ERROR"
    assert outcome.failure_code == "INTERNAL_ERROR"


async def test_an_escaped_exception_leaves_the_call_unpaired_and_fold_closes_it(
    tmp_path: Path,
) -> None:
    """内核不给未配对的调用在日志里编一条结果：闭合是读方派生（design D1）。

    执行段逃出来的异常是 run 里唯一会留下「有 `tool/call` 没 `tool/result`」的形状——硬杀那个
    形状归 seam ⑥。日志里没有一条结果配它，`TOOL_OUTCOME_UNKNOWN` 只出现在折叠出来的消息里；
    把它写进日志就是替这次调用编一个它没有拿到的结果。
    """
    log, _ = await run_session_fixture(
        tmp_path,
        "s-escaped-unpaired",
        FixtureProvider(entries=[turn_entry(tool_call("boom", "c1")), DONE]),
        registry=_BUGGY_REGISTRY,
        max_turns=4,
    )

    records = read_events(log.path)
    assert "c1" in call_ids(records, "tool/call")
    assert "c1" not in call_ids(records, "tool/result")
    assert "TOOL_OUTCOME_UNKNOWN" not in [outcome for _, outcome in result_outcomes(records)]

    closers = [message for message in fold(records).messages if message.role == "tool"]
    assert [message.tool_call_id for message in closers] == ["c1"]
    assert [message.content for message in closers] == ["TOOL_OUTCOME_UNKNOWN"]


async def test_context_assembled_carries_the_turn_id_it_belongs_to(tmp_path: Path) -> None:
    log, _ = await run_session_fixture(
        tmp_path,
        "s-turnid",
        FixtureProvider(entries=_tool_call_entries(2)),
        registry=ToolRegistry(),
        max_turns=2,
    )

    assembled = [record for record in read_events(log.path) if record.type == "context/assembled"]
    assert len(assembled) == 2
    assert [record.payload["turn_id"] for record in assembled] == ["t1", "t2"]


async def test_empty_tool_calls_ends_the_loop_with_model_completed(tmp_path: Path) -> None:
    log, outcome = await run_session_fixture(
        tmp_path,
        "s-stop",
        FixtureProvider(entries=[{"content": "done", "finish_reason": "stop"}]),
        registry=ToolRegistry(),
        max_turns=8,
    )

    records = read_events(log.path)
    turn_end = [record for record in records if record.type == "turn/end"]
    assert len(turn_end) == 1
    assert turn_end[0].payload["stop_reason"] == "MODEL_COMPLETED"
    assert outcome.stop_reason == "MODEL_COMPLETED"


async def test_reaching_max_turns_stops_with_max_turns_and_no_failure(tmp_path: Path) -> None:
    log, outcome = await run_session_fixture(
        tmp_path,
        "s-max",
        FixtureProvider(entries=_tool_call_entries(5)),
        registry=ToolRegistry(),
        max_turns=2,
    )

    records = read_events(log.path)
    last_turn_end = [record for record in records if record.type == "turn/end"][-1]
    assert last_turn_end.payload["stop_reason"] == "MAX_TURNS"
    assert outcome.stop_reason == "MAX_TURNS"
    assert outcome.failure_code is None
    assert outcome.turns == 2


async def test_turn_that_requests_tool_calls_closes_with_tool_calls(tmp_path: Path) -> None:
    log, outcome = await run_session_fixture(
        tmp_path,
        "s-toolcalls",
        FixtureProvider(
            entries=[*_tool_call_entries(1), {"content": "done", "finish_reason": "stop"}]
        ),
        registry=ToolRegistry(),
        max_turns=8,
    )

    records = read_events(log.path)
    turn_ends = [record.payload["stop_reason"] for record in records if record.type == "turn/end"]
    assert turn_ends == ["TOOL_CALLS", "MODEL_COMPLETED"]
    assert outcome.stop_reason == "MODEL_COMPLETED"


class _DeltaProvider:
    """记录循环传下来的 delta sink，并吐一段正文。"""

    def __init__(self) -> None:
        self.sink: object = None

    async def generate(
        self,
        messages: object,
        tools: object,
        signal: asyncio.Event,
        on_delta: object = None,
        on_reasoning: object = None,
    ) -> AssistantTurn:
        self.sink = on_delta
        if callable(on_delta):
            await on_delta("x")
        return AssistantTurn(content="x", finish_reason="stop")


async def test_the_turn_loop_passes_a_delta_sink_to_the_provider(tmp_path: Path) -> None:
    seen: list[tuple[str, str]] = []

    async def sink(turn_id: str, text: str) -> None:
        seen.append((turn_id, text))

    provider = _DeltaProvider()
    log, _ = await run_session_fixture(
        tmp_path,
        "s-delta",
        provider,
        on_delta=sink,
        max_turns=8,
    )

    types = [record.type for record in read_events(log.path)]
    assert provider.sink is not None
    assert seen == [("t1", "x")]
    assert "model/delta" not in types


class _AbortStreamProvider:
    """适配器在流式读取中取消：先吐半段，再返回 `PROVIDER_ABORTED`。"""

    def __init__(self, cancel: asyncio.Event) -> None:
        self._cancel = cancel

    async def generate(
        self,
        messages: object,
        tools: object,
        signal: asyncio.Event,
        on_delta: object = None,
        on_reasoning: object = None,
    ) -> ProviderFailure:
        if callable(on_delta):
            await on_delta("半")
        self._cancel.set()
        return ProviderFailure("PROVIDER_ABORTED", "取消")


async def test_a_provider_aborted_stream_turn_ends_aborted(tmp_path: Path) -> None:
    cancel = asyncio.Event()
    seen: list[tuple[str, str]] = []

    async def sink(turn_id: str, text: str) -> None:
        seen.append((turn_id, text))

    log, outcome = await run_session_fixture(
        tmp_path,
        "s-provider-abort",
        _AbortStreamProvider(cancel),
        registry=ToolRegistry(),
        cancel=cancel,
        on_delta=sink,
        max_turns=8,
    )

    records = read_events(log.path)
    types = [record.type for record in records]
    assert seen == [("t1", "半")]
    response = next(record for record in records if record.type == "model/response")
    assert response.payload["interrupted"] is True
    assert "error/model" not in types
    assert "error/abort" in types
    assert outcome.stop_reason == "ABORTED"


class _CancelDuringGenerate:
    """模拟回合中途取消：`generate` 期间把取消信号置起。"""

    def __init__(self, cancel: asyncio.Event) -> None:
        self._cancel = cancel

    async def generate(
        self,
        messages: object,
        tools: object,
        signal: asyncio.Event,
        on_delta: object = None,
        on_reasoning: object = None,
    ) -> AssistantTurn:
        if callable(on_delta):
            await on_delta("半")
        self._cancel.set()
        return AssistantTurn(content="部分回复", finish_reason="stop")


async def test_cancel_signal_ends_the_turn_with_aborted(tmp_path: Path) -> None:
    cancel = asyncio.Event()
    log, outcome = await run_session_fixture(
        tmp_path,
        "s-cancel",
        _CancelDuringGenerate(cancel),
        registry=ToolRegistry(),
        cancel=cancel,
        max_turns=8,
    )

    records = read_events(log.path)
    turn_end = [record for record in records if record.type == "turn/end"][-1]
    assert turn_end.payload["stop_reason"] == "ABORTED"
    assert records[-1].type == "session/end"
    assert records[-1].payload["stop_reason"] == "ABORTED"
    assert outcome.stop_reason == "ABORTED"


async def test_a_cancelled_turn_writes_an_error_abort_event(tmp_path: Path) -> None:
    cancel = asyncio.Event()
    log, outcome = await run_session_fixture(
        tmp_path,
        "s-abort",
        _CancelDuringGenerate(cancel),
        registry=ToolRegistry(),
        cancel=cancel,
        max_turns=8,
    )

    records = read_events(log.path)
    aborts = [record for record in records if record.type == "error/abort"]
    assert len(aborts) == 1
    assert aborts[0].payload["turn_id"] == "t1"
    assert aborts[0].payload["code"] == "ABORTED"
    assert [record.type for record in records][-4:] == [
        "error/abort",
        "turn/end",
        "segment/end",
        "session/end",
    ]
    assert outcome.stop_reason == "ABORTED"


async def test_a_cancel_during_stream_writes_an_interrupted_response(tmp_path: Path) -> None:
    cancel = asyncio.Event()
    seen: list[tuple[str, str]] = []

    async def sink(turn_id: str, text: str) -> None:
        seen.append((turn_id, text))

    log, outcome = await run_session_fixture(
        tmp_path,
        "s-stream-abort",
        _CancelDuringGenerate(cancel),
        registry=ToolRegistry(),
        cancel=cancel,
        on_delta=sink,
        max_turns=8,
    )

    records = read_events(log.path)
    types = [record.type for record in records]
    assert seen == [("t1", "半")]
    response = next(record for record in records if record.type == "model/response")
    assert response.payload["interrupted"] is True
    assert response.payload["blocks"] == [{"type": "text", "text": "半"}]
    assert "error/abort" in types
    assert outcome.stop_reason == "ABORTED"


async def test_provider_failure_is_recorded_as_error_model_and_provider_error(
    tmp_path: Path,
) -> None:
    log, outcome = await run_session_fixture(
        tmp_path,
        "s-fail",
        FixtureProvider(entries=[]),
        registry=ToolRegistry(),
        max_turns=8,
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
        self.calls: list[tuple[str, int, tuple[str, ...]]] = []
        self.signals: list[object] = []

    async def generate(self, *args: object, **kwargs: object) -> AssistantTurn:
        self.calls.append(("generate", len(args), tuple(kwargs)))
        self.signals.append(args[2] if len(args) == 3 else None)
        return AssistantTurn(content="done", finish_reason="stop")


async def test_loop_only_calls_generate_with_three_positional_parameters(tmp_path: Path) -> None:
    cancel = asyncio.Event()
    spy = _SpyProvider()
    await run_session_fixture(
        tmp_path,
        "s-spy",
        spy,
        registry=ToolRegistry(),
        cancel=cancel,
        max_turns=8,
    )

    assert spy.calls == [("generate", 3, ("on_delta", "on_reasoning"))]
    assert spy.signals[0] is cancel


def _two_write_entries() -> list[dict[str, object]]:
    return [
        {
            "content": "两处写",
            "finish_reason": "tool_calls",
            "tool_calls": [
                {"id": "c1", "name": "write", "arguments": {"file_path": "a.md", "content": "x\n"}},
                {"id": "c2", "name": "write", "arguments": {"file_path": "b.md", "content": "y\n"}},
            ],
        },
        {"content": "这一轮不该被走到", "finish_reason": "stop"},
    ]


async def test_a_fence_denial_ends_the_run_without_dispatching_the_rest(
    tmp_path: Path,
) -> None:
    log, outcome = await run_session_fixture(
        tmp_path,
        "s-fence",
        FixtureProvider(entries=_two_write_entries()),
        sandbox="read-only",
        max_turns=8,
    )

    records = read_events(log.path)
    assert [record.type for record in records] == [
        "session/start",
        "segment/start",
        "turn/start",
        "context/assembled",
        "model/request",
        "model/response",
        "tool/call",
        "tool/result",
        "error/fence",
        "turn/end",
        "segment/end",
        "session/end",
    ]
    assert [r.payload["tool_call_id"] for r in records if r.type == "tool/call"] == ["c1"]
    assert records[-3].payload["stop_reason"] == "FENCE_DENIED"
    assert records[-1].payload["stop_reason"] == "FENCE_DENIED"
    assert outcome.stop_reason == "FENCE_DENIED"
    assert not (tmp_path / "a.md").exists()
    assert not (tmp_path / "b.md").exists()
    denied = next(record for record in records if record.type == "error/fence")
    assert denied.payload["code"] == "SANDBOX_DENIES_WRITE"
    assert denied.payload["raw_path"] == "a.md"
    assert denied.payload["path"] is None


async def test_the_fence_denial_record_carries_both_path_fields(tmp_path: Path) -> None:
    """`error/fence` 的两个路径字段各有取值：判据不需要读自由文本 `detail`。"""
    entries = [
        {
            "content": "写到工作区外",
            "finish_reason": "tool_calls",
            "tool_calls": [
                {
                    "id": "c1",
                    "name": "write",
                    "arguments": {"file_path": "../outside.md", "content": "x\n"},
                }
            ],
        },
        {"content": "算了", "finish_reason": "stop"},
    ]
    log, _ = await run_session_fixture(
        tmp_path, "s-fence-paths", FixtureProvider(entries=entries), max_turns=8
    )

    records = read_events(log.path)
    fence = next(record for record in records if record.type == "error/fence")
    assert fence.payload["code"] == "OUTSIDE_WORKSPACE"
    assert fence.payload["raw_path"] == "../outside.md"
    assert fence.payload["path"] == path_key(tmp_path, "../outside.md")
    assert not (tmp_path.parent / "outside.md").exists()


async def test_a_cancel_at_the_turn_boundary_writes_no_tool_cancelled(tmp_path: Path) -> None:
    """取消发生在回合边界（`generate` 期间）时不写 `tool/cancelled`。

    打断正在执行的调用必写，那一半在 `test_turn_cancel.py` 的
    `test_a_cancel_interrupts_the_call_that_is_running`。两条合起来才是规格里那对判据：
    这个词只属于「被打断的那个调用」。
    """
    cancel = asyncio.Event()
    log, _ = await run_session_fixture(
        tmp_path,
        "s-no-cancel-event",
        _CancelDuringGenerate(cancel),
        registry=ToolRegistry(),
        cancel=cancel,
        max_turns=8,
    )

    records = read_events(log.path)
    types = [record.type for record in records]
    assert "tool/cancelled" not in types
    # 词表外的类型会被 `EventLog.append` 塌成 `error/internal`，所以还要看它记下的原类型。
    unrecognized = [record.payload.get("unrecognized_type") for record in records]
    assert "tool/cancelled" not in unrecognized
    assert "error/abort" in types


async def test_a_fenced_fixture_run_writes_no_model_retry(tmp_path: Path) -> None:
    """围栏拒绝收尾的 run 里没有 `model/retry`：重试事实只属于真实适配器的那条路径。"""
    log, _ = await run_session_fixture(
        tmp_path / "fence",
        "s-no-retry",
        FixtureProvider(entries=_two_write_entries()),
        sandbox="read-only",
        max_turns=8,
    )

    records = read_events(log.path)
    types = [record.type for record in records]
    assert "model/retry" not in types
    unrecognized = [record.payload.get("unrecognized_type") for record in records]
    assert "model/retry" not in unrecognized
    assert "error/fence" in types


def _openai_provider(bodies: list[dict[str, object]]) -> OpenAICompatProvider:
    """按顺序回放响应体的假 HTTP 层；最后一个体重复回放。"""
    index = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal index
        body = bodies[min(index, len(bodies) - 1)]
        index += 1
        return httpx.Response(200, json=body)

    return OpenAICompatProvider(
        base_url="http://127.0.0.1:9/v1",
        model="test-model",
        api_key=None,
        transport=httpx.MockTransport(handler),
    )


_ONE_TURN_TWO_CALLS: list[dict[str, object]] = [
    {
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {
                            "id": "c1",
                            "type": "function",
                            "function": {
                                "name": "read",
                                "arguments": '{"file_path": "a.md"}',
                            },
                        },
                        {
                            "id": "c2",
                            "type": "function",
                            "function": {
                                "name": "read",
                                "arguments": '{"file_path": "b.md"}',
                            },
                        },
                    ],
                },
                "finish_reason": "tool_calls",
            }
        ]
    },
    {
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": "完成", "tool_calls": []},
                "finish_reason": "stop",
            }
        ]
    },
]


async def test_one_turn_with_two_tool_calls_dispatches_both(tmp_path: Path) -> None:
    """一轮里两个工具调用都要派发，第二个不许被吞掉。"""
    (tmp_path / "a.md").write_text("甲", encoding="utf-8")
    (tmp_path / "b.md").write_text("乙", encoding="utf-8")
    log, outcome = await run_session_fixture(
        tmp_path,
        "s-two-calls",
        _openai_provider(_ONE_TURN_TWO_CALLS),
        prompt="读两个文件",
        max_turns=8,
    )

    records = read_events(log.path)
    calls = [record for record in records if record.type == "tool/call"]
    results = [record for record in records if record.type == "tool/result"]
    first_turn_end = next(record for record in records if record.type == "turn/end")

    assert [record.payload["tool_call_id"] for record in calls] == ["c1", "c2"]
    assert [record.payload["tool_call_id"] for record in results] == ["c1", "c2"]
    assert [record.payload["outcome"] for record in results] == ["OK", "OK"]
    assert first_turn_end.payload["stop_reason"] == "TOOL_CALLS"
    assert outcome.turns == 2
    assert outcome.stop_reason == "MODEL_COMPLETED"


_STOP_BODY: dict[str, object] = {
    "choices": [
        {
            "index": 0,
            "message": {"role": "assistant", "content": "完成", "tool_calls": []},
            "finish_reason": "stop",
        }
    ]
}


def _scripted_provider(responses: list[httpx.Response]) -> OpenAICompatProvider:
    """按顺序回放响应；最后一个重复回放。"""
    state = {"index": 0}

    def handle(request: httpx.Request) -> httpx.Response:
        response = responses[min(state["index"], len(responses) - 1)]
        state["index"] += 1
        return response

    return OpenAICompatProvider(
        base_url="http://127.0.0.1:9/v1",
        model="test-model",
        api_key=None,
        transport=httpx.MockTransport(handle),
    )


async def _run_with_provider(tmp_path: Path, provider: OpenAICompatProvider):
    log, outcome = await run_session_fixture(tmp_path, "s-retry", provider, max_turns=8)
    records = read_events(log.path)
    assert isinstance(records, list)
    return records, outcome


async def test_a_429_then_200_retries_once_and_writes_one_model_retry(tmp_path: Path) -> None:
    provider = _scripted_provider(
        [httpx.Response(429, json={"error": "slow down"}), httpx.Response(200, json=_STOP_BODY)]
    )

    records, outcome = await _run_with_provider(tmp_path, provider)
    types = [record.type for record in records]

    assert types == [
        "session/start",
        "segment/start",
        "turn/start",
        "context/assembled",
        "model/request",
        "model/retry",
        "model/response",
        "turn/end",
        "segment/end",
        "session/end",
    ]
    retries = [record.payload for record in records if record.type == "model/retry"]
    assert len(retries) == 1
    assert retries[0]["attempt"] == 1
    assert retries[0]["status"] == 429
    assert retries[0]["turn_id"] == records[2].payload["turn_id"]
    assert outcome.stop_reason == "MODEL_COMPLETED"
    assert outcome.failure_code is None


async def test_two_500s_write_one_model_retry_then_error_model(tmp_path: Path) -> None:
    provider = _scripted_provider(
        [httpx.Response(500, json={"error": "boom"}), httpx.Response(500, json={"error": "boom"})]
    )

    records, outcome = await _run_with_provider(tmp_path, provider)
    types = [record.type for record in records]

    assert types == [
        "session/start",
        "segment/start",
        "turn/start",
        "context/assembled",
        "model/request",
        "model/retry",
        "error/model",
        "turn/end",
        "segment/end",
        "session/end",
    ]
    retries = [record.payload for record in records if record.type == "model/retry"]
    assert len(retries) == 1
    assert retries[0]["status"] == 500
    assert outcome.stop_reason == "PROVIDER_ERROR"
    assert outcome.failure_code == "PROVIDER_HTTP_STATUS"


async def test_the_provider_sentence_reaches_the_error_model_detail(tmp_path: Path) -> None:
    """seam ① 接 seam ⑤：失败结果里那句正文原样回到 `error/model` 的 `detail`。"""
    provider = _scripted_provider(
        [httpx.Response(502, text="<html><body>Bad Gateway</body></html>" * 30)]
    )

    records, outcome = await _run_with_provider(tmp_path, provider)
    errors = [record for record in records if record.type == "error/model"]

    assert len(errors) == 1
    assert errors[0].payload["code"] == "PROVIDER_HTTP_STATUS"
    assert errors[0].payload["detail"].startswith("HTTP 502：<html>")
    assert len(errors[0].payload["detail"]) <= 200
    assert outcome.failure_code == "PROVIDER_HTTP_STATUS"


async def test_a_400_is_not_retried(tmp_path: Path) -> None:
    provider = _scripted_provider([httpx.Response(400, json={"error": "bad request"})])

    records, outcome = await _run_with_provider(tmp_path, provider)
    types = [record.type for record in records]

    assert types == [
        "session/start",
        "segment/start",
        "turn/start",
        "context/assembled",
        "model/request",
        "error/model",
        "turn/end",
        "segment/end",
        "session/end",
    ]
    assert outcome.failure_code == "PROVIDER_HTTP_STATUS"


async def test_a_timeout_is_a_provider_timeout_result(tmp_path: Path) -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("连接超时")

    provider = OpenAICompatProvider(
        base_url="http://127.0.0.1:9/v1",
        model="test-model",
        api_key=None,
        timeout_s=0.05,
        transport=httpx.MockTransport(handle),
    )

    records, outcome = await _run_with_provider(tmp_path, provider)
    types = [record.type for record in records]

    assert "model/retry" not in types
    assert outcome.stop_reason == "PROVIDER_ERROR"
    assert outcome.failure_code == "PROVIDER_TIMEOUT"


_FORGED_STOP: dict[str, object] = {
    "content": "done",
    "finish_reason": "stop",
    "attempts": [{"attempt": 1, "status": 429}],
}

_SCENE_ENTRIES: list[dict[str, object]] = [
    {
        "content": "",
        "finish_reason": "tool_calls",
        "tool_calls": [{"id": "c1", "name": "read", "arguments": {"file_path": "a.md"}}],
    },
    {"content": "完成", "finish_reason": "stop"},
]

_SCENE_BODIES: list[dict[str, object]] = [
    {
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {
                            "id": "c1",
                            "type": "function",
                            "function": {
                                "name": "read",
                                "arguments": '{"file_path": "a.md"}',
                            },
                        }
                    ],
                },
                "finish_reason": "tool_calls",
            }
        ]
    },
    _STOP_BODY,
]


async def _run_through(
    tmp_path: Path, provider: Provider, session_id: str, workspace: Path, provider_name: str
) -> tuple[list[EventRecord], RunOutcome]:
    log, outcome = await run_session_fixture(
        tmp_path,
        session_id,
        provider,
        workspace=workspace,
        session_dir=tmp_path / session_id,
        provider_name=provider_name,
        max_turns=8,
    )
    records = read_events(log.path)
    assert isinstance(records, list)
    return records, outcome


async def test_the_same_scene_through_both_providers_writes_the_same_log(
    tmp_path: Path,
) -> None:
    """规格 scenario「两种 provider 走同一入口」：同一个场景各跑一遍，日志序列与关键 payload 一致。

    `session/start` 比的是「除了 provider 与端点那三个字段之外」——那一处本来就该不同。
    """
    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True)
    (workspace / "a.md").write_text("文件内容", encoding="utf-8")

    mock_records, mock_outcome = await _run_through(
        tmp_path, FixtureProvider(entries=_SCENE_ENTRIES), "s-mock", workspace, "mock"
    )
    openai_records, openai_outcome = await _run_through(
        tmp_path,
        _scripted_provider([httpx.Response(200, json=body) for body in _SCENE_BODIES]),
        "s-openai",
        workspace,
        "openai",
    )

    assert [record.type for record in mock_records] == [record.type for record in openai_records]
    for key in ("tool/call", "tool/result", "model/response", "turn/end"):
        mine = [record.payload for record in mock_records if record.type == key]
        theirs = [record.payload for record in openai_records if record.type == key]
        assert mine == theirs, key
    mine_start = next(record.payload for record in mock_records if record.type == "session/start")
    theirs_start = next(
        record.payload for record in openai_records if record.type == "session/start"
    )
    # 只有「选了哪个 provider、指向哪儿」这一处允许不同；其余设置必须逐字一致。
    chosen = {"provider", "base_url", "model", "api_key_env"}
    assert {k: v for k, v in mine_start.items() if k not in chosen} == {
        k: v for k, v in theirs_start.items() if k not in chosen
    }
    assert mine_start["provider"] == "mock"
    assert theirs_start["provider"] == "openai"
    assert mock_outcome.stop_reason == openai_outcome.stop_reason == "MODEL_COMPLETED"
    assert mock_outcome.turns == openai_outcome.turns == 2


async def test_a_fixture_cannot_invent_a_model_retry(tmp_path: Path) -> None:
    """重试事实只能由真实适配器带回。fixture 里写 `attempts` 不得凭空造出 `model/retry`。"""
    log, _ = await run_session_fixture(
        tmp_path,
        "s-forge",
        FixtureProvider(entries=[_FORGED_STOP]),
        registry=ToolRegistry(),
        max_turns=8,
    )

    types = [record.type for record in read_events(log.path)]
    assert "model/retry" not in types


async def test_a_tool_call_is_unknown_when_the_whitelist_is_empty(tmp_path: Path) -> None:
    """工具表为空时模型照样被调用：调用落到派发段的 `UNKNOWN_TOOL`，回合照常闭合。"""
    log, outcome = await run_session_fixture(
        tmp_path,
        "s-notools",
        FixtureProvider(
            entries=[
                {
                    "content": "调一个不在表里的工具",
                    "finish_reason": "tool_calls",
                    "tool_calls": [
                        {"id": "c1", "name": "read", "arguments": {"file_path": "a.md"}},
                    ],
                },
                {"content": "算了", "finish_reason": "stop"},
            ]
        ),
        registry=build_registry([]),
        max_turns=8,
    )

    records = read_events(log.path)
    assert result_outcomes(records) == [("c1", "UNKNOWN_TOOL")]
    assert [record.type for record in records].count("turn/end") == 2
    assert outcome.stop_reason == "MODEL_COMPLETED"


async def test_the_endpoint_fields_come_from_one_endpoint_object(tmp_path: Path) -> None:
    """端点三条是一个对象：有它就三条齐、没有就三条都不在，不靠「是不是 openai」各判一遍。"""
    with_endpoint, _ = await run_session_fixture(
        tmp_path,
        "s-endpoint",
        FixtureProvider(entries=[DONE]),
        provider_name="openai",
        endpoint=ProviderEndpoint(
            base_url="https://example.test/v1",
            model="test-model",
            api_key_env="TEST_KEY",
        ),
    )
    without, _ = await run_session_fixture(
        tmp_path, "s-noendpoint", FixtureProvider(entries=[DONE])
    )

    start_with = next(
        record.payload
        for record in read_events(with_endpoint.path)
        if record.type == "session/start"
    )
    start_without = next(
        record.payload for record in read_events(without.path) if record.type == "session/start"
    )
    assert start_with["base_url"] == "https://example.test/v1"
    assert start_with["model"] == "test-model"
    assert start_with["api_key_env"] == "TEST_KEY"
    assert "base_url" not in start_without
    assert "model" not in start_without
    assert "api_key_env" not in start_without


async def test_a_builtin_tool_filtered_out_by_the_whitelist_is_unknown(tmp_path: Path) -> None:
    """内置不等于在册：白名单只留 `read` 时，内置的 `grep` 照样是 `UNKNOWN_TOOL`，回合照常闭合。"""
    log, outcome = await run_session_fixture(
        tmp_path,
        "s-grep-filtered",
        FixtureProvider(
            entries=[
                {
                    "content": "用 grep 找一下",
                    "finish_reason": "tool_calls",
                    "tool_calls": [{"id": "c1", "name": "grep", "arguments": {"pattern": "x"}}],
                },
                {"content": "算了", "finish_reason": "stop"},
            ]
        ),
        registry=build_registry(["read"]),
        max_turns=8,
    )

    records = read_events(log.path)
    assert result_outcomes(records) == [("c1", "UNKNOWN_TOOL")]
    assert [record.type for record in records].count("turn/end") == 2
    assert outcome.stop_reason == "MODEL_COMPLETED"


class _ReasoningCancelProvider:
    def __init__(self, cancel: asyncio.Event) -> None:
        self._cancel = cancel

    async def generate(
        self,
        messages: object,
        tools: object,
        signal: asyncio.Event,
        on_delta: object = None,
        on_reasoning: object = None,
    ) -> ProviderFailure:
        if callable(on_reasoning):
            await on_reasoning("", 0, "想")
        self._cancel.set()
        return ProviderFailure("PROVIDER_ABORTED", "取消")


class _SchemaAfterTextProvider:
    async def generate(
        self,
        messages: object,
        tools: object,
        signal: asyncio.Event,
        on_delta: object = None,
        on_reasoning: object = None,
    ) -> ProviderFailure:
        if callable(on_delta):
            await on_delta("半")
        return ProviderFailure("PROVIDER_SCHEMA_INVALID", "坏标签")


async def test_cancel_with_reasoning_prefix_writes_interrupted_reasoning_block(
    tmp_path: Path,
) -> None:
    cancel = asyncio.Event()
    log, outcome = await run_session_fixture(
        tmp_path,
        "s-reasoning-cancel",
        _ReasoningCancelProvider(cancel),
        registry=ToolRegistry(),
        cancel=cancel,
        on_reasoning=lambda *_args: asyncio.sleep(0),
        max_turns=4,
    )

    records = read_events(log.path)
    response = next(record for record in records if record.type == "model/response")
    assert response.payload["interrupted"] is True
    assert response.payload["blocks"] == [{"type": "reasoning", "text": "想"}]
    assert outcome.stop_reason == "ABORTED"
    assert "model/attempt" not in [record.type for record in records]


async def test_schema_failure_with_prefix_writes_attempt_not_response(
    tmp_path: Path,
) -> None:
    log, outcome = await run_session_fixture(
        tmp_path,
        "s-schema-prefix",
        _SchemaAfterTextProvider(),
        registry=ToolRegistry(),
        on_delta=lambda *_args: asyncio.sleep(0),
        max_turns=4,
    )

    records = read_events(log.path)
    types = [record.type for record in records]
    assert "model/response" not in types
    attempt = next(record for record in records if record.type == "model/attempt")
    assert attempt.payload["error_code"] == "PROVIDER_SCHEMA_INVALID"
    assert attempt.payload["partial_blocks"] == [{"type": "text", "text": "半"}]
    assert outcome.stop_reason == "PROVIDER_ERROR"
