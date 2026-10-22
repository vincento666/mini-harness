"""seam ①：超时与取消落进回合——`tool/cancelled` 与它的配对。"""

from __future__ import annotations

import asyncio
from pathlib import Path

from mini_harness.events import EventRecord, read_events
from mini_harness.events.fold import fold
from mini_harness.loop import ENTRY_RUN, ENTRY_SERVE, end_session, run_turn_segment, start_session
from mini_harness.provider import FixtureProvider
from mini_harness.tools.fences import ApprovalDecision
from tool_harness import (
    DONE,
    Intervals,
    build_session_env,
    call_ids,
    cancel_after,
    full_registry,
    result_outcomes,
    run_session_fixture,
    timed_registry,
    tool_call,
    turn_entry,
)

_LOOP_SCRIPT = "import time\n\nwhile True:\n    time.sleep(0.1)\n"

# 跑满一秒之后才落一个文件：进程被打断并收掉，这个文件就不会出现。
_LEAK_SCRIPT = (
    "import pathlib, time\n\n"
    "for _ in range(10):\n"
    "    time.sleep(0.1)\n"
    "pathlib.Path('leaked.txt').write_text('还在跑', encoding='utf-8')\n"
)


def _cancelled(records: list[EventRecord]) -> list[EventRecord]:
    return [record for record in records if record.type == "tool/cancelled"]


async def test_a_timed_out_call_does_not_stop_the_rest_of_the_batch(tmp_path: Path) -> None:
    """规格 scenario「超时后回合继续」：第一个 `bash` 超时，后面那个 `read` 照常派发。"""
    (tmp_path / "a.md").write_text("甲\n", encoding="utf-8")
    (tmp_path / "loop.py").write_text(_LOOP_SCRIPT, encoding="utf-8")

    log, outcome = await run_session_fixture(
        tmp_path,
        "s-timeout-continues",
        FixtureProvider(
            entries=[
                turn_entry(
                    tool_call("bash", "c1", command="python loop.py", timeout_seconds=1),
                    tool_call("read", "c2", file_path="a.md"),
                ),
                DONE,
            ]
        ),
        registry=full_registry(),
        max_turns=4,
    )

    records = read_events(log.path)
    assert isinstance(records, list)
    assert result_outcomes(records) == [("c1", "TOOL_TIMEOUT"), ("c2", "OK")]

    # 1.3 的 payload 形状：只有 `turn_id` 与 `tool_call_id`，不带命令输出。
    assert len(_cancelled(records)) == 1
    assert _cancelled(records)[0].payload["tool_call_id"] == "c1"
    assert set(_cancelled(records)[0].payload) == {"turn_id", "tool_call_id"}

    turn_end = [record for record in records if record.type == "turn/end"]
    assert [record.payload["stop_reason"] for record in turn_end] == [
        "TOOL_CALLS",
        "MODEL_COMPLETED",
    ]
    assert outcome.stop_reason == "MODEL_COMPLETED"


async def test_a_cancel_interrupts_the_call_that_is_running(tmp_path: Path) -> None:
    """规格 scenario「取消打断正在执行的调用」：正在跑的那一条塌成 `TOOL_CANCELLED`。

    `bash` 的超时是 30 s，取消在 0.5 s 置位：结果词是 `TOOL_CANCELLED` 而不是 `TOOL_TIMEOUT`，
    这条判据本身就排除了「其实是被超时收掉的」。
    """
    (tmp_path / "loop.py").write_text(_LEAK_SCRIPT, encoding="utf-8")
    cancel = asyncio.Event()
    watcher = asyncio.create_task(cancel_after(cancel, 0.5))

    log, outcome = await run_session_fixture(
        tmp_path,
        "s-cancel-midcall",
        FixtureProvider(
            entries=[
                turn_entry(tool_call("bash", "c1", command="python loop.py", timeout_seconds=30)),
                DONE,
            ]
        ),
        registry=full_registry(),
        max_turns=4,
        cancel=cancel,
    )
    await watcher

    # 被打断的不只是结果词：那条命令的进程树也要收掉，否则它会在 1 秒后自己落下标记。
    await asyncio.sleep(1.2)
    assert not (tmp_path / "leaked.txt").exists()

    records = read_events(log.path)
    assert isinstance(records, list)
    assert result_outcomes(records) == [("c1", "TOOL_CANCELLED")]
    assert call_ids(records, "tool/cancelled") == ["c1"]
    assert [record.type for record in records if record.type == "error/abort"] == ["error/abort"]
    turn_end = [record for record in records if record.type == "turn/end"]
    assert [record.payload["stop_reason"] for record in turn_end] == ["ABORTED"]
    assert records[-1].type == "session/end"
    assert records[-1].payload["stop_reason"] == "ABORTED"
    assert outcome.stop_reason == "ABORTED"


async def test_no_call_has_a_tool_call_without_a_result_after_a_cancel(tmp_path: Path) -> None:
    """规格 scenario「取消后没有无结果的 tool/call」：声明了的每条都有一对记录。

    `c2` 占着写独占权还在跑，`c3` 排在它后面：取消之后 `c3` 不再派发，但它被声明过，
    就要有一条 `tool/call` 与一条 `outcome: ABORTED_BEFORE_DISPATCH` 的 `tool/result`（ADR-0011）。
    """
    (tmp_path / "a.md").write_text("甲\n", encoding="utf-8")
    observed: Intervals = []
    cancel = asyncio.Event()
    watcher = asyncio.create_task(cancel_after(cancel, 0.5))

    log, _ = await run_session_fixture(
        tmp_path,
        "s-cancel-pairs",
        FixtureProvider(
            entries=[
                turn_entry(
                    tool_call("read", "c1", file_path="a.md"),
                    tool_call("write", "c2", file_path="new.md", content="新\n"),
                    tool_call("write", "c3", file_path="other.md", content="新\n"),
                ),
                DONE,
            ]
        ),
        registry=timed_registry(observed, delays={"new.md": 2.0}),
        max_turns=4,
        cancel=cancel,
    )
    await watcher

    records = read_events(log.path)
    assert isinstance(records, list)
    assert call_ids(records, "tool/call") == ["c1", "c2", "c3"]
    assert call_ids(records, "tool/result") == ["c1", "c2", "c3"]
    assert set(result_outcomes(records)) == {
        ("c1", "OK"),
        ("c2", "TOOL_CANCELLED"),
        ("c3", "ABORTED_BEFORE_DISPATCH"),
    }
    assert not (tmp_path / "other.md").exists(), "结果词说它没开始，文件就必须没被写过"


async def test_the_undispatched_call_gets_no_tool_cancelled(tmp_path: Path) -> None:
    """规格 scenario「未派发的调用不算被打断」：`tool/cancelled` 只对应真的开始过的调用。

    顺带钉住取消收尾的日志前缀是完整的：本批每条 `tool/result` 都在 `error/abort` 之前落盘，
    `error/abort` 在 `turn/end` 之前，`turn/end` 在 `session/end` 之前。
    """
    (tmp_path / "a.md").write_text("甲\n", encoding="utf-8")
    observed: Intervals = []
    cancel = asyncio.Event()
    watcher = asyncio.create_task(cancel_after(cancel, 0.5))

    log, _ = await run_session_fixture(
        tmp_path,
        "s-cancel-no-cancelled",
        FixtureProvider(
            entries=[
                turn_entry(
                    tool_call("read", "c1", file_path="a.md"),
                    tool_call("write", "c2", file_path="new.md", content="新\n"),
                    tool_call("write", "c3", file_path="other.md", content="新\n"),
                ),
                DONE,
            ]
        ),
        registry=timed_registry(observed, delays={"new.md": 2.0}),
        max_turns=4,
        cancel=cancel,
    )
    await watcher

    records = read_events(log.path)
    assert isinstance(records, list)
    assert call_ids(records, "tool/cancelled") == ["c2"]

    types = [record.type for record in records]
    last_result = max(index for index, name in enumerate(types) if name == "tool/result")
    abort = types.index("error/abort")
    turn_end = types.index("turn/end")
    assert last_result < abort < turn_end < len(types) - 1
    assert types[-1] == "session/end"
    assert [
        record.payload["stop_reason"]
        for record in records
        if record.type in {"turn/end", "session/end"}
    ] == ["ABORTED", "ABORTED"]


async def test_a_read_queued_on_the_concurrency_limit_is_not_interrupted(tmp_path: Path) -> None:
    """「未派发的调用不算被打断」的第二种形状：卡在只读并发额度上的那几条。

    八条 `read` 同时在跑（额度 8），第九、第十条已经写了 `tool/call`、还卡在信号量上。
    取消在这时置位：它们没开始过，结果词是 `ABORTED_BEFORE_DISPATCH`，不配 `tool/cancelled`
    （design D5「被打断预设它开始过」）。
    """
    for index in range(1, 11):
        (tmp_path / f"n{index}.md").write_text(f"{index}\n", encoding="utf-8")
    observed: Intervals = []
    cancel = asyncio.Event()
    watcher = asyncio.create_task(cancel_after(cancel, 0.5))
    delays = {f"n{index}.md": 2.0 for index in range(1, 9)}

    log, _ = await run_session_fixture(
        tmp_path,
        "s-cancel-queued-read",
        FixtureProvider(
            entries=[
                turn_entry(
                    *(
                        tool_call("read", f"c{index}", file_path=f"n{index}.md")
                        for index in range(1, 11)
                    )
                ),
                DONE,
            ]
        ),
        registry=timed_registry(observed, delays=delays),
        max_turns=4,
        cancel=cancel,
    )
    await watcher

    records = read_events(log.path)
    assert isinstance(records, list)
    assert call_ids(records, "tool/call") == [f"c{index}" for index in range(1, 11)]
    outcomes = dict(result_outcomes(records))
    assert [outcomes[f"c{index}"] for index in range(1, 9)] == ["TOOL_CANCELLED"] * 8
    assert [outcomes[f"c{index}"] for index in range(9, 11)] == ["ABORTED_BEFORE_DISPATCH"] * 2
    assert set(call_ids(records, "tool/cancelled")) == {f"c{index}" for index in range(1, 9)}


class _DenyAndCancelGate:
    """围栏拒绝与取消同时在场：提问当场拒绝，同时把取消置位。"""

    def __init__(self, cancel: asyncio.Event) -> None:
        self._cancel = cancel

    async def request(self, *, tool_name: str, detail: str) -> ApprovalDecision:
        self._cancel.set()
        return "DENIED"


async def test_cancel_wins_over_a_fence_denial_for_the_undispatched_call(tmp_path: Path) -> None:
    """裁决「取消与围栏拒绝同时在场时取消优先到底」：未派发的落一对记录，回合以 `ABORTED` 收尾。

    围栏单独在场时后面的调用连 `tool/call` 都不写（`test_a_fence_denial_does_not_swallow_the_calls_
    dispatched_before_it`）；取消也在场时它要落一对 `ABORTED_BEFORE_DISPATCH`——「取消不再掀翻批次」
    不因围栏在场而失效。收尾理由取取消，围栏拒绝的事实不丢：`error/fence` 在盘上，
    `RunOutcome.failure_code` 仍是那个围栏码。
    """
    cancel = asyncio.Event()
    gate = _DenyAndCancelGate(cancel)

    log, outcome = await run_session_fixture(
        tmp_path,
        "s-cancel-and-fence",
        FixtureProvider(
            entries=[
                turn_entry(
                    tool_call("write", "c1", file_path="one.md", content="一\n"),
                    tool_call("write", "c2", file_path="two.md", content="二\n"),
                ),
                DONE,
            ]
        ),
        registry=full_registry(),
        approval="ask",
        approval_gate=gate,
        cancel=cancel,
        max_turns=4,
    )

    records = read_events(log.path)
    assert isinstance(records, list)
    assert call_ids(records, "tool/call") == ["c1", "c2"]
    assert set(result_outcomes(records)) == {
        ("c1", "DENIED_BY_APPROVAL"),
        ("c2", "ABORTED_BEFORE_DISPATCH"),
    }
    assert call_ids(records, "tool/cancelled") == []
    assert not (tmp_path / "one.md").exists() and not (tmp_path / "two.md").exists()
    assert [record.type for record in records if record.type in {"error/fence", "error/abort"}] == [
        "error/fence",
        "error/abort",
    ]
    # 裁决：取消优先到底——收尾理由是取消，围栏拒绝的事实留在 `error/fence` 与 `failure_code` 里。
    assert outcome.stop_reason == "ABORTED"
    assert outcome.failure_code == "APPROVAL_DENIED"


async def test_an_aborted_run_folds_into_balanced_tool_messages(tmp_path: Path) -> None:
    """取消收尾的回合折叠出来是配平的：每个工具请求消息都有对应的工具结果消息。

    这条是「会话终止由入口决定」的可观察后果——回合结束了，这段上下文之后还要能发给模型。
    形状与上一条不同：慢的那条被打断，后面两条根本没开始，于是配对要补两条。
    """
    observed: Intervals = []
    cancel = asyncio.Event()
    watcher = asyncio.create_task(cancel_after(cancel, 0.5))

    log, _ = await run_session_fixture(
        tmp_path,
        "s-cancel-balanced",
        FixtureProvider(
            entries=[
                turn_entry(
                    tool_call("write", "c1", file_path="one.md", content="一\n"),
                    tool_call("write", "c2", file_path="two.md", content="二\n"),
                    tool_call("write", "c3", file_path="three.md", content="三\n"),
                ),
                DONE,
            ]
        ),
        registry=timed_registry(observed, delays={"one.md": 2.0}),
        max_turns=4,
        cancel=cancel,
    )
    await watcher

    records = read_events(log.path)
    assert isinstance(records, list)
    context = fold(records)
    requested = sorted(
        str(call["id"]) for message in context.messages for call in message.tool_calls
    )
    answered = sorted(
        str(message.tool_call_id) for message in context.messages if message.role == "tool"
    )
    assert requested == ["c1", "c2", "c3"]
    assert answered == requested


async def test_a_run_without_interruption_writes_no_tool_cancelled(tmp_path: Path) -> None:
    """规格 scenario「没有打断就没有该记录」。"""
    (tmp_path / "a.md").write_text("甲\n", encoding="utf-8")

    log, _ = await run_session_fixture(
        tmp_path,
        "s-no-cancelled",
        FixtureProvider(entries=[turn_entry(tool_call("read", "c1", file_path="a.md")), DONE]),
        registry=full_registry(),
        max_turns=4,
    )

    records = read_events(log.path)
    assert isinstance(records, list)
    assert _cancelled(records) == []


class _CancelWhileAskingGate:
    """人还没答，取消先到：提问挂在门里，事件循环照跑得动。"""

    def __init__(self, cancel: asyncio.Event) -> None:
        self._cancel = cancel
        self.asked: list[str] = []

    async def request(self, *, tool_name: str, detail: str) -> ApprovalDecision:
        self.asked.append(tool_name)
        self._cancel.set()
        await asyncio.sleep(30)
        return "APPROVED"


async def test_a_cancel_arrives_while_the_human_is_being_asked(tmp_path: Path) -> None:
    """规格 scenario「半对只在取消收尾的 session 里成立」：提问期间取消。

    提问之前 `approval/request` 已经在盘上；取消打断挂在门里的提问，这一对就停在半对。
    这一条塌成 `TOOL_CANCELLED`，session 以 `error/abort` 收尾，工具没有执行。
    """
    cancel = asyncio.Event()
    gate = _CancelWhileAskingGate(cancel)

    log, outcome = await run_session_fixture(
        tmp_path,
        "s-cancel-while-asking",
        FixtureProvider(
            entries=[turn_entry(tool_call("write", "c1", file_path="a.md", content="A\n")), DONE]
        ),
        registry=full_registry(),
        approval="ask",
        approval_gate=gate,
        cancel=cancel,
        max_turns=4,
    )

    records = read_events(log.path)
    assert isinstance(records, list)
    assert gate.asked == ["write"]
    assert call_ids(records, "tool/call") == ["c1"]
    assert call_ids(records, "approval/request") == ["c1"]
    assert call_ids(records, "approval/response") == []
    assert result_outcomes(records) == [("c1", "TOOL_CANCELLED")]
    assert [record.payload["tool_call_id"] for record in _cancelled(records)] == ["c1"]
    assert [record.type for record in records][-4:] == [
        "error/abort",
        "turn/end",
        "segment/end",
        "session/end",
    ]
    assert outcome.stop_reason == "ABORTED"
    assert not (tmp_path / "a.md").exists()


async def test_a_cancel_closes_the_segment_and_the_entry_closes_the_session(tmp_path: Path) -> None:
    """取消终止当前段：段写 `segment/end(ABORTED)` 就停，会话怎么收尾归入口（ADR-0011）。

    一次性 run 的入口补写 `session/end` 并映射退出码 5，那条判据在 `tests/test_cli_run.py`。
    """
    cancel = asyncio.Event()
    log, env = build_session_env(
        tmp_path,
        "s-cancel-segment",
        FixtureProvider(
            entries=[turn_entry(tool_call("write", "c1", file_path="a.md", content="A\n")), DONE]
        ),
        registry=full_registry(),
        approval="ask",
        approval_gate=_CancelWhileAskingGate(cancel),
        max_turns=4,
    )

    assert start_session(prompt="任务", entry=ENTRY_RUN, env=env) is None
    segment = await run_turn_segment(env=env, segment_id="s1", first_turn_index=1, cancel=cancel)

    records = read_events(log.path)
    assert segment.stop_reason == "ABORTED"
    assert [record.type for record in records][-3:] == ["error/abort", "turn/end", "segment/end"]
    assert "session/end" not in [record.type for record in records]
    assert records[-1].payload == {"segment_id": "s1", "stop_reason": "ABORTED", "turns": 1}

    assert end_session(env=env, stop_reason=segment.stop_reason, turns=segment.turns) is None
    assert [record.type for record in read_events(log.path)][-1:] == ["session/end"]


async def test_a_cancel_at_the_serve_entry_closes_the_session_the_same_way(
    tmp_path: Path,
) -> None:
    """serve 入口的取消与 run 同形：`entry` 是 `serve`，收尾四件都在盘上。

    进程内的取消（seam ①）。真实子进程里的 SIGINT 判据在 `tests/test_cli_serve.py`，Windows 上
    skip——缺口照 M3 记进 `docs/verification/m7-serve-http-sse-manual.md`。
    """
    (tmp_path / "loop.py").write_text(_LEAK_SCRIPT, encoding="utf-8")
    cancel = asyncio.Event()
    watcher = asyncio.create_task(cancel_after(cancel, 0.5))

    log, outcome = await run_session_fixture(
        tmp_path,
        "s-cancel-serve-entry",
        FixtureProvider(
            entries=[
                turn_entry(tool_call("bash", "c1", command="python loop.py", timeout_seconds=30)),
                DONE,
            ]
        ),
        registry=full_registry(),
        max_turns=4,
        cancel=cancel,
        entry=ENTRY_SERVE,
    )
    await watcher

    records = read_events(log.path)
    assert isinstance(records, list)
    assert records[0].payload["entry"] == "serve"
    assert [record.type for record in records][-4:] == [
        "error/abort",
        "turn/end",
        "segment/end",
        "session/end",
    ]
    assert records[-1].payload["stop_reason"] == "ABORTED"
    assert outcome.stop_reason == "ABORTED"
