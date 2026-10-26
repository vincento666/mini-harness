"""seam ⑥：`minihns host --http` 的黑盒判据（H1）。

这些判据跑真实子进程 + 真 HTTP：token 只从环境变量读，端口取空闲端口，进程在 finally 里收掉。
"""

from __future__ import annotations

import os
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
