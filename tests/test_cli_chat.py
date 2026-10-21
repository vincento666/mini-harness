"""seam ⑥：`minihns chat` 的黑盒（真实子进程）。"""

from __future__ import annotations

import asyncio
import json
import re
import signal
import sys
import time
from pathlib import Path
from typing import Any

import pytest

from cli_blackbox import _cli, _cli_process
from mini_harness.cli.main import _chat_sigint_handler, _ChatSignals
from paths import WRITE_OUTSIDE_SCENARIO


def _log_files(cwd: Path) -> list[Path]:
    session_dir = cwd / "sessions"
    if not session_dir.is_dir():
        return []
    return sorted(session_dir.glob("*.jsonl"))


def _records(cwd: Path) -> list[dict[str, Any]]:
    """chat 的判据都假定「一次 chat 恰有一份日志」，这里把它钉死。"""
    logs = _log_files(cwd)
    assert len(logs) == 1, f"一次 chat 应当恰有一份 session 日志，实际 {len(logs)} 份"
    return [
        json.loads(line)
        for line in logs[0].read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _types(cwd: Path) -> list[str]:
    return [str(record["type"]) for record in _records(cwd)]


def _fixture(cwd: Path, name: str, entries: list[dict[str, Any]]) -> str:
    path = cwd / name
    path.write_text(json.dumps(entries, ensure_ascii=False), encoding="utf-8")
    return str(path)


def _chat(*args: str, cwd: Path, stdin_text: str) -> Any:
    return _cli("chat", "--provider", "mock", *args, cwd=cwd, stdin_text=stdin_text)


def _flags(help_text: str) -> set[str]:
    """从 `--help` 的输出里取出所有选项串：参数表比对靠这个，不靠手抄一份清单。"""
    return set(re.findall(r"(?<![^\s])-{1,2}[a-z][a-z0-9-]*", help_text))


def test_chat_shares_the_flag_table_and_the_layering(tmp_path: Path) -> None:
    """seam ⑥：chat 与 run 共用同一份参数表与同一套层叠；`entry` 是 `chat`、`prompt` 是空串。"""
    (tmp_path / "mini.config.toml").write_text(
        'max_turns = 2\ntools = ["read"]\n', encoding="utf-8"
    )
    fixture = _fixture(tmp_path, "one.json", [{"content": "回复", "finish_reason": "stop"}])

    result = _chat("--fixture", fixture, cwd=tmp_path, stdin_text="第一条\n")

    assert result.returncode == 0
    payload = next(
        record["payload"] for record in _records(tmp_path) if record["type"] == "session/start"
    )
    assert payload["max_turns"] == 2
    assert payload["tools"] == ["read"]
    assert payload["entry"] == "chat"
    assert payload["prompt"] == ""


def test_two_inputs_make_one_log_two_segments_and_two_user_messages(tmp_path: Path) -> None:
    """seam ⑥：两条输入一份日志；每条输入是一条 `user/message`，位置在段边界之内。"""
    fixture = _fixture(
        tmp_path,
        "two.json",
        [
            {"content": "回复一", "finish_reason": "stop"},
            {"content": "回复二", "finish_reason": "stop"},
        ],
    )

    result = _chat("--fixture", fixture, cwd=tmp_path, stdin_text="第一条\n第二条\n")

    assert result.returncode == 0
    records = _records(tmp_path)
    types = [str(record["type"]) for record in records]
    assert types.count("session/start") == 1
    assert types.count("session/end") == 1
    assert types.count("segment/start") == 2
    assert types.count("segment/end") == 2
    # `user/message` 在 `segment/start` 之后、该段第一个 `turn/start` 之前。
    assert types[:4] == ["session/start", "segment/start", "user/message", "turn/start"]
    messages = [record["payload"] for record in records if record["type"] == "user/message"]
    assert [message["content"] for message in messages] == ["第一条", "第二条"]
    assert [message["segment_id"] for message in messages] == ["s1", "s2"]
    assert records[-1]["type"] == "session/end"
    assert records[-1]["payload"]["stop_reason"] == "MODEL_COMPLETED"
    # `session/end.turns` 是会话跑掉的回合数，不是回合编号。
    assert records[-1]["payload"]["turns"] == 2


def test_an_empty_stdin_is_a_legal_session(tmp_path: Path) -> None:
    """seam ⑥：stdin 立刻 EOF 也是一份合法会话——没有段，也没有回合。"""
    fixture = _fixture(tmp_path, "unused.json", [{"content": "不该出现", "finish_reason": "stop"}])

    result = _chat("--fixture", fixture, cwd=tmp_path, stdin_text="")

    assert result.returncode == 0
    assert _types(tmp_path) == ["session/start", "session/end"]
    assert _records(tmp_path)[-1]["payload"]["turns"] == 0


def test_blank_input_writes_no_record_and_opens_no_segment(tmp_path: Path) -> None:
    """seam ⑥：空白输入既不写 `user/message`，也不开段。"""
    fixture = _fixture(
        tmp_path,
        "two.json",
        [
            {"content": "回复一", "finish_reason": "stop"},
            {"content": "回复二", "finish_reason": "stop"},
        ],
    )

    result = _chat("--fixture", fixture, cwd=tmp_path, stdin_text="   \n第一条\n\n第二条\n")

    assert result.returncode == 0
    records = _records(tmp_path)
    assert [str(record["type"]) for record in records].count("segment/start") == 2
    messages = [record["payload"] for record in records if record["type"] == "user/message"]
    assert [message["content"] for message in messages] == ["第一条", "第二条"]


def test_a_segment_that_uses_up_max_turns_returns_to_the_prompt(tmp_path: Path) -> None:
    """seam ⑥：`max_turns` 是段内上限；用完回到提示符，下一条输入额度完整、编号不重置。"""
    entries = [
        {
            "content": f"第 {index} 次读",
            "finish_reason": "tool_calls",
            "tool_calls": [{"id": f"c{index}", "name": "read", "arguments": {"file_path": "a.md"}}],
        }
        for index in range(1, 5)
    ]
    fixture = _fixture(tmp_path, "exhaust.json", entries)

    result = _chat(
        "--fixture", fixture, "--max-turns", "2", cwd=tmp_path, stdin_text="第一条\n第二条\n"
    )

    assert result.returncode == 0
    records = _records(tmp_path)
    segments = [record["payload"] for record in records if record["type"] == "segment/end"]
    assert [segment["segment_id"] for segment in segments] == ["s1", "s2"]
    assert [segment["stop_reason"] for segment in segments] == ["MAX_TURNS", "MAX_TURNS"]
    assert [segment["turns"] for segment in segments] == [2, 2]
    # 回合编号在整个会话里连续：第二个段从 t3 起，不重置。
    turn_ids = [
        record["payload"]["turn_id"] for record in records if record["type"] == "turn/start"
    ]
    assert turn_ids == ["t1", "t2", "t3", "t4"]
    assert records[-1]["type"] == "session/end"


def test_a_segment_failure_does_not_end_the_session(tmp_path: Path) -> None:
    """seam ⑥：围栏拒绝落在盘上，会话继续；EOF 收尾是退出码 0。"""
    result = _chat("--fixture", str(WRITE_OUTSIDE_SCENARIO), cwd=tmp_path, stdin_text="越界写\n")

    assert result.returncode == 0
    records = _records(tmp_path)
    types = [str(record["type"]) for record in records]
    assert "error/fence" in types
    assert types[-2:] == ["segment/end", "session/end"]
    assert records[-2]["payload"]["stop_reason"] == "FENCE_DENIED"
    assert records[-1]["payload"]["stop_reason"] == "MODEL_COMPLETED"


_WINDOWS_CTRL_C_REASON = (
    "Windows 的 Ctrl-C 黑盒不在本项目范围：缺口沿用 M3 的边界，"
    "记进 docs/verification/m3-bash-concurrency-timeout-manual.md"
)


def _wait_until_log_contains(tmp_path: Path, process: Any, marker: str, what: str) -> None:
    """等子进程把某个标记写进日志：黑盒里的「等到它真跑到那儿」。"""
    for _ in range(200):
        logs = _log_files(tmp_path)
        if logs and marker in logs[0].read_text(encoding="utf-8"):
            return
        time.sleep(0.1)
    process.kill()
    pytest.fail(f"子进程没有{what}")


async def test_the_chat_handler_cancels_the_running_segment() -> None:
    """seam ⑥：段在跑时 Ctrl-C 只取消当前段——这条不看平台脸色。"""
    cancel = asyncio.Event()
    signals = _ChatSignals(active=cancel)

    _chat_sigint_handler(signals)(signal.SIGINT, None)
    await asyncio.sleep(0)

    assert cancel.is_set()


async def test_the_chat_handler_ends_the_session_when_no_segment_is_running() -> None:
    """seam ⑥：提示符上 Ctrl-C 是「结束会话」，不是取消——这条也不看平台脸色。"""
    signals = _ChatSignals(active=None)

    with pytest.raises(KeyboardInterrupt):
        _chat_sigint_handler(signals)(signal.SIGINT, None)


@pytest.mark.skipif(sys.platform == "win32", reason=_WINDOWS_CTRL_C_REASON)
def test_sigint_mid_segment_cancels_the_segment_not_the_session(tmp_path: Path) -> None:
    """seam ⑥：段进行中的 SIGINT 只终止当前段，进程不退出，会话回到提示符。"""
    fixture = _fixture(
        tmp_path,
        "sleep.json",
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
            {"content": "第二条输入的回复", "finish_reason": "stop"},
        ],
    )

    process = _cli_process(
        "chat",
        "--provider",
        "mock",
        "--fixture",
        str(fixture),
        "--yes",
        cwd=tmp_path,
        keep_stdin_open=True,
    )
    assert process.stdin is not None
    process.stdin.write("第一条\n")
    process.stdin.flush()

    _wait_until_log_contains(tmp_path, process, '"tool/call"', "进入工具执行段")
    process.send_signal(signal.SIGINT)
    _wait_until_log_contains(tmp_path, process, '"segment/end"', "写出被取消段的段边界")

    assert process.poll() is None, "取消当前段之后进程不该退出"

    process.stdin.write("第二条\n")
    process.stdin.flush()
    process.communicate(timeout=30)

    assert process.returncode == 0
    records = _records(tmp_path)
    types = [str(record["type"]) for record in records]
    assert "error/abort" in types
    segments = [record["payload"] for record in records if record["type"] == "segment/end"]
    assert segments[0] == {"segment_id": "s1", "stop_reason": "ABORTED", "turns": 1}
    # 会话还在：`session/end` 只在 stdin 关闭之后出现一次。
    assert types.count("session/end") == 1
    assert types[-2:] == ["segment/end", "session/end"]
    assert records[-1]["payload"]["stop_reason"] == "MODEL_COMPLETED"


@pytest.mark.skipif(sys.platform == "win32", reason=_WINDOWS_CTRL_C_REASON)
def test_sigint_at_the_prompt_ends_the_session_cleanly(tmp_path: Path) -> None:
    """seam ⑥：提示符上的 SIGINT 与 EOF 同一条路——写 `session/end`、退出码 0。"""
    fixture = _fixture(tmp_path, "unused.json", [{"content": "不该出现", "finish_reason": "stop"}])

    process = _cli_process(
        "chat", "--provider", "mock", "--fixture", str(fixture), cwd=tmp_path, keep_stdin_open=True
    )
    _wait_until_log_contains(
        tmp_path, process, '"session/start"', "在第一条输入之前写出 session/start"
    )

    process.send_signal(signal.SIGINT)
    process.communicate(timeout=30)

    assert process.returncode == 0
    assert _types(tmp_path) == ["session/start", "session/end"]


def test_stdout_carries_only_model_reply_text_and_the_prompt(tmp_path: Path) -> None:
    """seam ⑥：stdout 是日志的一个投影——只有模型回复正文与提示符。"""
    (tmp_path / "a.md").write_text("工具结果的内容不该出现在 stdout\n", encoding="utf-8")
    fixture = _fixture(
        tmp_path,
        "tool.json",
        [
            {
                "content": "先读一下",
                "finish_reason": "tool_calls",
                "tool_calls": [{"id": "c1", "name": "read", "arguments": {"file_path": "a.md"}}],
            },
            {"content": "这是回复正文", "finish_reason": "stop"},
        ],
    )

    result = _chat("--fixture", fixture, cwd=tmp_path, stdin_text="读一下 a.md\n")

    assert result.returncode == 0
    assert result.stdout.splitlines() == ["> ", "先读一下", "这是回复正文", "> "]
    assert "工具结果的内容不该出现在 stdout" not in result.stdout
    assert "context/assembled" not in result.stdout


def test_an_overflowed_segment_returns_to_the_prompt(tmp_path: Path) -> None:
    """seam ⑥：溢出塌成回合级收尾，会话继续，下一条输入开新段（ADR-0019）。"""
    fixture = _fixture(
        tmp_path,
        "two.json",
        [
            {"content": "摘要一", "finish_reason": "stop"},
            {"content": "摘要二", "finish_reason": "stop"},
        ],
    )

    result = _chat(
        "--fixture",
        fixture,
        "--window",
        "66000",
        "--reserve",
        "100",
        "--append-system-prompt",
        "说明" * 1000,
        cwd=tmp_path,
        stdin_text="第一条\n第二条\n",
    )

    assert result.returncode == 0
    records = _records(tmp_path)
    types = [str(record["type"]) for record in records]
    assert types.count("error/context") == 2
    # 溢出走自己那条路，不冒充 provider 失败。
    assert "error/model" not in types
    segments = [record["payload"] for record in records if record["type"] == "segment/end"]
    assert [segment["segment_id"] for segment in segments] == ["s1", "s2"]
    assert [segment["stop_reason"] for segment in segments] == [
        "CONTEXT_WINDOW_EXCEEDED",
        "CONTEXT_WINDOW_EXCEEDED",
    ]
    assert types.count("session/end") == 1
    assert records[-1]["payload"]["stop_reason"] == "MODEL_COMPLETED"


def test_a_segments_summary_never_appears_on_stdout(tmp_path: Path) -> None:
    """seam ⑥：段里真发生一次压缩时，那条摘要回复不打到 stdout。"""
    (tmp_path / "a.md").write_text("x" * 100000, encoding="utf-8")
    fixture = _fixture(
        tmp_path,
        "compact.json",
        [
            {
                "content": "先读一下",
                "finish_reason": "tool_calls",
                "tool_calls": [{"id": "c1", "name": "read", "arguments": {"file_path": "a.md"}}],
            },
            {"content": "那是摘要不该出现", "finish_reason": "stop"},
            {"content": "这是回复", "finish_reason": "stop"},
        ],
    )

    result = _chat(
        "--fixture",
        fixture,
        "--window",
        "70000",
        "--reserve",
        "100",
        cwd=tmp_path,
        stdin_text="读一下 a.md\n",
    )

    assert result.returncode == 0
    assert "compaction/summary" in _types(tmp_path)
    assert "那是摘要不该出现" not in result.stdout
    assert result.stdout.splitlines() == ["> ", "先读一下", "这是回复", "> "]


def test_chats_flag_table_is_runs_flag_table_minus_two(tmp_path: Path) -> None:
    """seam ⑥：chat 的参数表就是 run 的那份减 `--prompt` 与 `--events`（task 6.1）。"""
    run_help = _cli("run", "--help", cwd=tmp_path)
    chat_help = _cli("chat", "--help", cwd=tmp_path)

    assert run_help.returncode == 0
    assert chat_help.returncode == 0
    assert _flags(chat_help.stdout) == _flags(run_help.stdout) - {"-p", "--prompt", "--events"}

    for rejected in (("-p", "写一份报告"), ("--prompt", "写一份报告"), ("--events", "jsonl")):
        result = _cli("chat", *rejected, cwd=tmp_path)
        assert result.returncode == 2
        assert "unrecognized arguments" in result.stderr
    assert _log_files(tmp_path) == []


def test_a_chat_that_cannot_start_leaves_no_log(tmp_path: Path) -> None:
    """seam ⑥：chat 的「会话开始之前失败」与 run 同一条路——退出码 2、不建日志。"""
    result = _cli(
        "chat",
        "--provider",
        "openai",
        "--api-key-env",
        "MINIHNS_ABSENT_KEY",
        cwd=tmp_path,
    )

    assert result.returncode == 2
    assert "INVALID_ARGUMENT" in result.stderr
    assert "MINIHNS_ABSENT_KEY" in result.stderr
    assert _log_files(tmp_path) == []
