"""seam ⑥：`minihns serve --http` 的 HTTP 黑盒（真实子进程 + 真实 HTTP 客户端）。"""

from __future__ import annotations

import asyncio
import json
import socket
from collections.abc import Iterable
from pathlib import Path

import httpx

from cli_blackbox import _cli, _cli_process
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


def _log_records(cwd: Path) -> list[dict[str, object]]:
    logs = _log_files(cwd)
    assert len(logs) == 1
    return [json.loads(line) for line in logs[0].read_text(encoding="utf-8").splitlines() if line]


def _free_port() -> int:
    """拿一个刚释放的端口：绑 0 读回端口号再关掉。

    这中间有一小段竞争（别的进程可能抢走它），测试里接受：真被抢时 serve 会以退出码 2 失败，
    信号是清楚的，不会伪装成通过。
    """
    probe = socket.socket()
    probe.bind(("127.0.0.1", 0))
    port = probe.getsockname()[1]
    probe.close()
    return port


def _slow_fixture(cwd: Path) -> Path:
    """一条会慢的会话：`bash` 跑一个睡 2 秒的脚本，客户端才有时间在会话进行中连上。

    命令写成 `python <文件>`：`-c` 的引号在 `cmd.exe` 与 `/bin/sh` 里语义不同（同 `test_cli_run`）。
    `--yes` 是因为黑盒的 stdin 不是 tty，没有人可问。
    """
    (cwd / "slowly.py").write_text("import time\n\ntime.sleep(2)\n", encoding="utf-8")
    fixture = cwd / "slow.json"
    fixture.write_text(
        json.dumps(
            [
                {
                    "content": "跑一条慢命令",
                    "finish_reason": "tool_calls",
                    "tool_calls": [
                        {"id": "c1", "name": "bash", "arguments": {"command": "python slowly.py"}}
                    ],
                },
                {"content": "完了", "finish_reason": "stop"},
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return fixture


def _parse_sse(lines: Iterable[str]) -> list[dict[str, str]]:
    """按 SSE 的分帧规则切帧：空行结束一帧，`字段名: 值`。"""
    frames: list[dict[str, str]] = []
    fields: dict[str, str] = {}
    for line in lines:
        if not line:
            if fields:
                frames.append(fields)
                fields = {}
            continue
        name, _, value = line.partition(":")
        fields[name] = value.removeprefix(" ")
    if fields:
        frames.append(fields)
    return frames


async def _read_stream(
    port: int,
    *,
    last_event_id: str | None = None,
    query: dict[str, str] | None = None,
) -> tuple[int, list[dict[str, str]]]:
    """连上 `GET /events` 读到底。连接被拒就重试，直到 serve 进程开始监听。

    `trust_env=False`：本机环境里有 `HTTP_PROXY` 与带 `[::1]` 的 `NO_PROXY`，httpx 解析后者会当场
    抛 `InvalidURL`。事件流是本机回环上的连接，测试不该看运行环境的脸色。
    """
    headers = {} if last_event_id is None else {"Last-Event-ID": last_event_id}
    async with httpx.AsyncClient(base_url=f"http://127.0.0.1:{port}", trust_env=False) as client:
        for _ in range(200):
            try:
                async with client.stream(
                    "GET", "/events", headers=headers, params=query, timeout=30
                ) as response:
                    if response.status_code != 200:
                        await response.aread()
                        return response.status_code, []
                    lines = [line async for line in response.aiter_lines()]
                    return response.status_code, _parse_sse(lines)
            except httpx.ConnectError:
                await asyncio.sleep(0.02)
    raise AssertionError(f"{port} 上没有开始监听的 serve 进程")


async def test_one_frame_per_log_record(tmp_path: Path) -> None:
    """一帧对应一条记录：帧数等于日志行数，`id` / `event` / `data` 逐字段对得上。"""
    port = _free_port()
    process = _cli_process(
        "serve",
        "--http",
        "-p",
        "任务",
        "--port",
        str(port),
        "--provider",
        "mock",
        "--fixture",
        str(_slow_fixture(tmp_path)),
        "--yes",
        cwd=tmp_path,
    )
    try:
        status, frames = await _read_stream(port)
        exit_code = process.wait(timeout=60)
    finally:
        if process.poll() is None:
            process.terminate()

    records = _log_records(tmp_path)
    assert status == 200
    assert exit_code == 0
    assert len(frames) == len(records)
    for frame, record in zip(frames, records, strict=True):
        assert frame["id"] == str(record["seq"])
        assert frame["event"] == record["type"]
        assert json.loads(frame["data"]) == record
