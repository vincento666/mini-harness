"""seam ②：host 的 approval 门——只等 HTTP 回程，不读 stdin，超时是 UNAVAILABLE。

seam ⑥ 判的是「一次写怎么经 HTTP 被批准/拒绝」；这里判门的两个不可见分支：
等不到人时塌成什么、以及它绝不碰 stdin。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from mini_harness.session.assembly import AssemblyRequest
from mini_harness.session.host import HostApprovalGate, HostSession, HostState, create_session


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
