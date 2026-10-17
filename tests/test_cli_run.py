"""seam ⑥：CLI 黑盒（子进程）。"""

from __future__ import annotations

import asyncio
import codecs
import json
import os
import signal
from pathlib import Path

from cli_blackbox import _cli
from mini_harness.cli import main as cli_main
from mini_harness.cli.main import STOP_REASONS_TO_EXIT_CODES, exit_code_for, sigint_handler
from mini_harness.events import EventLog
from mini_harness.loop import STOP_REASONS, RunOutcome, SessionSettings
from mini_harness.provider import AssistantTurn
from paths import HELLO_SCENARIO


def _log_files(cwd: Path) -> list[Path]:
    session_dir = cwd / "sessions"
    if not session_dir.is_dir():
        return []
    return sorted(session_dir.glob("*.jsonl"))


async def test_sigint_handler_sets_the_cancel_event() -> None:
    cancel = asyncio.Event()

    sigint_handler(cancel)(signal.SIGINT, None)
    await asyncio.sleep(0)

    assert cancel.is_set()


def test_every_stop_reason_maps_to_an_exit_code() -> None:
    assert set(STOP_REASONS_TO_EXIT_CODES) == set(STOP_REASONS)
    assert STOP_REASONS_TO_EXIT_CODES["TOOL_CALLS"] == 0
    assert STOP_REASONS_TO_EXIT_CODES["MODEL_COMPLETED"] == 0
    assert STOP_REASONS_TO_EXIT_CODES["MAX_TURNS"] == 0
    assert STOP_REASONS_TO_EXIT_CODES["PROVIDER_ERROR"] == 1
    assert STOP_REASONS_TO_EXIT_CODES["ABORTED"] == 5
    for stop_reason, exit_code in STOP_REASONS_TO_EXIT_CODES.items():
        assert (
            exit_code_for(RunOutcome(session_id="s", stop_reason=stop_reason, turns=1)) == exit_code
        )


def test_a_log_layer_failure_outcome_maps_to_exit_code_one() -> None:
    outcome = RunOutcome(
        session_id="s",
        stop_reason="LOG_WRITE_FAILED",
        turns=1,
        failure_code="LOG_WRITE_FAILED",
        detail="sessions/s.jsonl: 拒绝访问",
    )

    assert exit_code_for(outcome) == 1


def test_unwritable_session_dir_is_a_log_write_failure(tmp_path: Path) -> None:
    blocker = tmp_path / "blocker"
    blocker.write_text("not a directory", encoding="utf-8")

    result = _cli(
        "run",
        "-p",
        "任务",
        "--provider",
        "mock",
        "--fixture",
        str(HELLO_SCENARIO),
        "--session-dir",
        str(blocker / "sessions"),
        cwd=tmp_path,
    )

    assert result.returncode == 1
    assert "LOG_WRITE_FAILED" in result.stderr
    assert str(blocker / "sessions") in result.stderr
    assert _log_files(tmp_path) == []


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
        "run",
        "-p",
        "任务",
        "--provider",
        "mock",
        "--fixture",
        str(HELLO_SCENARIO),
        "--max-turns",
        "0",
        cwd=tmp_path,
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

    result = _cli("run", "-p", "任务", "--provider", "mock", "--fixture", str(broken), cwd=tmp_path)

    assert result.returncode == 2
    assert "FIXTURE_INVALID" in result.stderr
    assert _log_files(tmp_path) == []


def test_fixture_with_a_utf8_bom_runs(tmp_path: Path) -> None:
    bommed = tmp_path / "bommed.json"
    bommed.write_bytes(
        codecs.BOM_UTF8
        + json.dumps([{"content": "hello", "finish_reason": "stop"}], ensure_ascii=False).encode(
            "utf-8"
        )
    )

    result = _cli("run", "-p", "任务", "--provider", "mock", "--fixture", str(bommed), cwd=tmp_path)

    assert result.returncode == 0
    assert "FIXTURE_INVALID" not in result.stderr
    assert _log_files(tmp_path)


def test_malformed_fixture_entry_is_rejected_before_any_session_log(tmp_path: Path) -> None:
    malformed = tmp_path / "malformed.json"
    malformed.write_text(json.dumps([{"foo": 1}]), encoding="utf-8")

    result = _cli(
        "run", "-p", "任务", "--provider", "mock", "--fixture", str(malformed), cwd=tmp_path
    )

    assert result.returncode == 2
    assert "FIXTURE_INVALID" in result.stderr
    assert _log_files(tmp_path) == []


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
        "run",
        "-p",
        "任务",
        "--provider",
        "mock",
        "--fixture",
        str(HELLO_SCENARIO),
        "--events",
        "jsonl",
        cwd=tmp_path,
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
        "run",
        "-p",
        "任务",
        "--provider",
        "mock",
        "--fixture",
        str(HELLO_SCENARIO),
        cwd=tmp_path,
        env=env,
    )

    log_text = _log_files(tmp_path)[0].read_text(encoding="utf-8")

    assert result.returncode == 0
    assert secret not in result.stdout
    assert secret not in result.stderr
    assert secret not in log_text


async def test_the_cli_installs_and_restores_the_sigint_handler(tmp_path: Path) -> None:
    before = signal.getsignal(signal.SIGINT)
    spy = _SigintSpyProvider()
    log = EventLog.create(session_dir=tmp_path, session_id="s-sigint")

    await cli_main._await_session(
        prompt="任务",
        provider=spy,
        settings=SessionSettings(workspace=tmp_path, provider_name="mock", max_turns=8),
        log=log,
    )

    assert len(spy.seen_handlers) == 1
    installed = spy.seen_handlers[0]
    assert callable(installed) and installed is not before
    assert signal.getsignal(signal.SIGINT) is before


class _SigintSpyProvider:
    """记录回合进行中 SIGINT 处理器是什么。"""

    def __init__(self) -> None:
        self.seen_handlers: list[object] = []

    async def generate(
        self, messages: object, tools: object, signal_event: asyncio.Event
    ) -> AssistantTurn:
        self.seen_handlers.append(signal.getsignal(signal.SIGINT))
        return AssistantTurn(content="done", finish_reason="stop")


def test_the_repo_hello_fixture_is_one_plain_reply(tmp_path: Path) -> None:
    assert HELLO_SCENARIO.is_file(), f"missing fixture: {HELLO_SCENARIO}"

    result = _cli(
        "run", "-p", "任务", "--provider", "mock", "--fixture", str(HELLO_SCENARIO), cwd=tmp_path
    )

    records = [
        json.loads(line)
        for line in _log_files(tmp_path)[0].read_text(encoding="utf-8").splitlines()
    ]
    responses = [record for record in records if record["type"] == "model/response"]

    assert result.returncode == 0
    assert len(responses) == 1
    assert responses[0]["payload"]["content"] == "hello from fixture"
    assert responses[0]["payload"]["finish_reason"] == "stop"


def test_an_unknown_sandbox_level_is_an_argument_error(tmp_path: Path) -> None:
    result = _cli(
        "run",
        "-p",
        "任务",
        "--provider",
        "mock",
        "--fixture",
        str(HELLO_SCENARIO),
        "--sandbox",
        "network-write",
        cwd=tmp_path,
    )

    assert result.returncode == 2
    # 「档位存在但取值非法」与「档位不存在」必须是两条不同的判据：前者报 invalid choice。
    assert "INVALID_ARGUMENT" in result.stderr
    assert "invalid choice" in result.stderr
    assert _log_files(tmp_path) == []


def test_sandbox_and_yes_are_accepted_without_changing_a_write_free_run(tmp_path: Path) -> None:
    result = _cli(
        "run",
        "-p",
        "任务",
        "--provider",
        "mock",
        "--fixture",
        str(HELLO_SCENARIO),
        "--sandbox",
        "read-only",
        "--yes",
        cwd=tmp_path,
    )

    assert result.returncode == 0
    assert len(_log_files(tmp_path)) == 1


def test_session_start_records_sandbox_approval_and_tools(tmp_path: Path) -> None:
    result = _cli(
        "run", "-p", "任务", "--provider", "mock", "--fixture", str(HELLO_SCENARIO), cwd=tmp_path
    )

    records = [
        json.loads(line)
        for line in _log_files(tmp_path)[0].read_text(encoding="utf-8").splitlines()
    ]
    payload = next(record["payload"] for record in records if record["type"] == "session/start")

    assert result.returncode == 0
    assert payload["sandbox"] == "workspace-write"
    assert payload["approval"] == "ask"
    # 注册表要到组 10 才有五个工具名；这里钉的是「tools 由注册表派生」这条通道。
    assert payload["tools"] == []
    assert "schema_version" not in payload


def test_sandbox_and_yes_flags_land_in_the_session_start_payload(tmp_path: Path) -> None:
    result = _cli(
        "run",
        "-p",
        "任务",
        "--provider",
        "mock",
        "--fixture",
        str(HELLO_SCENARIO),
        "--sandbox",
        "danger-full-access",
        "--yes",
        cwd=tmp_path,
    )

    records = [
        json.loads(line)
        for line in _log_files(tmp_path)[0].read_text(encoding="utf-8").splitlines()
    ]
    payload = next(record["payload"] for record in records if record["type"] == "session/start")

    assert result.returncode == 0
    assert payload["sandbox"] == "danger-full-access"
    assert payload["approval"] == "auto"
