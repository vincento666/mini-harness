"""seam ⑥：`minihns host --http` 的黑盒判据（H1）。

这些判据跑真实子进程 + 真 HTTP：token 只从环境变量读，端口取空闲端口，进程在 finally 里收掉。
"""

from __future__ import annotations

import json
import os
import re
import signal
import socket
import subprocess
import sys
import time
from collections.abc import Iterable
from pathlib import Path

import httpx
import pytest

from cli_blackbox import _cli, _cli_process

HOST_TOKEN = "h1-test-token-" + "x" * 32


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _host_env(token: str) -> dict[str, str]:
    env = dict(os.environ)
    env["MINIHNS_HOST_TOKEN"] = token
    return env


def _start_host(
    cwd: Path, port: int, token: str = HOST_TOKEN, *extra: str
) -> subprocess.Popen[str]:
    # Windows 上要新进程组才能把 Ctrl-Break 只发给 host；POSIX 用 SIGTERM。
    creationflags = subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0
    return _cli_process(
        "host",
        "--http",
        "--port",
        str(port),
        *extra,
        cwd=cwd,
        env=_host_env(token),
        creationflags=creationflags,
    )


def _wait_for_health(port: int, timeout: float = 25.0) -> httpx.Response:
    deadline = time.monotonic() + timeout
    # `trust_env=False`：本机的代理环境变量不该决定测试怎么连 loopback。
    with httpx.Client(trust_env=False, timeout=0.5) as client:
        while time.monotonic() < deadline:
            try:
                return client.get(f"http://127.0.0.1:{port}/health")
            except httpx.HTTPError:
                time.sleep(0.05)
    pytest.fail("host 没有在超时内响应 /health")


def _stop(process: subprocess.Popen[str]) -> int:
    """优雅收掉 host：Windows 发 Ctrl-Break（进程组已建好），POSIX 发 SIGTERM。

    硬杀会让 `coverage run` 来不及写 partial，host 那一半就看不见了；收尾必须走信号。
    """
    if process.poll() is not None:
        return process.wait(timeout=10)
    if sys.platform == "win32":
        process.send_signal(signal.CTRL_BREAK_EVENT)
    else:
        process.terminate()
    try:
        return process.wait(timeout=15)
    except subprocess.TimeoutExpired:
        process.kill()
        return process.wait(timeout=10)


def _headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {HOST_TOKEN}"}


def _mock_fixture(tmp_path: Path, name: str = "turns.json") -> Path:
    fixture = tmp_path / name
    fixture.write_text(
        json.dumps([{"content": "好", "finish_reason": "stop"}], ensure_ascii=False),
        encoding="utf-8",
    )
    return fixture


def _create_session(
    client: httpx.Client, workspace: Path, fixture: Path, **overrides: object
) -> str:
    response = client.post(
        "/sessions",
        headers=_headers(),
        json={
            "workspace": str(workspace),
            "provider": "mock",
            "fixture": str(fixture),
            **overrides,
        },
    )
    assert response.status_code == 201, response.text
    return str(response.json()["session_id"])


def _session_state(client: httpx.Client, session_id: str) -> dict[str, object]:
    response = client.get(f"/sessions/{session_id}", headers=_headers())
    assert response.status_code == 200, response.text
    return dict(response.json())


def _wait_until_idle(client: httpx.Client, session_id: str, timeout: float = 25.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if _session_state(client, session_id)["status"] == "idle":
            return
        time.sleep(0.05)
    pytest.fail("会话没有在超时内回到 idle")


def _wait_for_log(log: Path, marker: str, timeout: float = 25.0) -> str:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if log.is_file():
            text = log.read_text(encoding="utf-8")
            if marker in text:
                return text
        time.sleep(0.05)
    pytest.fail(f"日志里没有等到 {marker}")


def _slow_fixture(workspace: Path, tmp_path: Path) -> Path:
    (workspace / "slow.py").write_text("import time\n\ntime.sleep(1.0)\n", encoding="utf-8")
    fixture = tmp_path / "slow.json"
    fixture.write_text(
        json.dumps(
            [
                {
                    "content": "跑一条慢命令",
                    "finish_reason": "tool_calls",
                    "tool_calls": [
                        {"id": "c1", "name": "bash", "arguments": {"command": "python slow.py"}}
                    ],
                },
                {"content": "第一段完", "finish_reason": "stop"},
                {"content": "第二段完", "finish_reason": "stop"},
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return fixture


def test_a_full_queue_is_rejected(tmp_path: Path) -> None:
    session_dir = tmp_path / "sessions"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    fixture = _slow_fixture(workspace, tmp_path)
    port = _free_port()
    process = _start_host(
        tmp_path,
        port,
        HOST_TOKEN,
        "--session-dir",
        str(session_dir),
        "--allow-auto-approval",
    )
    try:
        _wait_for_health(port)
        with httpx.Client(
            trust_env=False, base_url=f"http://127.0.0.1:{port}", timeout=10.0
        ) as client:
            session_id = _create_session(
                client, workspace, fixture, provider="mock", approval="auto"
            )
            client.post(
                f"/sessions/{session_id}/messages",
                headers=_headers(),
                json={"content": "第一句"},
            )
            log = session_dir / f"{session_id}.jsonl"
            _wait_for_log(log, '"tool/call"')
            assert (
                client.post(
                    f"/sessions/{session_id}/messages",
                    headers=_headers(),
                    json={"content": "第二句"},
                ).json()["queued"]
                is True
            )
            third = client.post(
                f"/sessions/{session_id}/messages",
                headers=_headers(),
                json={"content": "第三句"},
            )
            assert third.status_code == 429
            assert third.json()["error"]["code"] == "SESSION_BUSY"
            _wait_until_idle(client, session_id)

        records = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
        messages = [
            record["payload"]["content"] for record in records if record["type"] == "user/message"
        ]
        assert messages == ["第一句", "第二句"]
    finally:
        _stop(process)


def test_an_empty_message_is_rejected(tmp_path: Path) -> None:
    session_dir = tmp_path / "sessions"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    fixture = _mock_fixture(tmp_path)
    port = _free_port()
    process = _start_host(tmp_path, port, HOST_TOKEN, "--session-dir", str(session_dir))
    try:
        _wait_for_health(port)
        with httpx.Client(
            trust_env=False, base_url=f"http://127.0.0.1:{port}", timeout=5.0
        ) as client:
            session_id = _create_session(client, workspace, fixture)
            for body in ({"content": ""}, {"content": "   "}, {}):
                response = client.post(
                    f"/sessions/{session_id}/messages", headers=_headers(), json=body
                )
                assert response.status_code == 400
                assert response.json()["error"]["code"] == "INVALID_ARGUMENT"
            state = _session_state(client, session_id)

        assert state["status"] == "idle"
        records = [
            json.loads(line)
            for line in (session_dir / f"{session_id}.jsonl")
            .read_text(encoding="utf-8")
            .splitlines()
        ]
        assert not any(record["type"] == "user/message" for record in records)
    finally:
        _stop(process)


def _read_frames(response: httpx.Response, count: int) -> list[dict[str, str]]:
    frames: list[dict[str, str]] = []
    fields: dict[str, str] = {}
    for line in response.iter_lines():
        if line == "":
            if fields:
                frames.append(fields)
                fields = {}
                if len(frames) >= count:
                    break
        elif line.startswith("id: "):
            fields["id"] = line[len("id: ") :]
        elif line.startswith("event: "):
            fields["event"] = line[len("event: ") :]
        elif line.startswith("data: "):
            fields["data"] = line[len("data: ") :]
    return frames


def test_cancel_while_waiting_for_approval_is_unavailable(tmp_path: Path) -> None:
    session_dir = tmp_path / "sessions"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    fixture = _write_fixture(tmp_path)
    port = _free_port()
    process = _start_host(tmp_path, port, HOST_TOKEN, "--session-dir", str(session_dir))
    try:
        _wait_for_health(port)
        with httpx.Client(
            trust_env=False, base_url=f"http://127.0.0.1:{port}", timeout=10.0
        ) as client:
            session_id = _create_session(client, workspace, fixture)
            client.post(
                f"/sessions/{session_id}/messages",
                headers=_headers(),
                json={"content": "写"},
            )
            log = session_dir / f"{session_id}.jsonl"
            _wait_for_approval(log)
            cancelled = client.post(f"/sessions/{session_id}/cancel", headers=_headers())
            assert cancelled.status_code == 202
            _wait_until_idle(client, session_id)

        records = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
        responses = [
            record["payload"] for record in records if record["type"] == "approval/response"
        ]
        ends = [record["payload"] for record in records if record["type"] == "segment/end"]
        assert responses[-1]["decision"] == "UNAVAILABLE"
        assert ends[-1]["stop_reason"] == "ABORTED"
        assert not (workspace / "notes.md").exists()
    finally:
        _stop(process)


def test_the_event_stream_carries_cors_headers(tmp_path: Path) -> None:
    session_dir = tmp_path / "sessions"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    fixture = _mock_fixture(tmp_path)
    port = _free_port()
    process = _start_host(tmp_path, port, HOST_TOKEN, "--session-dir", str(session_dir))
    try:
        _wait_for_health(port)
        with httpx.Client(
            trust_env=False, base_url=f"http://127.0.0.1:{port}", timeout=10.0
        ) as client:
            session_id = _create_session(client, workspace, fixture)
            with client.stream(
                "GET",
                f"/sessions/{session_id}/events",
                headers={**_headers(), "Origin": "null"},
            ) as response:
                assert response.status_code == 200
                assert response.headers["Access-Control-Allow-Origin"] == "null"
                _next_frame(response.iter_lines())
    finally:
        _stop(process)


def test_host_frames_equal_the_log(tmp_path: Path) -> None:
    session_dir = tmp_path / "sessions"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    fixture = _mock_fixture(tmp_path)
    port = _free_port()
    process = _start_host(tmp_path, port, HOST_TOKEN, "--session-dir", str(session_dir))
    try:
        _wait_for_health(port)
        with httpx.Client(
            trust_env=False, base_url=f"http://127.0.0.1:{port}", timeout=10.0
        ) as client:
            session_id = _create_session(client, workspace, fixture)
            client.post(
                f"/sessions/{session_id}/messages",
                headers=_headers(),
                json={"content": "任务"},
            )
            _wait_until_idle(client, session_id)
            log = session_dir / f"{session_id}.jsonl"
            records = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
            with client.stream(
                "GET", f"/sessions/{session_id}/events", headers=_headers()
            ) as response:
                assert response.status_code == 200
                frames = _read_frames(response, len(records))

        assert len(frames) == len(records)
        for frame, record in zip(frames, records, strict=True):
            assert frame["event"] == record["type"]
            assert frame["id"] == str(record["seq"])
            assert json.loads(frame["data"]) == record
    finally:
        _stop(process)


def test_a_cursor_resumes_without_gaps(tmp_path: Path) -> None:
    session_dir = tmp_path / "sessions"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    fixture = _mock_fixture(tmp_path)
    port = _free_port()
    process = _start_host(tmp_path, port, HOST_TOKEN, "--session-dir", str(session_dir))
    try:
        _wait_for_health(port)
        with httpx.Client(
            trust_env=False, base_url=f"http://127.0.0.1:{port}", timeout=10.0
        ) as client:
            session_id = _create_session(client, workspace, fixture)
            client.post(
                f"/sessions/{session_id}/messages",
                headers=_headers(),
                json={"content": "任务"},
            )
            _wait_until_idle(client, session_id)

            for path, headers in (
                (f"/sessions/{session_id}/events?from=3", _headers()),
                (
                    f"/sessions/{session_id}/events",
                    {**_headers(), "Last-Event-ID": "3"},
                ),
            ):
                with client.stream("GET", path, headers=headers) as response:
                    frames = _read_frames(response, 1)
                assert frames[0]["id"] == "4"

            with client.stream(
                "GET", f"/sessions/{session_id}/events?from=0", headers=_headers()
            ) as response:
                frames = _read_frames(response, 1)
            assert frames[0]["id"] == "1"

            negative = client.get(f"/sessions/{session_id}/events?from=-1", headers=_headers())
            not_a_number = client.get(f"/sessions/{session_id}/events?from=abc", headers=_headers())
            still_there = _session_state(client, session_id)

        assert negative.status_code == 400
        assert negative.json()["error"]["code"] == "INVALID_ARGUMENT"
        assert not_a_number.status_code == 400
        assert still_there["status"] == "idle"
    finally:
        _stop(process)


def _next_frame(lines: Iterable[str]) -> dict[str, str]:
    fields: dict[str, str] = {}
    for line in lines:
        text = str(line)
        if text == "":
            if fields:
                return fields
        elif text.startswith("id: "):
            fields["id"] = text[len("id: ") :]
        elif text.startswith("event: "):
            fields["event"] = text[len("event: ") :]
        elif text.startswith("data: "):
            fields["data"] = text[len("data: ") :]
    raise AssertionError("事件流提前结束")


def test_snapshot_precedes_only_new_frames(tmp_path: Path) -> None:
    session_dir = tmp_path / "sessions"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    fixture = tmp_path / "three.json"
    fixture.write_text(
        json.dumps(
            [
                {"content": "一", "finish_reason": "stop"},
                {"content": "二", "finish_reason": "stop"},
                {"content": "三", "finish_reason": "stop"},
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    port = _free_port()
    process = _start_host(tmp_path, port, HOST_TOKEN, "--session-dir", str(session_dir))
    try:
        _wait_for_health(port)
        with httpx.Client(
            trust_env=False, base_url=f"http://127.0.0.1:{port}", timeout=10.0
        ) as client:
            session_id = _create_session(client, workspace, fixture)
            for content in ("第一句", "第二句"):
                client.post(
                    f"/sessions/{session_id}/messages",
                    headers=_headers(),
                    json={"content": content},
                )
                _wait_until_idle(client, session_id)
            log = session_dir / f"{session_id}.jsonl"
            records = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
            expected_last = records[-1]["seq"]

            with client.stream(
                "GET",
                f"/sessions/{session_id}/events?snapshot=1",
                headers=_headers(),
            ) as response:
                lines = response.iter_lines()
                first = _next_frame(lines)
                assert first["event"] == "snapshot"
                snapshot = json.loads(first["data"])
                assert snapshot["session_id"] == session_id
                assert snapshot["last_seq"] == expected_last
                assert isinstance(snapshot["messages"], list)

                client.post(
                    f"/sessions/{session_id}/messages",
                    headers=_headers(),
                    json={"content": "第三句"},
                )
                new_frame = _next_frame(lines)

        assert int(new_frame["id"]) == expected_last + 1
        assert json.loads(new_frame["data"])["type"] == "segment/start"
    finally:
        _stop(process)


def _normalized_log(path: Path) -> list[dict[str, object]]:
    records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    return [
        {key: value for key, value in record.items() if key not in {"ts", "session_id"}}
        for record in records
    ]


def test_the_event_stream_mixes_durable_and_delta_frames(tmp_path: Path) -> None:
    session_dir = tmp_path / "sessions"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    fixture = tmp_path / "delta.json"
    fixture.write_text(
        json.dumps(
            [{"content": "你好", "deltas": ["你", "好"], "finish_reason": "stop"}],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    port = _free_port()
    process = _start_host(tmp_path, port, HOST_TOKEN, "--session-dir", str(session_dir))
    try:
        _wait_for_health(port)
        with httpx.Client(
            trust_env=False, base_url=f"http://127.0.0.1:{port}", timeout=10.0
        ) as client:
            session_id = _create_session(client, workspace, fixture)
            with client.stream(
                "GET", f"/sessions/{session_id}/events", headers=_headers()
            ) as response:
                lines = response.iter_lines()
                first = _next_frame(lines)
                assert first["event"] == "session/start"
                client.post(
                    f"/sessions/{session_id}/messages",
                    headers=_headers(),
                    json={"content": "任务"},
                )
                frames: list[dict[str, str]] = []
                while True:
                    frame = _next_frame(lines)
                    frames.append(frame)
                    if frame["event"] == "model/response":
                        break

        events = [frame["event"] for frame in frames]
        assert "model/request" in events
        assert events.count("model/delta") == 2
        assert events.index("model/request") < events.index("model/delta")
        deltas = [json.loads(frame["data"]) for frame in frames if frame["event"] == "model/delta"]
        assert all("id" not in frame for frame in frames if frame["event"] == "model/delta")
        assert [delta["text"] for delta in deltas] == ["你", "好"]
        response_payload = json.loads(
            next(frame["data"] for frame in frames if frame["event"] == "model/response")
        )
        assert response_payload["payload"]["content"] == "".join(delta["text"] for delta in deltas)
        log = session_dir / f"{session_id}.jsonl"
        assert "model/delta" not in log.read_text(encoding="utf-8")
    finally:
        _stop(process)


def test_reasoning_delta_is_a_separate_ephemeral_frame(tmp_path: Path) -> None:
    session_dir = tmp_path / "sessions"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    fixture = tmp_path / "reasoning.json"
    fixture.write_text(
        json.dumps(
            [
                {
                    "content": "答案",
                    "deltas": ["答", "案"],
                    "reasoning_deltas": ["想", "一下"],
                    "finish_reason": "stop",
                }
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    port = _free_port()
    process = _start_host(tmp_path, port, HOST_TOKEN, "--session-dir", str(session_dir))
    try:
        _wait_for_health(port)
        with httpx.Client(
            trust_env=False, base_url=f"http://127.0.0.1:{port}", timeout=10.0
        ) as client:
            session_id = _create_session(client, workspace, fixture)
            with client.stream(
                "GET", f"/sessions/{session_id}/events", headers=_headers()
            ) as response:
                lines = response.iter_lines()
                assert _next_frame(lines)["event"] == "session/start"
                client.post(
                    f"/sessions/{session_id}/messages",
                    headers=_headers(),
                    json={"content": "任务"},
                )
                frames = []
                while True:
                    frame = _next_frame(lines)
                    frames.append(frame)
                    if frame["event"] == "model/response":
                        break

        events = [frame["event"] for frame in frames]
        assert events.count("reasoning/delta") == 2
        assert events.count("model/delta") == 2
        assert events.index("reasoning/delta") < events.index("model/delta")
        reasoning = [
            json.loads(frame["data"]) for frame in frames if frame["event"] == "reasoning/delta"
        ]
        assert [item["text"] for item in reasoning] == ["想", "一下"]
        assert all("id" not in frame for frame in frames if frame["event"] == "reasoning/delta")
        log = session_dir / f"{session_id}.jsonl"
        assert "reasoning/delta" not in log.read_text(encoding="utf-8")
    finally:
        _stop(process)


def test_a_delta_does_not_move_the_cursor(tmp_path: Path) -> None:
    session_dir = tmp_path / "sessions"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    fixture = tmp_path / "delta-cursor.json"
    fixture.write_text(
        json.dumps(
            [{"content": "你好", "deltas": ["你", "好"], "finish_reason": "stop"}],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    port = _free_port()
    process = _start_host(tmp_path, port, HOST_TOKEN, "--session-dir", str(session_dir))
    try:
        _wait_for_health(port)
        with httpx.Client(
            trust_env=False, base_url=f"http://127.0.0.1:{port}", timeout=10.0
        ) as client:
            session_id = _create_session(client, workspace, fixture)
            client.post(
                f"/sessions/{session_id}/messages",
                headers=_headers(),
                json={"content": "任务"},
            )
            _wait_until_idle(client, session_id)
            log = session_dir / f"{session_id}.jsonl"
            records = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
            last_seq = records[-1]["seq"]

            with client.stream(
                "GET",
                f"/sessions/{session_id}/events?snapshot=1",
                headers=_headers(),
            ) as response:
                snapshot = json.loads(_next_frame(response.iter_lines())["data"])

        assert snapshot["last_seq"] == last_seq
        assert snapshot["messages"][-1]["content"] == "你好"
        assert "model/delta" not in log.read_text(encoding="utf-8")
    finally:
        _stop(process)


def test_reconnect_does_not_replay_lost_deltas(tmp_path: Path) -> None:
    session_dir = tmp_path / "sessions"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    fixture = tmp_path / "delta-reconnect.json"
    fixture.write_text(
        json.dumps(
            [{"content": "你好", "deltas": ["你", "好"], "finish_reason": "stop"}],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    port = _free_port()
    process = _start_host(tmp_path, port, HOST_TOKEN, "--session-dir", str(session_dir))
    try:
        _wait_for_health(port)
        with httpx.Client(
            trust_env=False, base_url=f"http://127.0.0.1:{port}", timeout=10.0
        ) as client:
            session_id = _create_session(client, workspace, fixture)
            with client.stream(
                "GET", f"/sessions/{session_id}/events", headers=_headers()
            ) as response:
                lines = response.iter_lines()
                assert _next_frame(lines)["event"] == "session/start"
                client.post(
                    f"/sessions/{session_id}/messages",
                    headers=_headers(),
                    json={"content": "任务"},
                )
                while _next_frame(lines)["event"] != "model/delta":
                    pass
            _wait_until_idle(client, session_id)

            with client.stream(
                "GET",
                f"/sessions/{session_id}/events?snapshot=1",
                headers=_headers(),
            ) as response:
                snapshot = json.loads(_next_frame(response.iter_lines())["data"])

            log = session_dir / f"{session_id}.jsonl"
            text = log.read_text(encoding="utf-8")
        assert snapshot["messages"][-1]["content"] == "你好"
        assert "model/delta" not in text
        assert text.count('"type": "model/response"') == 1
    finally:
        _stop(process)


def test_a_disconnected_delta_reader_does_not_stop_the_segment(tmp_path: Path) -> None:
    session_dir = tmp_path / "sessions"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    fixture = tmp_path / "delta-disconnect.json"
    fixture.write_text(
        json.dumps(
            [{"content": "你好", "deltas": ["你", "好"], "finish_reason": "stop"}],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    port = _free_port()
    process = _start_host(tmp_path, port, HOST_TOKEN, "--session-dir", str(session_dir))
    try:
        _wait_for_health(port)
        with httpx.Client(
            trust_env=False, base_url=f"http://127.0.0.1:{port}", timeout=10.0
        ) as client:
            baseline = _create_session(client, workspace, fixture)
            client.post(
                f"/sessions/{baseline}/messages",
                headers=_headers(),
                json={"content": "任务"},
            )
            _wait_until_idle(client, baseline)

            watched = _create_session(client, workspace, fixture)
            with client.stream(
                "GET", f"/sessions/{watched}/events", headers=_headers()
            ) as response:
                _next_frame(response.iter_lines())
                client.post(
                    f"/sessions/{watched}/messages",
                    headers=_headers(),
                    json={"content": "任务"},
                )
            _wait_until_idle(client, watched)

        assert _normalized_log(session_dir / f"{watched}.jsonl") == _normalized_log(
            session_dir / f"{baseline}.jsonl"
        )
    finally:
        _stop(process)


def test_a_disconnect_does_not_change_the_session(tmp_path: Path) -> None:
    session_dir = tmp_path / "sessions"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    fixture = _mock_fixture(tmp_path)
    port = _free_port()
    process = _start_host(tmp_path, port, HOST_TOKEN, "--session-dir", str(session_dir))
    try:
        _wait_for_health(port)
        with httpx.Client(
            trust_env=False, base_url=f"http://127.0.0.1:{port}", timeout=10.0
        ) as client:
            baseline = _create_session(client, workspace, fixture)
            client.post(
                f"/sessions/{baseline}/messages",
                headers=_headers(),
                json={"content": "任务"},
            )
            _wait_until_idle(client, baseline)

            watched = _create_session(client, workspace, fixture)
            with client.stream(
                "GET", f"/sessions/{watched}/events", headers=_headers()
            ) as response:
                lines = response.iter_lines()
                _next_frame(lines)
                client.post(
                    f"/sessions/{watched}/messages",
                    headers=_headers(),
                    json={"content": "任务"},
                )
                _next_frame(lines)
            _wait_until_idle(client, watched)
            state = _session_state(client, watched)

        assert state["status"] == "idle"
        baseline_log = session_dir / f"{baseline}.jsonl"
        watched_log = session_dir / f"{watched}.jsonl"
        assert _normalized_log(watched_log) == _normalized_log(baseline_log)
    finally:
        _stop(process)


def test_host_outlives_a_session(tmp_path: Path) -> None:
    session_dir = tmp_path / "sessions"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    fixture = _mock_fixture(tmp_path)
    port = _free_port()
    process = _start_host(tmp_path, port, HOST_TOKEN, "--session-dir", str(session_dir))
    try:
        _wait_for_health(port)
        with httpx.Client(
            trust_env=False, base_url=f"http://127.0.0.1:{port}", timeout=10.0
        ) as client:
            session_id = _create_session(client, workspace, fixture)
            client.post(
                f"/sessions/{session_id}/messages",
                headers=_headers(),
                json={"content": "任务"},
            )
            _wait_until_idle(client, session_id)
            health = client.get("/health")
            listed = client.get("/sessions", headers=_headers())

        assert health.status_code == 200
        assert health.json()["sessions"] == 1
        assert [item["session_id"] for item in listed.json()["sessions"]] == [session_id]
    finally:
        _stop(process)


@pytest.mark.skipif(
    sys.platform == "win32", reason="SIGINT 子进程判据在 Linux runner 上跑（与 M7 一致）"
)
def test_sigint_cancels_all_segments_and_writes_session_end(tmp_path: Path) -> None:
    session_dir = tmp_path / "sessions"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    fixture = _slow_fixture(workspace, tmp_path)
    port = _free_port()
    process = _start_host(
        tmp_path,
        port,
        HOST_TOKEN,
        "--session-dir",
        str(session_dir),
        "--allow-auto-approval",
    )
    try:
        _wait_for_health(port)
        with httpx.Client(
            trust_env=False, base_url=f"http://127.0.0.1:{port}", timeout=10.0
        ) as client:
            session_id = _create_session(
                client, workspace, fixture, provider="mock", approval="auto"
            )
            client.post(
                f"/sessions/{session_id}/messages",
                headers=_headers(),
                json={"content": "任务"},
            )
            log = session_dir / f"{session_id}.jsonl"
            _wait_for_log(log, '"tool/call"')
            process.send_signal(signal.SIGINT)
            code = process.wait(timeout=20)

        assert code == 0
        records = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
        types = [record["type"] for record in records]
        ends = [record["payload"] for record in records if record["type"] == "segment/end"]
        assert "error/abort" in types
        assert ends[-1]["stop_reason"] == "ABORTED"
        assert types[-1] == "session/end"
    finally:
        _stop(process)


def test_shutdown_leaves_no_orphan_session(tmp_path: Path) -> None:
    session_dir = tmp_path / "sessions"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    fixture = _slow_fixture(workspace, tmp_path)
    port = _free_port()
    process = _start_host(
        tmp_path,
        port,
        HOST_TOKEN,
        "--session-dir",
        str(session_dir),
        "--allow-auto-approval",
    )
    try:
        _wait_for_health(port)
        with httpx.Client(
            trust_env=False, base_url=f"http://127.0.0.1:{port}", timeout=10.0
        ) as client:
            session_ids = [
                _create_session(client, workspace, fixture, provider="mock", approval="auto")
                for _ in range(2)
            ]
            for session_id in session_ids:
                client.post(
                    f"/sessions/{session_id}/messages",
                    headers=_headers(),
                    json={"content": "任务"},
                )
            for session_id in session_ids:
                _wait_for_log(session_dir / f"{session_id}.jsonl", '"tool/call"')
            code = _stop(process)

        assert code == 0
        for session_id in session_ids:
            log = session_dir / f"{session_id}.jsonl"
            records = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
            assert records[-1]["type"] == "session/end"
            assert records[-1]["payload"]["stop_reason"] == "MODEL_COMPLETED"
    finally:
        _stop(process)


def test_every_host_error_uses_the_envelope(tmp_path: Path) -> None:
    session_dir = tmp_path / "sessions"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    fixture = _slow_fixture(workspace, tmp_path)
    port = _free_port()
    process = _start_host(
        tmp_path,
        port,
        HOST_TOKEN,
        "--session-dir",
        str(session_dir),
        "--allow-auto-approval",
    )
    try:
        _wait_for_health(port)
        with httpx.Client(
            trust_env=False, base_url=f"http://127.0.0.1:{port}", timeout=10.0
        ) as client:
            session_id = _create_session(
                client, workspace, fixture, provider="mock", approval="auto"
            )
            client.post(
                f"/sessions/{session_id}/messages",
                headers=_headers(),
                json={"content": "第一句"},
            )
            _wait_for_log(session_dir / f"{session_id}.jsonl", '"tool/call"')
            client.post(
                f"/sessions/{session_id}/messages",
                headers=_headers(),
                json={"content": "第二句"},
            )
            third = client.post(
                f"/sessions/{session_id}/messages",
                headers=_headers(),
                json={"content": "第三句"},
            )
            running_delete = client.delete(f"/sessions/{session_id}", headers=_headers())
            unknown = client.get("/sessions/" + "0" * 32, headers=_headers())

            responses = {
                401: client.get("/sessions"),
                403: client.get(
                    "/sessions",
                    headers={**_headers(), "Origin": "https://example.com"},
                ),
                404: unknown,
                409: running_delete,
                429: third,
            }
            _wait_until_idle(client, session_id)

        expected_codes = {
            401: "UNAUTHORIZED",
            403: "FORBIDDEN",
            404: "SESSION_NOT_FOUND",
            409: "SESSION_BUSY",
            429: "SESSION_BUSY",
        }
        for status, response in responses.items():
            assert response.status_code == status
            envelope = response.json()
            assert envelope["error"]["code"] == expected_codes[status]
            detail = str(envelope["error"]["detail"])
            assert HOST_TOKEN[:8] not in detail
            assert "Traceback" not in detail
    finally:
        _stop(process)


def test_the_token_never_reaches_the_log(tmp_path: Path) -> None:
    session_dir = tmp_path / "sessions"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    fixture = _write_fixture(tmp_path)
    port = _free_port()
    process = _start_host(tmp_path, port, HOST_TOKEN, "--session-dir", str(session_dir))
    try:
        _wait_for_health(port)
        with httpx.Client(
            trust_env=False, base_url=f"http://127.0.0.1:{port}", timeout=10.0
        ) as client:
            session_id = _create_session(client, workspace, fixture)
            client.post(
                f"/sessions/{session_id}/messages",
                headers=_headers(),
                json={"content": "写"},
            )
            log = session_dir / f"{session_id}.jsonl"
            tool_call_id = _wait_for_approval(log)
            _resolve_approval(client, session_id, tool_call_id, "approve")
            _wait_until_idle(client, session_id)

        assert HOST_TOKEN[:8] not in log.read_text(encoding="utf-8")
    finally:
        _stop(process)


def test_danger_full_access_needs_the_server_flag(tmp_path: Path) -> None:
    session_dir = tmp_path / "sessions"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    fixture = _mock_fixture(tmp_path)
    body = {
        "workspace": str(workspace),
        "provider": "mock",
        "fixture": str(fixture),
        "sandbox": "danger-full-access",
    }

    port = _free_port()
    process = _start_host(tmp_path, port, HOST_TOKEN, "--session-dir", str(session_dir))
    try:
        _wait_for_health(port)
        with httpx.Client(
            trust_env=False, base_url=f"http://127.0.0.1:{port}", timeout=5.0
        ) as client:
            rejected = client.post("/sessions", headers=_headers(), json=body)
        assert rejected.status_code == 400
        assert rejected.json()["error"]["code"] == "INVALID_ARGUMENT"
    finally:
        _stop(process)

    port = _free_port()
    process = _start_host(
        tmp_path,
        port,
        HOST_TOKEN,
        "--session-dir",
        str(session_dir),
        "--allow-danger-full-access",
    )
    try:
        _wait_for_health(port)
        with httpx.Client(
            trust_env=False, base_url=f"http://127.0.0.1:{port}", timeout=5.0
        ) as client:
            allowed = client.post("/sessions", headers=_headers(), json=body)
        assert allowed.status_code == 201
        session_id = allowed.json()["session_id"]
        records = [
            json.loads(line)
            for line in (session_dir / f"{session_id}.jsonl")
            .read_text(encoding="utf-8")
            .splitlines()
        ]
        started = next(record["payload"] for record in records if record["type"] == "session/start")
        assert started["sandbox"] == "danger-full-access"
    finally:
        _stop(process)


def test_auto_approval_needs_the_server_flag(tmp_path: Path) -> None:
    session_dir = tmp_path / "sessions"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    fixture = _write_fixture(tmp_path)
    body = {
        "workspace": str(workspace),
        "provider": "mock",
        "fixture": str(fixture),
        "approval": "auto",
    }

    port = _free_port()
    process = _start_host(tmp_path, port, HOST_TOKEN, "--session-dir", str(session_dir))
    try:
        _wait_for_health(port)
        with httpx.Client(
            trust_env=False, base_url=f"http://127.0.0.1:{port}", timeout=5.0
        ) as client:
            rejected = client.post("/sessions", headers=_headers(), json=body)
        assert rejected.status_code == 400
        assert rejected.json()["error"]["code"] == "INVALID_ARGUMENT"
    finally:
        _stop(process)

    port = _free_port()
    process = _start_host(
        tmp_path,
        port,
        HOST_TOKEN,
        "--session-dir",
        str(session_dir),
        "--allow-auto-approval",
    )
    try:
        _wait_for_health(port)
        with httpx.Client(
            trust_env=False, base_url=f"http://127.0.0.1:{port}", timeout=10.0
        ) as client:
            created = client.post("/sessions", headers=_headers(), json=body)
            assert created.status_code == 201
            session_id = created.json()["session_id"]
            client.post(
                f"/sessions/{session_id}/messages",
                headers=_headers(),
                json={"content": "写"},
            )
            _wait_until_idle(client, session_id)

        records = [
            json.loads(line)
            for line in (session_dir / f"{session_id}.jsonl")
            .read_text(encoding="utf-8")
            .splitlines()
        ]
        types = [record["type"] for record in records]
        results = [record["payload"] for record in records if record["type"] == "tool/result"]
        assert results[-1]["outcome"] == "OK"
        assert not any(event_type.startswith("approval/") for event_type in types)
    finally:
        _stop(process)


def _wait_for_approvals(log: Path, count: int) -> list[str]:
    deadline = time.monotonic() + 25.0
    while time.monotonic() < deadline:
        if log.is_file():
            records = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
            ids = [
                str(record["payload"]["tool_call_id"])
                for record in records
                if record["type"] == "approval/request"
            ]
            if len(ids) >= count:
                return ids
        time.sleep(0.05)
    pytest.fail(f"没有等到第 {count} 条 approval/request")


def _completion_fixture(workspace: Path, tmp_path: Path) -> Path:
    (workspace / "slow.py").write_text("import time\n\ntime.sleep(1.0)\n", encoding="utf-8")
    fixture = tmp_path / "completion.json"
    fixture.write_text(
        json.dumps(
            [
                {
                    "content": "写一个文件",
                    "finish_reason": "tool_calls",
                    "tool_calls": [
                        {
                            "id": "call-1",
                            "name": "write",
                            "arguments": {"file_path": "notes.md", "content": "hello\n"},
                        }
                    ],
                },
                {"content": "第一段完", "finish_reason": "stop"},
                {
                    "content": "跑一条慢命令",
                    "finish_reason": "tool_calls",
                    "tool_calls": [
                        {"id": "call-2", "name": "bash", "arguments": {"command": "python slow.py"}}
                    ],
                },
                {"content": "取消后", "finish_reason": "stop"},
                {"content": "第三段完", "finish_reason": "stop"},
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return fixture


def test_the_host_completion_script(tmp_path: Path) -> None:
    """H1 完成判据：两句话排队、批准一次写、取消一段、snapshot 重连，帧与日志相等。"""
    session_dir = tmp_path / "sessions"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    fixture = _completion_fixture(workspace, tmp_path)
    port = _free_port()
    process = _start_host(tmp_path, port, HOST_TOKEN, "--session-dir", str(session_dir))
    try:
        _wait_for_health(port)
        with httpx.Client(
            trust_env=False, base_url=f"http://127.0.0.1:{port}", timeout=15.0
        ) as client:
            session_id = _create_session(client, workspace, fixture)
            log = session_dir / f"{session_id}.jsonl"
            first = client.post(
                f"/sessions/{session_id}/messages",
                headers=_headers(),
                json={"content": "第一句"},
            )
            assert first.status_code == 202
            call_ids = _wait_for_approvals(log, 1)
            second = client.post(
                f"/sessions/{session_id}/messages",
                headers=_headers(),
                json={"content": "第二句"},
            )
            assert second.json()["queued"] is True
            _resolve_approval(client, session_id, call_ids[0], "approve")

            call_ids = _wait_for_approvals(log, 2)
            _resolve_approval(client, session_id, call_ids[1], "approve")
            time.sleep(0.2)
            cancelled = client.post(f"/sessions/{session_id}/cancel", headers=_headers())
            assert cancelled.status_code == 202
            _wait_until_idle(client, session_id)

            third = client.post(
                f"/sessions/{session_id}/messages",
                headers=_headers(),
                json={"content": "第三句"},
            )
            assert third.status_code == 202
            _wait_until_idle(client, session_id)

            records = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
            with client.stream(
                "GET",
                f"/sessions/{session_id}/events?snapshot=1",
                headers=_headers(),
            ) as response:
                snapshot = json.loads(_next_frame(response.iter_lines())["data"])
            with client.stream(
                "GET", f"/sessions/{session_id}/events", headers=_headers()
            ) as response:
                frames = _read_frames(response, len(records))

        assert snapshot["last_seq"] == records[-1]["seq"]
        assert isinstance(snapshot["messages"], list)
        assert len(frames) == len(records)
        for frame, record in zip(frames, records, strict=True):
            assert json.loads(frame["data"]) == record
        types = [record["type"] for record in records]
        ends = [
            record["payload"]["stop_reason"]
            for record in records
            if record["type"] == "segment/end"
        ]
        assert types[0] == "session/start"
        assert records[0]["payload"]["entry"] == "host"
        assert ends == ["MODEL_COMPLETED", "ABORTED", "MODEL_COMPLETED"]
        assert "error/abort" in types
        assert (workspace / "notes.md").read_text(encoding="utf-8") == "hello\n"
    finally:
        _stop(process)


def _write_fixture(tmp_path: Path) -> Path:
    fixture = tmp_path / "write.json"
    fixture.write_text(
        json.dumps(
            [
                {
                    "content": "写一个文件",
                    "finish_reason": "tool_calls",
                    "tool_calls": [
                        {
                            "id": "call-1",
                            "name": "write",
                            "arguments": {"file_path": "notes.md", "content": "hello\n"},
                        }
                    ],
                },
                {"content": "写完了", "finish_reason": "stop"},
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return fixture


def _wait_for_approval(log: Path) -> str:
    text = _wait_for_log(log, '"approval/request"')
    records = [json.loads(line) for line in text.splitlines()]
    request = next(record for record in records if record["type"] == "approval/request")
    return str(request["payload"]["tool_call_id"])


def _resolve_approval(
    client: httpx.Client, session_id: str, tool_call_id: str, decision: str
) -> httpx.Response:
    deadline = time.monotonic() + 10.0
    while time.monotonic() < deadline:
        response = client.post(
            f"/sessions/{session_id}/approvals/{tool_call_id}",
            headers=_headers(),
            json={"decision": decision},
        )
        if response.status_code != 404:
            return response
        time.sleep(0.05)
    pytest.fail(f"审批 {tool_call_id} 一直没有登记")


def test_host_approves_a_write_over_http(tmp_path: Path) -> None:
    session_dir = tmp_path / "sessions"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    fixture = _write_fixture(tmp_path)
    port = _free_port()
    process = _start_host(tmp_path, port, HOST_TOKEN, "--session-dir", str(session_dir))
    try:
        _wait_for_health(port)
        with httpx.Client(
            trust_env=False, base_url=f"http://127.0.0.1:{port}", timeout=10.0
        ) as client:
            session_id = _create_session(client, workspace, fixture)
            client.post(
                f"/sessions/{session_id}/messages",
                headers=_headers(),
                json={"content": "写"},
            )
            log = session_dir / f"{session_id}.jsonl"
            tool_call_id = _wait_for_approval(log)
            response = _resolve_approval(client, session_id, tool_call_id, "approve")
            assert response.status_code == 200
            _wait_until_idle(client, session_id)

        records = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
        responses = [
            record["payload"] for record in records if record["type"] == "approval/response"
        ]
        results = [record["payload"] for record in records if record["type"] == "tool/result"]
        assert responses[-1]["decision"] == "APPROVED"
        assert results[-1]["outcome"] == "OK"
        assert (workspace / "notes.md").read_text(encoding="utf-8") == "hello\n"
    finally:
        _stop(process)


def test_host_denies_a_write_over_http(tmp_path: Path) -> None:
    session_dir = tmp_path / "sessions"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    fixture = _write_fixture(tmp_path)
    port = _free_port()
    process = _start_host(tmp_path, port, HOST_TOKEN, "--session-dir", str(session_dir))
    try:
        _wait_for_health(port)
        with httpx.Client(
            trust_env=False, base_url=f"http://127.0.0.1:{port}", timeout=10.0
        ) as client:
            session_id = _create_session(client, workspace, fixture)
            client.post(
                f"/sessions/{session_id}/messages",
                headers=_headers(),
                json={"content": "写"},
            )
            log = session_dir / f"{session_id}.jsonl"
            tool_call_id = _wait_for_approval(log)
            response = _resolve_approval(client, session_id, tool_call_id, "deny")
            assert response.status_code == 200
            _wait_until_idle(client, session_id)
            unknown = client.post(
                f"/sessions/{session_id}/approvals/not-a-call",
                headers=_headers(),
                json={"decision": "approve"},
            )
            assert unknown.status_code == 404

        records = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
        responses = [
            record["payload"] for record in records if record["type"] == "approval/response"
        ]
        results = [record["payload"] for record in records if record["type"] == "tool/result"]
        ends = [record["payload"] for record in records if record["type"] == "segment/end"]
        assert responses[-1]["decision"] == "DENIED"
        assert results[-1]["outcome"] == "DENIED_BY_APPROVAL"
        assert ends[-1]["stop_reason"] == "FENCE_DENIED"
        assert not (workspace / "notes.md").exists()
    finally:
        _stop(process)


def test_cancel_ends_only_the_segment(tmp_path: Path) -> None:
    session_dir = tmp_path / "sessions"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    fixture = _slow_fixture(workspace, tmp_path)
    port = _free_port()
    process = _start_host(
        tmp_path,
        port,
        HOST_TOKEN,
        "--session-dir",
        str(session_dir),
        "--allow-auto-approval",
    )
    try:
        _wait_for_health(port)
        with httpx.Client(
            trust_env=False, base_url=f"http://127.0.0.1:{port}", timeout=10.0
        ) as client:
            session_id = _create_session(
                client, workspace, fixture, provider="mock", approval="auto"
            )
            log = session_dir / f"{session_id}.jsonl"
            client.post(
                f"/sessions/{session_id}/messages",
                headers=_headers(),
                json={"content": "第一句"},
            )
            _wait_for_log(log, '"tool/call"')
            queued = client.post(
                f"/sessions/{session_id}/messages",
                headers=_headers(),
                json={"content": "排队句"},
            )
            assert queued.json()["queued"] is True
            cancelled = client.post(f"/sessions/{session_id}/cancel", headers=_headers())
            assert cancelled.status_code == 202
            _wait_until_idle(client, session_id)

            again = client.post(
                f"/sessions/{session_id}/messages",
                headers=_headers(),
                json={"content": "第三句"},
            )
            assert again.status_code == 202
            _wait_until_idle(client, session_id)

        records = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
        types = [record["type"] for record in records]
        ends = [record["payload"] for record in records if record["type"] == "segment/end"]
        messages = [
            record["payload"]["content"] for record in records if record["type"] == "user/message"
        ]
        assert "error/abort" in types
        assert [end["stop_reason"] for end in ends] == [
            "ABORTED",
            "MODEL_COMPLETED",
            "MODEL_COMPLETED",
        ]
        assert messages == ["第一句", "排队句", "第三句"]
    finally:
        _stop(process)


def test_cancel_on_an_idle_session_is_a_noop(tmp_path: Path) -> None:
    session_dir = tmp_path / "sessions"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    fixture = _mock_fixture(tmp_path)
    port = _free_port()
    process = _start_host(tmp_path, port, HOST_TOKEN, "--session-dir", str(session_dir))
    try:
        _wait_for_health(port)
        with httpx.Client(
            trust_env=False, base_url=f"http://127.0.0.1:{port}", timeout=5.0
        ) as client:
            session_id = _create_session(client, workspace, fixture)
            log = session_dir / f"{session_id}.jsonl"
            before = log.read_bytes()
            response = client.post(f"/sessions/{session_id}/cancel", headers=_headers())
            after = log.read_bytes()

        assert response.status_code == 200
        assert after == before
    finally:
        _stop(process)


def test_delete_closes_only_an_idle_session(tmp_path: Path) -> None:
    session_dir = tmp_path / "sessions"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    fixture = _slow_fixture(workspace, tmp_path)
    port = _free_port()
    process = _start_host(
        tmp_path,
        port,
        HOST_TOKEN,
        "--session-dir",
        str(session_dir),
        "--allow-auto-approval",
    )
    try:
        _wait_for_health(port)
        with httpx.Client(
            trust_env=False, base_url=f"http://127.0.0.1:{port}", timeout=10.0
        ) as client:
            session_id = _create_session(
                client, workspace, fixture, provider="mock", approval="auto"
            )
            log = session_dir / f"{session_id}.jsonl"
            client.post(
                f"/sessions/{session_id}/messages",
                headers=_headers(),
                json={"content": "第一句"},
            )
            _wait_for_log(log, '"tool/call"')
            while_running = client.delete(f"/sessions/{session_id}", headers=_headers())
            assert while_running.status_code == 409
            _wait_until_idle(client, session_id)

            closed = client.delete(f"/sessions/{session_id}", headers=_headers())
            again = client.delete(f"/sessions/{session_id}", headers=_headers())
            replacement = _create_session(
                client, workspace, fixture, provider="mock", approval="auto"
            )

        assert closed.status_code == 200
        assert again.status_code == 404
        assert replacement != session_id
        records = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
        assert records[-1]["type"] == "session/end"
        assert records[-1]["payload"]["stop_reason"] == "MODEL_COMPLETED"
    finally:
        _stop(process)


def test_a_second_message_queues_and_runs_after_the_first(tmp_path: Path) -> None:
    session_dir = tmp_path / "sessions"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "slow.py").write_text("import time\n\ntime.sleep(1.0)\n", encoding="utf-8")
    fixture = tmp_path / "slow.json"
    fixture.write_text(
        json.dumps(
            [
                {
                    "content": "跑一条慢命令",
                    "finish_reason": "tool_calls",
                    "tool_calls": [
                        {"id": "c1", "name": "bash", "arguments": {"command": "python slow.py"}}
                    ],
                },
                {"content": "第一段完", "finish_reason": "stop"},
                {"content": "第二段完", "finish_reason": "stop"},
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    port = _free_port()
    process = _start_host(
        tmp_path,
        port,
        HOST_TOKEN,
        "--session-dir",
        str(session_dir),
        "--allow-auto-approval",
    )
    try:
        _wait_for_health(port)
        with httpx.Client(
            trust_env=False, base_url=f"http://127.0.0.1:{port}", timeout=10.0
        ) as client:
            session_id = _create_session(
                client, workspace, fixture, provider="mock", approval="auto"
            )
            first = client.post(
                f"/sessions/{session_id}/messages",
                headers=_headers(),
                json={"content": "第一句"},
            )
            assert first.status_code == 202
            assert first.json()["queued"] is False
            log = session_dir / f"{session_id}.jsonl"
            _wait_for_log(log, '"tool/call"')

            second = client.post(
                f"/sessions/{session_id}/messages",
                headers=_headers(),
                json={"content": "第二句"},
            )
            third = client.post(
                f"/sessions/{session_id}/messages",
                headers=_headers(),
                json={"content": "第三句"},
            )
            assert second.status_code == 202
            assert second.json()["queued"] is True
            assert third.status_code == 429
            assert third.json()["error"]["code"] == "SESSION_BUSY"
            _wait_until_idle(client, session_id)

        records = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
        starts = [
            record["payload"]["segment_id"]
            for record in records
            if record["type"] == "segment/start"
        ]
        ends = [
            record["payload"]["stop_reason"]
            for record in records
            if record["type"] == "segment/end"
        ]
        messages = [
            record["payload"]["content"] for record in records if record["type"] == "user/message"
        ]
        types = [record["type"] for record in records]
        first_end = types.index("segment/end")
        second_start = types.index("segment/start", first_end)
        assert starts == ["s1", "s2"]
        assert ends == ["MODEL_COMPLETED", "MODEL_COMPLETED"]
        assert messages == ["第一句", "第二句"]
        assert first_end < second_start
    finally:
        _stop(process)


def test_a_message_starts_a_segment(tmp_path: Path) -> None:
    session_dir = tmp_path / "sessions"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    fixture = _mock_fixture(tmp_path)
    port = _free_port()
    process = _start_host(tmp_path, port, HOST_TOKEN, "--session-dir", str(session_dir))
    try:
        _wait_for_health(port)
        with httpx.Client(
            trust_env=False, base_url=f"http://127.0.0.1:{port}", timeout=10.0
        ) as client:
            session_id = _create_session(client, workspace, fixture)
            response = client.post(
                f"/sessions/{session_id}/messages",
                headers=_headers(),
                json={"content": "任务"},
            )
            assert response.status_code == 202
            assert response.json()["queued"] is False
            _wait_until_idle(client, session_id)

        records = [
            json.loads(line)
            for line in (session_dir / f"{session_id}.jsonl")
            .read_text(encoding="utf-8")
            .splitlines()
        ]
        types = [record["type"] for record in records]
        start = types.index("segment/start")
        user = types.index("user/message")
        end = types.index("segment/end")
        assert start < user < end
        assert records[user]["payload"]["content"] == "任务"
        assert records[end]["payload"]["stop_reason"] == "MODEL_COMPLETED"
    finally:
        _stop(process)


def test_create_session_writes_the_host_entry(tmp_path: Path) -> None:
    session_dir = tmp_path / "sessions"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    fixture = _mock_fixture(tmp_path)
    port = _free_port()
    process = _start_host(tmp_path, port, HOST_TOKEN, "--session-dir", str(session_dir))
    try:
        _wait_for_health(port)
        with httpx.Client(
            trust_env=False, base_url=f"http://127.0.0.1:{port}", timeout=5.0
        ) as client:
            response = client.post(
                "/sessions",
                headers=_headers(),
                json={
                    "workspace": str(workspace),
                    "provider": "mock",
                    "fixture": str(fixture),
                    "max_turns": 3,
                },
            )
        assert response.status_code == 201
        created = response.json()
        session_id = created["session_id"]
        assert re.fullmatch(r"[0-9a-f]{32}", session_id)
        assert isinstance(created["cursor"], int)

        log = session_dir / f"{session_id}.jsonl"
        records = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
        started = next(record["payload"] for record in records if record["type"] == "session/start")
        assert started["entry"] == "host"
        assert started["prompt"] == ""
        assert started["workspace"] == str(workspace.resolve())
        assert started["provider"] == "mock"
        assert started["max_turns"] == 3
    finally:
        _stop(process)


def test_host_can_bind_all_interfaces_with_a_token(tmp_path: Path) -> None:
    port = _free_port()
    process = _start_host(tmp_path, port, HOST_TOKEN, "--host", "0.0.0.0")
    try:
        assert _wait_for_health(port).status_code == 200
    finally:
        _stop(process)


def test_invalid_bind_arguments_exit_two_without_a_log(tmp_path: Path) -> None:
    for argument in (["--port", "0"], ["--port", "70000"], ["--host", "example.com"]):
        result = _cli(
            "host",
            "--http",
            *argument,
            cwd=tmp_path,
            env=_host_env(HOST_TOKEN),
        )

        assert result.returncode == 2, argument
        assert "INVALID_ARGUMENT" in result.stderr, argument
        assert list(tmp_path.rglob("*.jsonl")) == []


def test_a_bind_failure_exits_two_without_a_log(tmp_path: Path) -> None:
    with socket.socket() as occupied:
        occupied.bind(("127.0.0.1", 0))
        occupied.listen()
        port = int(occupied.getsockname()[1])

        result = _cli(
            "host",
            "--http",
            "--port",
            str(port),
            cwd=tmp_path,
            env=_host_env(HOST_TOKEN),
        )

    assert result.returncode == 2
    assert "INVALID_ARGUMENT" in result.stderr
    assert list(tmp_path.rglob("*.jsonl")) == []


def test_a_bad_session_request_leaves_no_log(tmp_path: Path) -> None:
    session_dir = tmp_path / "sessions"
    fixture = _mock_fixture(tmp_path)
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    invalid_config_workspace = tmp_path / "invalid-config"
    invalid_config_workspace.mkdir()
    (invalid_config_workspace / "mini.config.toml").write_text(
        'max_turns = "three"\n', encoding="utf-8"
    )
    unknown_tool_workspace = tmp_path / "unknown-tool"
    unknown_tool_workspace.mkdir()
    (unknown_tool_workspace / "mini.config.toml").write_text(
        'tools = ["web_search"]\n', encoding="utf-8"
    )

    port = _free_port()
    process = _start_host(tmp_path, port, HOST_TOKEN, "--session-dir", str(session_dir))
    try:
        _wait_for_health(port)
        bad_bodies = [
            {
                "workspace": str(invalid_config_workspace),
                "provider": "mock",
                "fixture": str(fixture),
            },
            {
                "workspace": str(workspace),
                "provider": "openai",
                "base_url": "http://127.0.0.1:1/v1",
                "model": "m",
                "api_key_env": "MINIHNS_HOST_TEST_UNSET_KEY",
            },
            {"workspace": str(unknown_tool_workspace), "provider": "mock", "fixture": str(fixture)},
            {"auto_approve": True},
            {"max_turns": "three"},
        ]
        with httpx.Client(
            trust_env=False, base_url=f"http://127.0.0.1:{port}", timeout=5.0
        ) as client:
            for body in bad_bodies:
                response = client.post("/sessions", headers=_headers(), json=body)
                assert response.status_code == 400, body
                assert response.json()["error"]["code"] == "INVALID_ARGUMENT"

        assert list(session_dir.glob("*.jsonl")) == []
    finally:
        _stop(process)


def test_the_session_cap_is_enforced(tmp_path: Path) -> None:
    session_dir = tmp_path / "sessions"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    fixture = _mock_fixture(tmp_path)
    port = _free_port()
    process = _start_host(tmp_path, port, HOST_TOKEN, "--session-dir", str(session_dir))
    body = {"workspace": str(workspace), "provider": "mock", "fixture": str(fixture)}
    try:
        _wait_for_health(port)
        with httpx.Client(
            trust_env=False, base_url=f"http://127.0.0.1:{port}", timeout=5.0
        ) as client:
            for _ in range(4):
                created = client.post("/sessions", headers=_headers(), json=body)
                assert created.status_code == 201

            fifth = client.post("/sessions", headers=_headers(), json=body)
            listed = client.get("/sessions", headers=_headers())

        assert fifth.status_code == 429
        assert fifth.json()["error"]["code"] == "TOO_MANY_SESSIONS"
        assert len(listed.json()["sessions"]) == 4
        assert len(list(session_dir.glob("*.jsonl"))) == 4
    finally:
        _stop(process)


def test_an_invalid_session_id_is_rejected(tmp_path: Path) -> None:
    session_dir = tmp_path / "sessions"
    port = _free_port()
    process = _start_host(tmp_path, port, HOST_TOKEN, "--session-dir", str(session_dir))
    try:
        _wait_for_health(port)
        with httpx.Client(
            trust_env=False, base_url=f"http://127.0.0.1:{port}", timeout=5.0
        ) as client:
            short = client.get("/sessions/xyz", headers=_headers())
            traversal = client.get("/sessions/%2E%2E/secret/events", headers=_headers())
            unknown = client.get("/sessions/" + "0" * 32, headers=_headers())

        assert short.status_code == 400
        assert short.json()["error"]["code"] == "INVALID_ARGUMENT"
        assert traversal.status_code == 400
        assert traversal.json()["error"]["code"] == "INVALID_ARGUMENT"
        assert unknown.status_code == 404
        assert unknown.json()["error"]["code"] == "SESSION_NOT_FOUND"
    finally:
        _stop(process)


def test_a_foreign_origin_is_forbidden(tmp_path: Path) -> None:
    port = _free_port()
    process = _start_host(tmp_path, port)
    try:
        _wait_for_health(port)
        base_url = f"http://127.0.0.1:{port}"
        with httpx.Client(trust_env=False, base_url=base_url, timeout=5.0) as client:
            foreign = client.post(
                "/sessions",
                json={"provider": "mock"},
                headers={
                    "Authorization": f"Bearer {HOST_TOKEN}",
                    "Origin": "https://example.com",
                },
            )
            assert foreign.status_code == 403
            assert foreign.json()["error"]["code"] == "FORBIDDEN"

            for origin in ("null", base_url):
                preflight = client.options(
                    "/sessions",
                    headers={
                        "Origin": origin,
                        "Access-Control-Request-Method": "POST",
                        "Access-Control-Request-Headers": "authorization,content-type",
                    },
                )
                assert preflight.status_code == 204, origin
                assert preflight.headers["Access-Control-Allow-Origin"] == origin
                allow_headers = preflight.headers["Access-Control-Allow-Headers"].lower()
                assert "authorization" in allow_headers
                assert "content-type" in allow_headers
    finally:
        _stop(process)


def test_host_rejects_missing_or_wrong_token(tmp_path: Path) -> None:
    port = _free_port()
    process = _start_host(tmp_path, port)
    try:
        _wait_for_health(port)
        with httpx.Client(
            trust_env=False, base_url=f"http://127.0.0.1:{port}", timeout=5.0
        ) as client:
            missing = client.get("/sessions")
            wrong = client.get("/sessions", headers={"Authorization": "Bearer wrong"})
            allowed = client.get("/sessions", headers={"Authorization": f"Bearer {HOST_TOKEN}"})

        assert missing.status_code == 401
        assert missing.json()["error"]["code"] == "UNAUTHORIZED"
        assert wrong.status_code == 401
        assert wrong.json()["error"]["code"] == "UNAUTHORIZED"
        assert allowed.status_code == 200
        assert allowed.json() == {"sessions": []}
    finally:
        _stop(process)


def test_host_starts_and_health_is_public(tmp_path: Path) -> None:
    port = _free_port()
    env_without_token = dict(os.environ)
    env_without_token.pop("MINIHNS_HOST_TOKEN", None)

    missing = _cli(
        "host",
        "--http",
        "--port",
        str(port),
        cwd=tmp_path,
        env=env_without_token,
    )

    assert missing.returncode == 2
    assert "INVALID_ARGUMENT" in missing.stderr
    assert list(tmp_path.rglob("*.jsonl")) == []

    process = _start_host(tmp_path, port)
    try:
        response = _wait_for_health(port)

        assert response.status_code == 200
        assert response.json() == {"protocol": 1, "sessions": 0, "features": ["delta"]}
    finally:
        _stop(process)
