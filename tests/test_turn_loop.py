"""seam ①：显式回合主循环。"""

from __future__ import annotations

import asyncio
import os
import stat
from pathlib import Path

import httpx

from mini_harness.events import EventLog, EventRecord, read_events
from mini_harness.loop import RunOutcome, SessionSettings, run_session
from mini_harness.provider import AssistantTurn, FixtureProvider, Provider
from mini_harness.provider.openai_compat import OpenAICompatProvider
from mini_harness.tools import ToolRegistry
from mini_harness.tools.fences import path_key
from tool_harness import run_session_fixture


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
    assert [record.type for record in records][-3:] == ["error/abort", "turn/end", "session/end"]
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
        self.calls: list[tuple[str, int]] = []
        self.signals: list[object] = []

    async def generate(self, *args: object, **kwargs: object) -> AssistantTurn:
        self.calls.append(("generate", len(args) + len(kwargs)))
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

    assert spy.calls == [("generate", 3)]
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
        "turn/start",
        "context/assembled",
        "model/request",
        "model/response",
        "tool/call",
        "tool/result",
        "error/fence",
        "turn/end",
        "session/end",
    ]
    assert [r.payload["tool_call_id"] for r in records if r.type == "tool/call"] == ["c1"]
    assert records[-2].payload["stop_reason"] == "FENCE_DENIED"
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


async def test_no_m2_scenario_writes_tool_cancelled_or_model_retry(tmp_path: Path) -> None:
    cancel = asyncio.Event()
    cancel_log, _ = await run_session_fixture(
        tmp_path,
        "s-no-cancel-event",
        _CancelDuringGenerate(cancel),
        registry=ToolRegistry(),
        cancel=cancel,
        max_turns=8,
    )
    fence_log, _ = await run_session_fixture(
        tmp_path / "fence",
        "s-no-retry",
        FixtureProvider(entries=_two_write_entries()),
        sandbox="read-only",
        max_turns=8,
    )

    types = [record.type for record in read_events(cancel_log.path)]
    types += [record.type for record in read_events(fence_log.path)]
    assert "tool/cancelled" not in types
    assert "model/retry" not in types
    # 词表外的类型会被 `EventLog.append` 塌成 `error/internal`，所以还要看它记下的原类型。
    unrecognized = [
        record.payload.get("unrecognized_type")
        for record in read_events(cancel_log.path) + read_events(fence_log.path)
    ]
    assert "tool/cancelled" not in unrecognized
    assert "model/retry" not in unrecognized
    assert "error/abort" in types
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
        "turn/start",
        "context/assembled",
        "model/request",
        "model/retry",
        "model/response",
        "turn/end",
        "session/end",
    ]
    retries = [record.payload for record in records if record.type == "model/retry"]
    assert len(retries) == 1
    assert retries[0]["attempt"] == 1
    assert retries[0]["status"] == 429
    assert retries[0]["turn_id"] == records[1].payload["turn_id"]
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
        "turn/start",
        "context/assembled",
        "model/request",
        "model/retry",
        "error/model",
        "turn/end",
        "session/end",
    ]
    retries = [record.payload for record in records if record.type == "model/retry"]
    assert len(retries) == 1
    assert retries[0]["status"] == 500
    assert outcome.stop_reason == "PROVIDER_ERROR"
    assert outcome.failure_code == "PROVIDER_HTTP_STATUS"


async def test_a_400_is_not_retried(tmp_path: Path) -> None:
    provider = _scripted_provider([httpx.Response(400, json={"error": "bad request"})])

    records, outcome = await _run_with_provider(tmp_path, provider)
    types = [record.type for record in records]

    assert types == [
        "session/start",
        "turn/start",
        "context/assembled",
        "model/request",
        "error/model",
        "turn/end",
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
