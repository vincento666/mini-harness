"""seam ⑥：CLI 黑盒（子进程）。"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from paths import HELLO_SCENARIO


def _cli(*args: str, cwd: Path, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "mini_harness.cli.main", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
    )


def _log_files(cwd: Path) -> list[Path]:
    session_dir = cwd / "sessions"
    if not session_dir.is_dir():
        return []
    return sorted(session_dir.glob("*.jsonl"))


def test_mock_provider_without_fixture_is_an_invalid_argument(tmp_path: Path) -> None:
    result = _cli("run", "-p", "任务", "--provider", "mock", cwd=tmp_path)

    assert result.returncode == 2
    assert "INVALID_ARGUMENT" in result.stderr
    assert _log_files(tmp_path) == []


def test_run_without_prompt_is_an_invalid_argument(tmp_path: Path) -> None:
    result = _cli("run", cwd=tmp_path)

    assert result.returncode == 2
    assert "INVALID_ARGUMENT" in result.stderr
    assert _log_files(tmp_path) == []


def test_run_with_empty_prompt_is_an_invalid_argument(tmp_path: Path) -> None:
    result = _cli("run", "-p", "", cwd=tmp_path)

    assert result.returncode == 2
    assert "INVALID_ARGUMENT" in result.stderr
    assert _log_files(tmp_path) == []


def test_max_turns_zero_is_an_invalid_argument(tmp_path: Path) -> None:
    result = _cli(
        "run", "-p", "任务", "--provider", "mock", "--fixture", str(HELLO_SCENARIO),
        "--max-turns", "0", cwd=tmp_path,
    )

    assert result.returncode == 2
    assert "INVALID_ARGUMENT" in result.stderr


def test_unknown_provider_is_rejected(tmp_path: Path) -> None:
    result = _cli("run", "-p", "任务", "--provider", "deepseek", cwd=tmp_path)

    assert result.returncode == 2
    assert "UNKNOWN_PROVIDER" in result.stderr


def test_invalid_fixture_is_rejected(tmp_path: Path) -> None:
    broken = tmp_path / "broken.json"
    broken.write_text("{not json", encoding="utf-8")

    result = _cli(
        "run", "-p", "任务", "--provider", "mock", "--fixture", str(broken), cwd=tmp_path
    )

    assert result.returncode == 2
    assert "FIXTURE_INVALID" in result.stderr


def test_happy_path_prints_session_id_and_writes_the_log(tmp_path: Path) -> None:
    result = _cli(
        "run", "-p", "任务", "--provider", "mock", "--fixture", str(HELLO_SCENARIO), cwd=tmp_path
    )

    session_id = result.stdout.strip()
    assert result.returncode == 0
    assert session_id
    assert (tmp_path / "sessions" / f"{session_id}.jsonl").is_file()


def test_events_jsonl_stdout_matches_the_log_line_by_line(tmp_path: Path) -> None:
    result = _cli(
        "run", "-p", "任务", "--provider", "mock", "--fixture", str(HELLO_SCENARIO),
        "--events", "jsonl", cwd=tmp_path,
    )

    log_path = _log_files(tmp_path)[0]
    stdout_events = [json.loads(line) for line in result.stdout.splitlines() if line.strip()]
    log_events = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()]

    assert result.returncode == 0
    assert len(stdout_events) == len(log_events)
    assert stdout_events == log_events


def test_api_key_from_the_environment_never_reaches_log_or_stdout(tmp_path: Path) -> None:
    secret = "sk-test-super-secret-value"
    env = {**os.environ, "DEEPSEEK_API_KEY": secret}

    result = _cli(
        "run", "-p", "任务", "--provider", "mock", "--fixture", str(HELLO_SCENARIO),
        cwd=tmp_path, env=env,
    )

    log_text = _log_files(tmp_path)[0].read_text(encoding="utf-8")

    assert result.returncode == 0
    assert secret not in result.stdout
    assert secret not in result.stderr
    assert secret not in log_text
