"""seam ⑥：`minihns host` 上的委派视图（M12 design D7）。

子会话有自己的日志与列表条目；父会话的事件流只转发父自己的记录。
"""

from __future__ import annotations

import json
import time
from collections.abc import Iterable
from pathlib import Path

import httpx

from test_cli_host import (
    HOST_TOKEN,
    _create_session,
    _free_port,
    _headers,
    _next_frame,
    _session_state,
    _start_host,
    _stop,
    _wait_for_health,
    _wait_until_idle,
)


def _delegating_fixture(tmp_path: Path) -> Path:
    """父回合声明一个 subagent；子会话说一句带标记的话；父再收尾。"""
    fixture = tmp_path / "delegating.json"
    fixture.write_text(
        json.dumps(
            [
                {
                    "content": "派一个子代理",
                    "finish_reason": "tool_calls",
                    "tool_calls": [
                        {"id": "c1", "name": "subagent", "arguments": {"task": "子任务"}}
                    ],
                },
                {"content": "子会话的答案", "finish_reason": "stop"},
                {"content": "父结束", "finish_reason": "stop"},
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return fixture


def _frames_until(lines: Iterable[str], event: str) -> list[dict[str, str]]:
    frames: list[dict[str, str]] = []
    while True:
        frame = _next_frame(lines)
        frames.append(frame)
        if frame["event"] == event:
            return frames


def test_session_views_carry_parent_and_depth(tmp_path: Path) -> None:
    session_dir = tmp_path / "sessions"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    fixture = _delegating_fixture(tmp_path)
    port = _free_port()
    process = _start_host(tmp_path, port, HOST_TOKEN, "--session-dir", str(session_dir))
    try:
        _wait_for_health(port)
        with httpx.Client(
            trust_env=False, base_url=f"http://127.0.0.1:{port}", timeout=10.0
        ) as client:
            root = _create_session(client, workspace, fixture)
            response = client.post(
                f"/sessions/{root}/messages", headers=_headers(), json={"content": "任务"}
            )
            assert response.status_code == 202, response.text
            _wait_until_idle(client, root)

            listed = client.get("/sessions", headers=_headers()).json()["sessions"]
            child = next(item for item in listed if item.get("parent_session_id") == root)
            assert child["depth"] == 1
            assert child["status"] == "ended"

            detail = client.get(f"/sessions/{child['session_id']}", headers=_headers())
            assert detail.status_code == 200, detail.text
            assert detail.json()["parent_session_id"] == root
            assert detail.json()["depth"] == 1

            root_view = _session_state(client, root)
            assert root_view["parent_session_id"] is None
            assert root_view["depth"] == 0
    finally:
        _stop(process)


def test_the_parent_stream_does_not_forward_child_events(tmp_path: Path) -> None:
    session_dir = tmp_path / "sessions"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    fixture = _delegating_fixture(tmp_path)
    port = _free_port()
    process = _start_host(tmp_path, port, HOST_TOKEN, "--session-dir", str(session_dir))
    try:
        _wait_for_health(port)
        with httpx.Client(
            trust_env=False, base_url=f"http://127.0.0.1:{port}", timeout=10.0
        ) as client:
            root = _create_session(client, workspace, fixture)
            with client.stream("GET", f"/sessions/{root}/events", headers=_headers()) as response:
                lines = response.iter_lines()
                first = _next_frame(lines)
                assert first["event"] == "session/start"
                client.post(
                    f"/sessions/{root}/messages", headers=_headers(), json={"content": "任务"}
                )
                frames = [first, *_frames_until(lines, "segment/end")]

            listed = client.get("/sessions", headers=_headers()).json()["sessions"]
            child = next(item for item in listed if item.get("parent_session_id") == root)

        streamed = "\n".join(frame["data"] for frame in frames)
        # 父流里只有父自己的记录：子会话的 id 与它的 session/start 一次都不出现。
        assert child["session_id"] not in streamed
        starts = [
            json.loads(frame["data"])["payload"]
            for frame in frames
            if frame["event"] == "session/start"
        ]
        assert [payload["entry"] for payload in starts] == ["host"]
    finally:
        _stop(process)


def test_a_cancelled_child_is_still_listed(tmp_path: Path) -> None:
    """被取消的子会话也登记进列表：它的日志是完整的 ABORTED 收尾（design D7）。"""
    session_dir = tmp_path / "sessions"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    fixture = tmp_path / "slow-child.json"
    fixture.write_text(
        json.dumps(
            [
                {
                    "content": "派一个慢的",
                    "finish_reason": "tool_calls",
                    "tool_calls": [
                        {"id": "c1", "name": "subagent", "arguments": {"task": "慢任务"}}
                    ],
                },
                {
                    "content": "先跑一条慢命令",
                    "finish_reason": "tool_calls",
                    "tool_calls": [
                        {
                            "id": "c2",
                            "name": "bash",
                            "arguments": {"command": "sleep 5", "timeout_seconds": 5},
                        }
                    ],
                },
                {"content": "父结束", "finish_reason": "stop"},
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    port = _free_port()
    process = _start_host(
        tmp_path, port, HOST_TOKEN, "--session-dir", str(session_dir), "--allow-auto-approval"
    )
    try:
        _wait_for_health(port)
        with httpx.Client(
            trust_env=False, base_url=f"http://127.0.0.1:{port}", timeout=10.0
        ) as client:
            root = _create_session(client, workspace, fixture, approval="auto")
            client.post(f"/sessions/{root}/messages", headers=_headers(), json={"content": "任务"})

            # 子会话的日志一建出来就取消父段：取消落在子代理还在跑的时候。
            child_id: str | None = None
            deadline = time.monotonic() + 15.0
            while time.monotonic() < deadline:
                others = [path.stem for path in session_dir.glob("*.jsonl") if path.stem != root]
                if others:
                    child_id = others[0]
                    break
                time.sleep(0.05)
            assert child_id is not None, "子会话没有建出日志"

            response = client.post(f"/sessions/{root}/cancel", headers=_headers())
            assert response.status_code == 202, response.text
            _wait_until_idle(client, root)

            listed = client.get("/sessions", headers=_headers()).json()["sessions"]
            child = next(item for item in listed if item["session_id"] == child_id)
        assert child["parent_session_id"] == root
        assert child["status"] == "ended"
        records = [
            json.loads(line)
            for line in (session_dir / f"{child_id}.jsonl").read_text(encoding="utf-8").splitlines()
        ]
        assert records[-1]["type"] == "session/end"
        assert records[-1]["payload"]["stop_reason"] == "ABORTED"
    finally:
        _stop(process)
