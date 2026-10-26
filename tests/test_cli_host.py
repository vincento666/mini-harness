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


def _stop(process: subprocess.Popen[str]) -> None:
    """优雅收掉 host：Windows 发 Ctrl-Break（进程组已建好），POSIX 发 SIGTERM。

    硬杀会让 `coverage run` 来不及写 partial，host 那一半就看不见了；收尾必须走信号。
    """
    if process.poll() is not None:
        process.wait(timeout=10)
        return
    if sys.platform == "win32":
        process.send_signal(signal.CTRL_BREAK_EVENT)
    else:
        process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=10)


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

        assert closed.status_code == 200
        assert again.status_code == 404
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
        assert response.json() == {"protocol": 1, "sessions": 0}
    finally:
        _stop(process)
