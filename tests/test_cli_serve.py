"""seam ⑥：`minihns serve --http` 的 HTTP 黑盒（真实子进程 + 真实 HTTP 客户端）。"""

from __future__ import annotations

import socket
from pathlib import Path

from cli_blackbox import _cli
from paths import HELLO_SCENARIO


def _log_files(cwd: Path) -> list[Path]:
    session_dir = cwd / "sessions"
    if not session_dir.is_dir():
        return []
    return sorted(session_dir.glob("*.jsonl"))


def test_serve_requires_a_non_empty_prompt(tmp_path: Path) -> None:
    """prompt 是 serve 的必填项：缺它的失败发生在会话开始之前。"""
    result = _cli(
        "serve",
        "--http",
        "--provider",
        "mock",
        "--fixture",
        str(HELLO_SCENARIO),
        cwd=tmp_path,
    )

    assert result.returncode == 2
    assert "INVALID_ARGUMENT: -p/--prompt 必填且非空" in result.stderr
    assert _log_files(tmp_path) == []


def test_ports_outside_the_vocabulary_are_invalid_arguments(tmp_path: Path) -> None:
    """`--port` 的词表是 1 至 65535（照 DSH 的 `dsh-host-webserver`）：越界在会话开始之前判掉。"""
    for port in ("0", "65536"):
        result = _cli(
            "serve",
            "--http",
            "-p",
            "任务",
            "--port",
            port,
            "--provider",
            "mock",
            "--fixture",
            str(HELLO_SCENARIO),
            cwd=tmp_path,
        )

        assert result.returncode == 2
        assert f"INVALID_ARGUMENT: --port 只接受 1 至 65535 的整数，收到 {port}" in result.stderr
        assert _log_files(tmp_path) == []


def test_host_outside_the_vocabulary_is_an_invalid_argument(tmp_path: Path) -> None:
    """`--host` 只接受 `127.0.0.1` 与 `0.0.0.0`（照 DSH 的 `dsh-host-webserver`）。"""
    result = _cli(
        "serve",
        "--http",
        "-p",
        "任务",
        "--host",
        "localhost",
        "--provider",
        "mock",
        "--fixture",
        str(HELLO_SCENARIO),
        cwd=tmp_path,
    )

    assert result.returncode == 2
    assert "INVALID_ARGUMENT: --host 只接受 127.0.0.1 / 0.0.0.0，收到 localhost" in result.stderr
    assert _log_files(tmp_path) == []


def test_serve_does_not_accept_events(tmp_path: Path) -> None:
    """`serve` 的 flag 表是 run 的表减去 `--events`：事件流住在 HTTP 上，不在 stdout 上。"""
    result = _cli(
        "serve",
        "--http",
        "-p",
        "任务",
        "--events",
        "jsonl",
        "--provider",
        "mock",
        "--fixture",
        str(HELLO_SCENARIO),
        cwd=tmp_path,
    )

    assert result.returncode == 2
    assert "INVALID_ARGUMENT" in result.stderr
    assert _log_files(tmp_path) == []


def test_an_occupied_port_fails_before_the_session_starts(tmp_path: Path) -> None:
    """端口被占是 session 开始之前的失败：不建日志、不发模型请求，stderr 说清是哪个端口。"""
    blocker = socket.socket()
    blocker.bind(("127.0.0.1", 0))
    port = blocker.getsockname()[1]
    blocker.listen(1)
    try:
        result = _cli(
            "serve",
            "--http",
            "-p",
            "任务",
            "--port",
            str(port),
            "--provider",
            "mock",
            "--fixture",
            str(HELLO_SCENARIO),
            cwd=tmp_path,
        )
    finally:
        blocker.close()

    assert result.returncode == 2
    assert "INVALID_ARGUMENT" in result.stderr
    assert str(port) in result.stderr
    assert _log_files(tmp_path) == []


def test_serve_window_budget_failure_is_the_same_shape_as_run(tmp_path: Path) -> None:
    """使触发线为 0 的窗口与预留是参数错误：与 run 同形，且在日志创建之前。"""
    result = _cli(
        "serve",
        "--http",
        "-p",
        "任务",
        "--window",
        "65536",
        "--reserve",
        "8192",
        "--provider",
        "mock",
        "--fixture",
        str(HELLO_SCENARIO),
        cwd=tmp_path,
    )

    assert result.returncode == 2
    assert "INVALID_ARGUMENT" in result.stderr
    assert _log_files(tmp_path) == []
