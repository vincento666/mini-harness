"""seam ⑥：CLI 黑盒（子进程）。"""

from __future__ import annotations

import asyncio
import codecs
import json
import os
import signal
import socket
import sys
import time
from pathlib import Path

import pytest

from cli_blackbox import _cli, _cli_process
from mini_harness.cli import main as cli_main
from mini_harness.cli.main import STOP_REASONS_TO_EXIT_CODES, exit_code_for, sigint_handler
from mini_harness.config import build_registry
from mini_harness.events import EventLog
from mini_harness.loop import ENTRY_RUN, STOP_REASONS, RunOutcome, SessionSettings
from mini_harness.provider import AssistantTurn
from mini_harness.tools.bash_tools import shell_form
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
    assert len(STOP_REASONS) == 7
    assert "FENCE_DENIED" in STOP_REASONS
    assert STOP_REASONS_TO_EXIT_CODES["TOOL_CALLS"] == 0
    assert STOP_REASONS_TO_EXIT_CODES["MODEL_COMPLETED"] == 0
    assert STOP_REASONS_TO_EXIT_CODES["MAX_TURNS"] == 0
    assert STOP_REASONS_TO_EXIT_CODES["PROVIDER_ERROR"] == 1
    assert STOP_REASONS_TO_EXIT_CODES["FENCE_DENIED"] == 3
    assert STOP_REASONS_TO_EXIT_CODES["ABORTED"] == 5
    # M5 起 4 是可达码：不变量 D 的溢出结果映射到它。
    assert STOP_REASONS_TO_EXIT_CODES["CONTEXT_WINDOW_EXCEEDED"] == 4
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
    result = _cli("run", "-p", "任务", "--provider", "claude", cwd=tmp_path)

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


def test_a_fence_denial_exits_with_three(tmp_path: Path) -> None:
    """退出码 3 的 seam ⑥ 判据：档位轴拒绝一次写，整段 session 以 `FENCE_DENIED` 收尾。"""
    fixture = tmp_path / "fence.json"
    fixture.write_text(
        json.dumps(
            [
                {
                    "content": "写一个文件",
                    "finish_reason": "tool_calls",
                    "tool_calls": [
                        {
                            "id": "c1",
                            "name": "write",
                            "arguments": {"file_path": "a.md", "content": "x\n"},
                        }
                    ],
                },
                {"content": "算了", "finish_reason": "stop"},
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    result = _cli(
        "run",
        "-p",
        "任务",
        "--provider",
        "mock",
        "--fixture",
        str(fixture),
        "--sandbox",
        "read-only",
        cwd=tmp_path,
    )

    assert result.returncode == 3
    assert "SANDBOX_DENIES_WRITE" in result.stderr
    assert _log_files(tmp_path)


def test_happy_path_prints_session_id_and_writes_the_log(tmp_path: Path) -> None:
    result = _cli(
        "run", "-p", "任务", "--provider", "mock", "--fixture", str(HELLO_SCENARIO), cwd=tmp_path
    )

    session_id = result.stdout.strip()
    assert result.returncode == 0
    assert session_id
    assert (tmp_path / "sessions" / f"{session_id}.jsonl").is_file()


def test_a_one_shot_run_writes_exactly_one_segment(tmp_path: Path) -> None:
    """一次性 run 恰一个段：段的边界在盘上，其余逐行与 M5 之前相同。"""
    result = _cli(
        "run", "-p", "任务", "--provider", "mock", "--fixture", str(HELLO_SCENARIO), cwd=tmp_path
    )

    records = [
        json.loads(line)
        for line in _log_files(tmp_path)[0].read_text(encoding="utf-8").splitlines()
    ]
    segments = [record for record in records if record["type"].startswith("segment/")]

    assert result.returncode == 0
    assert [record["type"] for record in records] == [
        "session/start",
        "segment/start",
        "turn/start",
        "context/assembled",
        "model/request",
        "model/response",
        "turn/end",
        "segment/end",
        "session/end",
    ]
    assert segments[0]["payload"] == {"segment_id": "s1"}
    assert segments[1]["payload"] == {
        "segment_id": "s1",
        "stop_reason": "MODEL_COMPLETED",
        "turns": 1,
    }


def test_compaction_ratio_out_of_range_fails_before_a_session(tmp_path: Path) -> None:
    for config in (
        "compaction_retain_ratio = 0\n",
        "compaction_threshold_ratio = 1.1\n",
    ):
        (tmp_path / "mini.config.toml").write_text(config, encoding="utf-8")

        result = _cli(
            "run",
            "-p",
            "任务",
            "--provider",
            "mock",
            "--fixture",
            str(HELLO_SCENARIO),
            cwd=tmp_path,
        )

        assert result.returncode == 2
        assert "INVALID_ARGUMENT" in result.stderr
        assert _log_files(tmp_path) == []


def test_compaction_negative_tokens_fail_before_a_session(tmp_path: Path) -> None:
    for config in (
        "compaction_headroom_tokens = -1\n",
        "compaction_retain_tokens = -1\n",
    ):
        (tmp_path / "mini.config.toml").write_text(config, encoding="utf-8")

        result = _cli(
            "run",
            "-p",
            "任务",
            "--provider",
            "mock",
            "--fixture",
            str(HELLO_SCENARIO),
            cwd=tmp_path,
        )

        assert result.returncode == 2
        assert "INVALID_ARGUMENT" in result.stderr
        assert _log_files(tmp_path) == []


def test_compaction_boundary_values_are_accepted(tmp_path: Path) -> None:
    (tmp_path / "mini.config.toml").write_text(
        "compaction_threshold_ratio = 1\n"
        "compaction_retain_ratio = 1\n"
        "compaction_headroom_tokens = 0\n"
        "compaction_retain_tokens = 0\n",
        encoding="utf-8",
    )

    result = _cli(
        "run", "-p", "任务", "--provider", "mock", "--fixture", str(HELLO_SCENARIO), cwd=tmp_path
    )

    assert result.returncode == 0, result.stderr
    records = [
        json.loads(line)
        for line in _log_files(tmp_path)[0].read_text(encoding="utf-8").splitlines()
    ]
    payload = next(record["payload"] for record in records if record["type"] == "session/start")
    assert payload["compaction_threshold_ratio"] == 1.0
    assert payload["compaction_retain_ratio"] == 1.0
    assert payload["compaction_headroom_tokens"] == 0
    assert payload["compaction_retain_tokens"] == 0


def test_compaction_config_reaches_the_session_start_payload(tmp_path: Path) -> None:
    (tmp_path / "mini.config.toml").write_text(
        "compaction_threshold_ratio = 0.5\n"
        "compaction_headroom_tokens = 1000\n"
        "compaction_retain_ratio = 0.10\n"
        "compaction_retain_tokens = 3000\n",
        encoding="utf-8",
    )

    result = _cli(
        "run", "-p", "任务", "--provider", "mock", "--fixture", str(HELLO_SCENARIO), cwd=tmp_path
    )

    records = [
        json.loads(line)
        for line in _log_files(tmp_path)[0].read_text(encoding="utf-8").splitlines()
    ]
    payload = next(record["payload"] for record in records if record["type"] == "session/start")
    assert result.returncode == 0
    assert payload["compaction_threshold_ratio"] == 0.5
    assert payload["compaction_headroom_tokens"] == 1000
    assert payload["compaction_retain_ratio"] == 0.10
    assert payload["compaction_retain_tokens"] == 3000


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
        entry=ENTRY_RUN,
        provider=spy,
        settings=SessionSettings(workspace=tmp_path, provider_name="mock", max_turns=8),
        log=log,
        registry=build_registry(None),
    )

    assert len(spy.seen_handlers) == 1
    installed = spy.seen_handlers[0]
    assert callable(installed) and installed is not before
    assert signal.getsignal(signal.SIGINT) is before


def test_run_has_no_switch_that_changes_the_model_timeout(tmp_path: Path) -> None:
    """120 秒是实现常量：`minihns run` 的参数表里没有改变它的开关。"""
    result = _cli("run", "-p", "任务", "--provider", "mock", "--timeout", "5", cwd=tmp_path)

    assert result.returncode == 2
    assert "unrecognized arguments: --timeout" in result.stderr


_RUN_SWITCHES = {
    "-h",
    "--help",
    "-p",
    "--prompt",
    "--config",
    "--workspace",
    "--session-dir",
    "--provider",
    "--fixture",
    "--base-url",
    "--model",
    "--api-key-env",
    "--max-turns",
    "--window",
    "--reserve",
    "--append-system-prompt",
    "--events",
    "--sandbox",
    "--yes",
}


def test_the_run_argument_table_holds_no_switch_for_a_bounded_number(tmp_path: Path) -> None:
    """seam ⑥：`bash` 的 30 / 600、并发上限 8、模型超时 120 是实现常量，参数表里没有开关改它们。

    判据是整张表：列出来的就是全部（`-h` / `--help` 是 argparse 自带的）。哪天加一个
    `--bash-timeout` 或 `--max-parallel-tools`，这条立刻红——那正是要的信号。
    `--max-turns` 的默认值也是 8，那是回合上限，与并发上限无关。
    `--window` / `--reserve` 在这一栏：它们是规格里的窗口预算参数，不是实现常量的开关
    （触发线公式里那个 65536 才是实现常量，没有开关）。
    `--config` 是 M9 进表的：它是配置层的入口，规格里就有，不是给实现常量开的开关。
    """
    result = _cli("run", "--help", cwd=tmp_path)

    assert result.returncode == 0
    listed = {token.strip("[],") for token in result.stdout.split() if token.startswith("-")}
    assert listed == _RUN_SWITCHES


def test_a_bash_command_runs_end_to_end_in_the_cli(tmp_path: Path) -> None:
    """seam ⑥：`bash` 在真实 CLI 里跑通——命令在工作区根起、结果进日志、退出码 0。

    命令写成 `python <文件>`：`-c` 的引号在 `cmd.exe` 与 `/bin/sh` 里语义不同，用它判到的是
    shell 方言而不是 CLI 契约。`--yes` 是因为黑盒的 stdin 不是 tty，没有人可问。
    """
    (tmp_path / "make_marker.py").write_text("open('made.md', 'w').close()\n", encoding="utf-8")
    fixture = tmp_path / "bash.json"
    fixture.write_text(
        json.dumps(
            [
                {
                    "content": "跑一条真实检查命令",
                    "finish_reason": "tool_calls",
                    "tool_calls": [
                        {
                            "id": "c1",
                            "name": "bash",
                            "arguments": {"command": "python make_marker.py"},
                        }
                    ],
                },
                {
                    "content": "再读它留下的文件",
                    "finish_reason": "tool_calls",
                    "tool_calls": [
                        {"id": "c2", "name": "read", "arguments": {"file_path": "made.md"}}
                    ],
                },
                {"content": "完了", "finish_reason": "stop"},
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    result = _cli(
        "run", "-p", "任务", "--provider", "mock", "--fixture", str(fixture), "--yes", cwd=tmp_path
    )

    assert result.returncode == 0
    logs = _log_files(tmp_path)
    assert logs
    events = [json.loads(line) for line in logs[0].read_text(encoding="utf-8").splitlines()]
    outcomes = [
        str(event["payload"]["outcome"]) for event in events if event["type"] == "tool/result"
    ]
    assert outcomes == ["OK", "OK"]
    assert (tmp_path / "made.md").exists()


def test_a_bash_timeout_in_the_cli_is_a_result_word_and_the_run_continues(tmp_path: Path) -> None:
    """seam ⑥：`bash` 超时在真实 CLI 里塌成结果词，回合继续走到正常收尾，退出码 0。

    Windows 也跑得动：命令是 `python <文件>`、超时用 `timeout_seconds: 1`。M3 原本只有
    Linux 侧的 SIGINT 黑盒，超时这条两端都要有——它判的是超时收尾，不是打断收尾。
    `--yes` 是因为黑盒的 stdin 不是 tty，而 `bash` 算会改动的工具。
    """
    (tmp_path / "loop.py").write_text("import time\n\nwhile True:\n    time.sleep(0.1)\n", "utf-8")
    (tmp_path / "a.md").write_text("甲\n", encoding="utf-8")
    fixture = tmp_path / "timeout.json"
    fixture.write_text(
        json.dumps(
            [
                {
                    "content": "跑一条不会自己停的命令",
                    "finish_reason": "tool_calls",
                    "tool_calls": [
                        {
                            "id": "c1",
                            "name": "bash",
                            "arguments": {"command": "python loop.py", "timeout_seconds": 1},
                        }
                    ],
                },
                {
                    "content": "超时之后回合继续",
                    "finish_reason": "tool_calls",
                    "tool_calls": [
                        {"id": "c2", "name": "read", "arguments": {"file_path": "a.md"}}
                    ],
                },
                {"content": "完了", "finish_reason": "stop"},
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    result = _cli(
        "run", "-p", "任务", "--provider", "mock", "--fixture", str(fixture), "--yes", cwd=tmp_path
    )

    assert result.returncode == 0
    logs = _log_files(tmp_path)
    assert logs
    events = [json.loads(line) for line in logs[0].read_text(encoding="utf-8").splitlines()]
    outcomes = [
        (str(event["payload"]["tool_call_id"]), str(event["payload"]["outcome"]))
        for event in events
        if event["type"] == "tool/result"
    ]
    assert outcomes == [("c1", "TOOL_TIMEOUT"), ("c2", "OK")]
    assert [
        event["payload"]["tool_call_id"] for event in events if event["type"] == "tool/cancelled"
    ] == ["c1"]
    assert events[-1]["type"] == "session/end"


@pytest.mark.skipif(
    sys.platform == "win32",
    reason=(
        "Windows 的 Ctrl-C 黑盒不在 M3："
        "缺口记进 docs/verification/m3-bash-concurrency-timeout-manual.md"
    ),
)
def test_sigint_in_a_real_subprocess_exits_with_five(tmp_path: Path) -> None:
    """seam ⑥：真实子进程里的 SIGINT → 退出码 5，日志以 `error/abort` 与 ABORTED 收尾。

    被打断的是一条正在执行的 `bash`：`sleep 30` 在 POSIX 下待在自己的进程组里，
    SIGINT 只发给 harness 那个进程，命令本身要靠 harness 收掉。
    """
    fixture = tmp_path / "sleep.json"
    fixture.write_text(
        json.dumps(
            [
                {
                    "content": "跑一条挂很久的命令",
                    "finish_reason": "tool_calls",
                    "tool_calls": [
                        {
                            "id": "c1",
                            "name": "bash",
                            "arguments": {"command": "sleep 30", "timeout_seconds": 30},
                        }
                    ],
                },
                {"content": "不该走到这里", "finish_reason": "stop"},
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    process = _cli_process(
        "run", "-p", "任务", "--provider", "mock", "--fixture", str(fixture), "--yes", cwd=tmp_path
    )
    for _ in range(200):
        logs = _log_files(tmp_path)
        if logs and '"tool/call"' in logs[0].read_text(encoding="utf-8"):
            break
        time.sleep(0.1)
    else:
        process.kill()
        pytest.fail("子进程没有进入工具执行段")

    process.send_signal(signal.SIGINT)
    _, stderr = process.communicate(timeout=30)

    assert process.returncode == 5
    assert "ABORTED" in stderr
    records = [json.loads(line) for line in _log_files(tmp_path)[0].read_text("utf-8").splitlines()]
    types = [record["type"] for record in records]
    assert types.count("tool/call") == 1
    assert types.count("tool/cancelled") == 1
    outcomes = [r["payload"]["outcome"] for r in records if r["type"] == "tool/result"]
    assert outcomes == ["TOOL_CANCELLED"]
    assert types[-4:] == ["error/abort", "turn/end", "segment/end", "session/end"]
    assert records[-1]["payload"]["stop_reason"] == "ABORTED"


_TICKER = "import time\n\nfor _ in range(100):\n    time.sleep(0.1)\n"


def _hard_kill_a_run(tmp_path: Path) -> Path:
    """起一条真实 `minihns run`，轮询到那条挂着的命令的 `tool/call` 落盘就硬杀，返回日志路径。

    杀点由日志定位：`tool/call` 出现时命令一定在跑。命令自己会在十秒后结束，硬杀之后即使
    它成了孤儿也不会永远留着。Windows 的 `Popen.kill()` 与 Linux CI 的 `SIGKILL` 是同一个动作。
    """
    (tmp_path / "a.md").write_text("甲\n", encoding="utf-8")
    (tmp_path / "ticker.py").write_text(_TICKER, encoding="utf-8")
    fixture = tmp_path / "hardkill.json"
    fixture.write_text(
        json.dumps(
            [
                {
                    "content": "先读一个文件，再跑一条挂着的命令",
                    "finish_reason": "tool_calls",
                    "tool_calls": [
                        {"id": "c1", "name": "read", "arguments": {"file_path": "a.md"}},
                        {
                            "id": "c2",
                            "name": "bash",
                            "arguments": {"command": "python ticker.py", "timeout_seconds": 30},
                        },
                    ],
                },
                {"content": "不该走到这里", "finish_reason": "stop"},
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    process = _cli_process(
        "run", "-p", "任务", "--provider", "mock", "--fixture", str(fixture), "--yes", cwd=tmp_path
    )
    for _ in range(400):
        logs = _log_files(tmp_path)
        if logs:
            try:
                records = [json.loads(line) for line in logs[0].read_text("utf-8").splitlines()]
            except json.JSONDecodeError:
                records = []
            if any(
                record["type"] == "tool/call" and record["payload"]["tool_call_id"] == "c2"
                for record in records
            ):
                break
        time.sleep(0.05)
    else:
        process.kill()
        pytest.fail("子进程没有进入工具执行段")

    process.kill()
    process.wait(timeout=30)
    return _log_files(tmp_path)[0]


def test_a_hard_kill_leaves_no_half_written_line(tmp_path: Path) -> None:
    """seam ⑥：进程被硬杀之后，日志里已落盘的每一行都还是完整的一条记录。

    断言只挑与杀点无关的性质：每行独立可解析、文件以换行结尾、落了的 `tool/result` 字段齐全。
    """
    log_path = _hard_kill_a_run(tmp_path)

    text = log_path.read_text(encoding="utf-8")
    assert text.endswith("\n"), "最后一行也是完整的一条，不是半行"
    records = [json.loads(line) for line in text.splitlines()]
    types = [record["type"] for record in records]
    results = [record for record in records if record["type"] == "tool/result"]
    assert results, "先完成的那条读已经落了一条完整结果"
    for record in results:
        assert {"turn_id", "tool_call_id", "outcome", "content"} <= set(record["payload"])
    assert "session/end" not in types, "内核被杀在半路，没人写收尾"


def test_a_hard_killed_log_replays_without_appending(tmp_path: Path) -> None:
    """seam ⑥：被硬杀的日志照样能逐点重放，且 replay 不往它后面追加任何东西。"""
    log_path = _hard_kill_a_run(tmp_path)
    before = log_path.read_bytes()

    replay = _cli("replay", log_path.stem, cwd=tmp_path)

    assert replay.returncode == 0
    assert "verified seq=" in replay.stdout
    assert log_path.read_bytes() == before


class _SigintSpyProvider:
    """记录回合进行中 SIGINT 处理器是什么。"""

    def __init__(self) -> None:
        self.seen_handlers: list[object] = []

    async def generate(
        self,
        messages: object,
        tools: object,
        signal_event: asyncio.Event,
        on_delta: object = None,
        on_reasoning: object = None,
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


def test_session_start_records_the_platform_facts(tmp_path: Path) -> None:
    """`session/start` 记下 os 与 shell，且与 bash 实际执行用的那条一致（ADR-0029）。"""
    result = _cli(
        "run", "-p", "任务", "--provider", "mock", "--fixture", str(HELLO_SCENARIO), cwd=tmp_path
    )

    records = [
        json.loads(line)
        for line in _log_files(tmp_path)[0].read_text(encoding="utf-8").splitlines()
    ]
    payload = next(record["payload"] for record in records if record["type"] == "session/start")

    assert result.returncode == 0
    assert payload["platform"] == {"os": os.name, "shell": shell_form()}


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def test_the_three_entries_record_the_same_platform_facts(tmp_path: Path) -> None:
    """run / chat / serve 同一条装配路：三份 `session/start` 带同一份平台事实（ADR-0029）。"""
    expected = {"os": os.name, "shell": shell_form()}
    extra = {"run": [], "chat": [], "serve": ["--http", "--port", str(_free_port())]}

    for entry, flags in extra.items():
        cwd = tmp_path / entry
        cwd.mkdir()
        args = [entry, *flags]
        if entry != "chat":
            args += ["-p", "任务"]
        result = _cli(*args, "--provider", "mock", "--fixture", str(HELLO_SCENARIO), cwd=cwd)

        records = [
            json.loads(line) for line in _log_files(cwd)[0].read_text(encoding="utf-8").splitlines()
        ]
        payload = next(record["payload"] for record in records if record["type"] == "session/start")

        assert result.returncode == 0, (entry, result.stderr)
        assert payload["platform"] == expected, entry


def test_the_three_entries_still_write_the_same_payload(tmp_path: Path) -> None:
    """装配抽成库之后，run / chat / serve 的 `session/start` 仍是同一份事实（H1 task 1.3）。

    `entry` 与 `prompt` 是入口自己的两格：run 与 serve 带 prompt，chat 的 prompt 是空串。
    其余字段逐字段相等——任一入口少写或多写一格，都说明装配路被分叉了。
    """
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    extra = {"run": [], "chat": [], "serve": ["--http", "--port", str(_free_port())]}
    payloads: dict[str, dict[str, object]] = {}

    for entry, flags in extra.items():
        session_dir = tmp_path / entry / "sessions"
        args = [
            entry,
            *flags,
            "--provider",
            "mock",
            "--fixture",
            str(HELLO_SCENARIO),
            "--workspace",
            str(workspace),
            "--session-dir",
            str(session_dir),
        ]
        if entry == "chat":
            result = _cli(*args, cwd=workspace, stdin_text="任务\n")
        else:
            result = _cli(*args, "-p", "任务", cwd=workspace)

        log = next(session_dir.glob("*.jsonl"))
        records = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
        payloads[entry] = next(
            record["payload"] for record in records if record["type"] == "session/start"
        )
        assert result.returncode == 0, (entry, result.stderr)

    normalized = {
        entry: {key: value for key, value in payload.items() if key not in {"entry", "prompt"}}
        for entry, payload in payloads.items()
    }
    assert normalized["run"] == normalized["chat"] == normalized["serve"]
    assert [payloads[entry]["entry"] for entry in ("run", "chat", "serve")] == [
        "run",
        "chat",
        "serve",
    ]
    assert payloads["run"]["prompt"] == "任务"
    assert payloads["chat"]["prompt"] == ""
    # `serve` 仍是一次性入口，prompt 由 `-p` 给；只有 chat 与 H1 的 host 把它留空。
    assert payloads["serve"]["prompt"] == "任务"
    assert set(payloads["run"]) == {
        "entry",
        "workspace",
        "provider",
        "max_turns",
        "append_system_prompt",
        "prompt",
        "sandbox",
        "approval",
        "window",
        "reserve",
        "compaction_threshold_ratio",
        "compaction_headroom_tokens",
        "compaction_retain_ratio",
        "compaction_retain_tokens",
        "tools",
        "platform",
    }


def test_the_platform_facts_are_not_a_cli_flag(tmp_path: Path) -> None:
    """平台事实没有开关：`--help` 里不出现它，`--platform` 是不认识的参数（ADR-0029）。"""
    help_result = _cli("run", "--help", cwd=tmp_path)
    assert "platform" not in help_result.stdout

    rejected = _cli("run", "-p", "任务", "--platform", "posix", cwd=tmp_path)
    assert rejected.returncode == 2
    assert "unrecognized arguments" in rejected.stderr
    assert _log_files(tmp_path) == []


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
    # 六个名字来自注册表：session/start 的 tools 由它派生，不是另立一份清单。
    assert payload["tools"] == ["read", "write", "edit", "glob", "grep", "bash"]
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


def _session_start(log_path: Path) -> dict[str, object]:
    records = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()]
    started: dict[str, object] = next(
        record["payload"] for record in records if record["type"] == "session/start"
    )
    return started


def test_the_default_window_and_reserve_land_in_the_session_start_payload(tmp_path: Path) -> None:
    _cli("run", "-p", "任务", "--provider", "mock", "--fixture", str(HELLO_SCENARIO), cwd=tmp_path)

    payload = _session_start(_log_files(tmp_path)[0])
    assert payload["window"] == 128000
    assert payload["reserve"] == 8192


def test_a_run_records_which_entry_opened_the_session(tmp_path: Path) -> None:
    """seam ⑥：`entry` 的两个值各有判据——`run` 这一半在这儿，`chat` 那一半在 `test_cli_chat.py`。"""
    _cli(
        "run",
        "-p",
        "任务",
        "--provider",
        "mock",
        "--fixture",
        str(HELLO_SCENARIO),
        cwd=tmp_path,
    )

    assert _session_start(_log_files(tmp_path)[0])["entry"] == "run"


def test_window_and_reserve_flags_land_in_the_session_start_payload(tmp_path: Path) -> None:
    """规格 scenario「窗口与预留进 payload」。这条只看 payload：两个数都是合法取值，
    会话正常收尾；窗口小到每次装配都越线的那条判据在下面。"""
    _cli(
        "run",
        "-p",
        "任务",
        "--provider",
        "mock",
        "--fixture",
        str(HELLO_SCENARIO),
        "--window",
        "131072",
        "--reserve",
        "4096",
        cwd=tmp_path,
    )

    payload = _session_start(_log_files(tmp_path)[0])
    assert payload["window"] == 131072
    assert payload["reserve"] == 4096


@pytest.mark.parametrize("flag", ["--window", "--reserve"])
def test_a_budget_argument_below_one_is_a_parameter_error_with_no_log(
    tmp_path: Path, flag: str
) -> None:
    result = _cli(
        "run",
        "-p",
        "任务",
        "--provider",
        "mock",
        "--fixture",
        str(HELLO_SCENARIO),
        flag,
        "0",
        cwd=tmp_path,
    )

    assert result.returncode == 2
    assert "INVALID_ARGUMENT" in result.stderr
    # 参数错误发生在 session 开始之前：连日志都不该有。
    assert _log_files(tmp_path) == []


def test_a_window_that_leaves_no_pressure_budget_is_a_parameter_error(tmp_path: Path) -> None:
    """窗口减去预留之后没有压力预算：配置期就失败，连日志都不建（ADR-0019）。"""
    result = _cli(
        "run",
        "-p",
        "任务",
        "--provider",
        "mock",
        "--fixture",
        str(HELLO_SCENARIO),
        "--window",
        "4096",
        "--reserve",
        "8192",
        cwd=tmp_path,
    )

    assert result.returncode == 2
    assert "INVALID_ARGUMENT" in result.stderr
    # stderr 要点出那两个数：窗口与预留。
    assert all(number in result.stderr for number in ("4096", "8192"))
    assert _log_files(tmp_path) == []


def test_a_window_that_leaves_exactly_zero_pressure_budget_is_a_parameter_error(
    tmp_path: Path,
) -> None:
    """`W - O` 恰为 0 也是「没有压力预算」：什么都装不下。"""
    result = _cli(
        "run",
        "-p",
        "任务",
        "--provider",
        "mock",
        "--fixture",
        str(HELLO_SCENARIO),
        "--window",
        "4000",
        "--reserve",
        "4000",
        cwd=tmp_path,
    )

    assert result.returncode == 2
    assert "INVALID_ARGUMENT" in result.stderr
    assert all(number in result.stderr for number in ("4000", "4000"))
    assert _log_files(tmp_path) == []


def test_the_smallest_window_with_a_positive_trigger_line_runs(tmp_path: Path) -> None:
    """触发线为正的最小窗口照跑：`session/start` 里 `window` 与 `reserve` 是传进去的那两个数。"""
    result = _cli(
        "run",
        "-p",
        "任务",
        "--provider",
        "mock",
        "--fixture",
        str(HELLO_SCENARIO),
        "--window",
        "70000",
        "--reserve",
        "4096",
        cwd=tmp_path,
    )

    payload = _session_start(_log_files(tmp_path)[0])
    assert result.returncode == 0
    assert payload["window"] == 70000
    assert payload["reserve"] == 4096


def test_a_window_with_a_zero_trigger_line_runs(tmp_path: Path) -> None:
    """触发线为 0 不是配置错误：压力预算 `W - O` 还在，会话照跑，退出码 0。

    窗口 4000 / 预留 100 的触发线是 0（`4000 - 100 - 65536` 为负）、保留预算 640，
    压力预算 3900。旧口径里这种窗口在配置期就被拒掉。
    """
    result = _cli(
        "run",
        "-p",
        "任务",
        "--provider",
        "mock",
        "--fixture",
        str(HELLO_SCENARIO),
        "--window",
        "4000",
        "--reserve",
        "100",
        cwd=tmp_path,
    )

    assert result.returncode == 0
    payload = _session_start(_log_files(tmp_path)[0])
    assert payload["window"] == 4000
    assert payload["reserve"] == 100


# 压力预算 3900 个 token（15600 个字符）：20000 个字符约 5000 个估算 token，装不下。
# 对话体里又无可遮蔽的内容——prompt 在 `session/start` 里，受保护、不能遮蔽。
_TIGHT_WINDOW = "4000"
_TIGHT_RESERVE = "100"
_OVERFLOW_PROMPT = "任务" * 10000


# 死区窗口：`--window 70000 --reserve 100` 的触发线 4364 比保留预算 11200 还小。
# 24000 个字符约 6000 个估算 token，落在 (4364, 11200]：越线、无可遮蔽，压力预算 69900 装得下。
_DEAD_ZONE_WINDOW = "70000"
_DEAD_ZONE_RESERVE = "100"
_DEAD_ZONE_PROMPT = "任务" * 12000


def test_a_dead_zone_window_still_holds_a_conversation(tmp_path: Path) -> None:
    """触发线比保留预算还小的窗口不是运行期撞墙：越线、无可遮蔽，仍照常装配并跑完。"""
    result = _cli(
        "run",
        "-p",
        _DEAD_ZONE_PROMPT,
        "--provider",
        "mock",
        "--fixture",
        str(HELLO_SCENARIO),
        "--window",
        _DEAD_ZONE_WINDOW,
        "--reserve",
        _DEAD_ZONE_RESERVE,
        cwd=tmp_path,
    )

    lines = _log_files(tmp_path)[0].read_text(encoding="utf-8").splitlines()
    types = [json.loads(line)["type"] for line in lines]

    assert result.returncode == 0
    assert "context/assembled" in types
    assert "model/request" in types
    assert "error/context" not in types
    assert "compaction/summary" not in types


def test_a_run_that_cannot_fit_its_window_exits_four_with_an_error_context(tmp_path: Path) -> None:
    """窗口小到无可遮蔽：溢出收尾是结果，退出码 4，日志里有 `error/context`。"""
    result = _cli(
        "run",
        "-p",
        _OVERFLOW_PROMPT,
        "--provider",
        "mock",
        "--fixture",
        str(HELLO_SCENARIO),
        "--window",
        _TIGHT_WINDOW,
        "--reserve",
        _TIGHT_RESERVE,
        cwd=tmp_path,
    )

    lines = _log_files(tmp_path)[0].read_text(encoding="utf-8").splitlines()
    records = [json.loads(line) for line in lines]
    types = [record["type"] for record in records]

    assert result.returncode == 4
    notes = [line for line in result.stderr.splitlines() if "CONTEXT_WINDOW_EXCEEDED" in line]
    assert len(notes) == 1, "非 0 退出在 stderr 上该有一行"
    assert notes[0].count("CONTEXT_WINDOW_EXCEEDED") == 1
    detail = str(records[-4]["payload"]["detail"])
    assert detail != "", "日志里那条 detail 非空"
    assert detail in notes[0], "那一行含日志里那句非空 detail"
    assert notes[0] not in result.stdout, "stdout 归 session id，那一行不在它上面"
    assert notes[0] not in "\n".join(lines), "那一行不写进事件日志"
    assert types[-4:] == ["error/context", "turn/end", "segment/end", "session/end"]
    assert "model/request" not in types
    assert records[-4]["payload"]["code"] == "CONTEXT_WINDOW_EXCEEDED"


def test_a_log_that_overflowed_before_any_assembly_still_replays(tmp_path: Path) -> None:
    """溢出发生在第一次装配之前：那份日志照样可重放，退出码 0。"""
    run = _cli(
        "run",
        "-p",
        _OVERFLOW_PROMPT,
        "--provider",
        "mock",
        "--fixture",
        str(HELLO_SCENARIO),
        "--window",
        _TIGHT_WINDOW,
        "--reserve",
        _TIGHT_RESERVE,
        cwd=tmp_path,
    )
    assert run.returncode == 4

    log_path = _log_files(tmp_path)[0]
    replay = _cli("replay", log_path.stem, "--session-dir", str(log_path.parent), cwd=tmp_path)
    printed = replay.stdout.splitlines()

    assert replay.returncode == 0
    assert "REPLAY_MISMATCH" not in replay.stderr
    # 没有装配点要说清，不能靠「一条都没验」冒充验过。
    assert any("没有装配点" in line for line in printed)
    assert any(
        line.startswith("turn ") and line.endswith(": CONTEXT_WINDOW_EXCEEDED") for line in printed
    )
    assert not any(line.startswith("final_context") for line in printed)
