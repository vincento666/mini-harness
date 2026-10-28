"""seam ②：host 的 approval 门——只等 HTTP 回程，不读 stdin，超时是 UNAVAILABLE。

seam ⑥ 判的是「一次写怎么经 HTTP 被批准/拒绝」；这里判门的两个不可见分支：
等不到人时塌成什么、以及它绝不碰 stdin。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from mini_harness.session.assembly import AssemblyRequest
from mini_harness.session.host import (
    DELTA_QUEUE_MAX,
    HostApprovalGate,
    HostSession,
    HostState,
    create_session,
)


def _handle(tmp_path: Path) -> HostSession:
    fixture = tmp_path / "turns.json"
    fixture.write_text(
        json.dumps([{"content": "好", "finish_reason": "stop"}], ensure_ascii=False),
        encoding="utf-8",
    )
    state = HostState(
        defaults=AssemblyRequest(
            provider="mock",
            fixture=str(fixture),
            session_dir=str(tmp_path / "sessions"),
        )
    )
    handle = create_session(state, state.defaults, {})
    assert isinstance(handle, HostSession)
    return handle


async def test_host_session_broadcasts_deltas_to_subscribers(tmp_path: Path) -> None:
    handle = _handle(tmp_path)
    # 没有订阅者时 publish 也不该影响回合。
    await handle.publish_delta("t0", "先")

    queue = handle.subscribe_deltas()
    await handle.publish_delta("t1", "你")
    await handle.publish_delta("t1", "好")

    assert queue.get_nowait() == {"turn_id": "t1", "index": 0, "text": "你"}
    assert queue.get_nowait() == {"turn_id": "t1", "index": 1, "text": "好"}
    assert queue.empty()

    handle.unsubscribe_deltas(queue)
    await handle.publish_delta("t1", "退订之后")
    assert queue.empty()


async def test_a_slow_delta_subscriber_drops_old_deltas(tmp_path: Path) -> None:
    handle = _handle(tmp_path)
    queue = handle.subscribe_deltas()

    for number in range(DELTA_QUEUE_MAX + 5):
        await handle.publish_delta("t1", str(number))

    assert queue.qsize() == DELTA_QUEUE_MAX
    assert queue.get_nowait()["index"] == 5


async def test_an_expired_approval_is_unavailable(tmp_path: Path) -> None:
    handle = _handle(tmp_path)
    gate = HostApprovalGate(handle, timeout=0.1)

    decision = await gate.request(tool_call_id="call-1", tool_name="write", detail="notes.md")

    assert decision == "UNAVAILABLE"
    assert handle.approvals == {}


class _Trap:
    """可读的 tty 替身：谁读它谁就被记下来。"""

    def __init__(self) -> None:
        self.reads = 0

    def isatty(self) -> bool:
        return True

    def readline(self) -> str:
        self.reads += 1
        return "y\n"


async def test_the_host_gate_never_reads_stdin(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    handle = _handle(tmp_path)
    trap = _Trap()
    monkeypatch.setattr("sys.stdin", trap)
    gate = HostApprovalGate(handle, timeout=0.1)

    decision = await gate.request(tool_call_id="call-1", tool_name="write", detail="notes.md")

    assert decision == "UNAVAILABLE"
    assert trap.reads == 0
