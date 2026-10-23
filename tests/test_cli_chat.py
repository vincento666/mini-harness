"""seam ⑥：`minihns chat` 的黑盒（真实子进程）。"""

from __future__ import annotations

import asyncio
import json
import os
import re
import signal
import sys
import time
from pathlib import Path
from typing import Any

import pytest

from cli_blackbox import (
    _cli,
    _cli_console_process,
    _cli_process,
    _FakeEndpoint,
    _LiveStreams,
    _send_ctrl_c,
)
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


_KEY_ENV = "MINIHNS_TEST_KEY"
_KEY_VALUE = "sk-test-0123456789abcdef"


def _chat_openai(cwd: Path, base_url: str, *, stdin_text: str) -> Any:
    """`chat` 走真实适配器的路：provider 是 openai，端点是测试进程里监听 loopback 的假 server。"""
    env = dict(os.environ)
    env[_KEY_ENV] = _KEY_VALUE
    return _cli(
        "chat",
        "--provider",
        "openai",
        "--base-url",
        base_url,
        "--model",
        "test-model",
        "--api-key-env",
        _KEY_ENV,
        cwd=cwd,
        env=env,
        stdin_text=stdin_text,
    )


def _log_text(cwd: Path) -> str:
    """整份日志的原文：判「某一行没有写进日志」时用这个，不看解析后的记录。"""
    logs = _log_files(cwd)
    assert len(logs) == 1, f"一次 chat 应当恰有一份 session 日志，实际 {len(logs)} 份"
    return logs[0].read_text(encoding="utf-8")


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


def test_a_provider_failed_segment_says_so_on_stderr(tmp_path: Path) -> None:
    """seam ⑥：段级收尾不是无声的——那一行在 stderr，不在 stdout，也不在日志里。"""
    with _FakeEndpoint(
        status=400, body={"error": {"type": "invalid_request_error", "message": "bad tools"}}
    ) as endpoint:
        result = _chat_openai(tmp_path, endpoint.base_url, stdin_text="第一条\n")

    assert result.returncode == 0
    notes = [line for line in result.stderr.splitlines() if "PROVIDER_HTTP_STATUS" in line]
    assert len(notes) == 1, "段以 PROVIDER_ERROR 收尾时 stderr 该有一行"
    assert "PROVIDER_ERROR" in notes[0]
    # 1.4：新的组装规则下这一行照旧——reason、与 reason 不同的 code、然后 provider 那句 detail。
    assert "bad tools" in notes[0], "造成它的失败结果带着提供方那句话，那一行得把它说出来"
    assert notes[0] not in result.stdout
    assert notes[0] not in _log_text(tmp_path)


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


def test_a_max_turns_segment_says_so_on_stderr(tmp_path: Path) -> None:
    """seam ⑥：用完回合数也是不以正常回复收尾——屏幕上有一行，会话继续。"""
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
    notes = [line for line in result.stderr.splitlines() if "MAX_TURNS" in line]
    assert len(notes) == 2, "两个段各用完一次"
    assert all("PROVIDER" not in line for line in notes), "没有失败结果时只有停止理由"
    assert notes[0] not in result.stdout
    assert notes[0] not in _log_text(tmp_path)


def test_a_fence_denied_segment_says_so_on_stderr(tmp_path: Path) -> None:
    """seam ⑥：围栏拒绝收尾的段也不能无声——真实端点那一跑撞到它什么都不打。"""
    result = _chat("--fixture", str(WRITE_OUTSIDE_SCENARIO), cwd=tmp_path, stdin_text="越界写\n")

    assert result.returncode == 0
    notes = [line for line in result.stderr.splitlines() if "[段]" in line]
    assert len(notes) == 1, "段以 FENCE_DENIED 收尾时 stderr 该有一行"
    assert "FENCE_DENIED" in notes[0]
    assert notes[0] not in result.stdout
    assert notes[0] not in _log_text(tmp_path)


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


def test_a_provider_failure_inside_a_segment_leaves_the_session_running(tmp_path: Path) -> None:
    """seam ⑥：provider 失败是段级收尾——`error/model` 在盘上，会话继续，编号不重置。"""
    entries = [
        {
            "content": f"第 {index} 次读",
            "finish_reason": "tool_calls",
            "tool_calls": [{"id": f"c{index}", "name": "read", "arguments": {"file_path": "a.md"}}],
        }
        for index in (1, 2)
    ]
    fixture = _fixture(tmp_path, "two_then_none.json", entries)

    result = _chat(
        "--fixture", fixture, "--max-turns", "4", cwd=tmp_path, stdin_text="第一条\n第二条\n"
    )

    assert result.returncode == 0
    records = _records(tmp_path)
    failures = [record for record in records if record["type"] == "error/model"]
    assert len(failures) == 2, "两个段各撞上一次 fixture 耗尽"
    assert {str(record["payload"]["code"]) for record in failures} == {"PROVIDER_EXHAUSTED"}
    segments = [record["payload"] for record in records if record["type"] == "segment/end"]
    assert [(segment["segment_id"], segment["stop_reason"]) for segment in segments] == [
        ("s1", "PROVIDER_ERROR"),
        ("s2", "PROVIDER_ERROR"),
    ]
    turn_ids = [
        record["payload"]["turn_id"] for record in records if record["type"] == "turn/start"
    ]
    assert turn_ids == ["t1", "t2", "t3", "t4"]
    assert records[-1]["type"] == "session/end"
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
    chat_stdout, chat_stderr = process.communicate(timeout=30)

    assert process.returncode == 0
    # 被取消的段（`ABORTED`）打那一行；正常收尾的那一段不打。
    notes = [line for line in chat_stderr.splitlines() if "[段]" in line]
    assert len(notes) == 1, "只有被取消的那一段在 stderr 上留一行"
    assert "ABORTED" in notes[0]
    assert "[段]" not in chat_stdout
    assert notes[0] not in _log_text(tmp_path)
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
    assert result.stdout.splitlines() == ["> 先读一下", "这是回复正文", "> "]
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


def test_an_overflowed_segment_says_so_on_stderr(tmp_path: Path) -> None:
    """seam ⑥：溢出塌成回合级收尾，屏幕上看得见那一行，会话继续接受下一条输入。"""
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
    notes = [line for line in result.stderr.splitlines() if "CONTEXT_WINDOW_EXCEEDED" in line]
    assert len(notes) == 2
    assert notes[0] not in result.stdout
    assert notes[0] not in _log_text(tmp_path)
    segments = [
        record["payload"] for record in _records(tmp_path) if record["type"] == "segment/end"
    ]
    assert [segment["stop_reason"] for segment in segments] == [
        "CONTEXT_WINDOW_EXCEEDED",
        "CONTEXT_WINDOW_EXCEEDED",
    ]


def test_a_chat_that_ends_cleanly_prints_no_segment_note(tmp_path: Path) -> None:
    """seam ⑥：正常收尾不打扰——段以 `MODEL_COMPLETED` 结束时 stderr 里没有那一行。"""
    fixture = _fixture(
        tmp_path,
        "clean.json",
        [
            {"content": "完成一", "finish_reason": "stop"},
            {"content": "完成二", "finish_reason": "stop"},
        ],
    )

    result = _chat("--fixture", fixture, cwd=tmp_path, stdin_text="第一条\n第二条\n")

    assert result.returncode == 0
    assert "[段]" not in result.stderr
    assert [
        record["payload"]["stop_reason"]
        for record in _records(tmp_path)
        if record["type"] == "segment/end"
    ] == ["MODEL_COMPLETED", "MODEL_COMPLETED"]


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
    assert result.stdout.splitlines() == ["> 先读一下", "这是回复", "> "]


def test_a_compaction_shows_what_it_shadowed_on_stderr(tmp_path: Path) -> None:
    """seam ⑥：压缩在屏幕上看得见——那一行说的是被折掉的那一段与前后的大小。

    第二条输入是判据的一半：压缩只发生在第一段，那一行就只能出现一次。
    """
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
            {"content": "第二条回复", "finish_reason": "stop"},
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
        stdin_text="读一下 a.md\n再来一条\n",
    )

    assert result.returncode == 0
    summaries = [
        record["payload"] for record in _records(tmp_path) if record["type"] == "compaction/summary"
    ]
    assert len(summaries) == 1
    shadowed = summaries[0]["shadowed_range"]
    needle = (
        str(shadowed["start"]),
        str(shadowed["end"]),
        str(summaries[0]["tokens_before"]),
        str(summaries[0]["tokens_after"]),
    )
    lines = [line for line in result.stderr.splitlines() if all(part in line for part in needle)]
    assert len(lines) == 1, "stderr 里该有一行说清折掉了哪一段、前后各多大"
    assert lines[0] not in result.stdout
    assert lines[0] not in _log_text(tmp_path)


def test_a_chat_without_compaction_prints_no_shadow_note(tmp_path: Path) -> None:
    """seam ⑥：没有压缩就没有遮蔽反馈——不打扰。"""
    fixture = _fixture(tmp_path, "flat.json", [{"content": "完成", "finish_reason": "stop"}])

    result = _chat("--fixture", fixture, cwd=tmp_path, stdin_text="第一条\n")

    assert result.returncode == 0
    assert "compaction/summary" not in _types(tmp_path)
    assert "[遮蔽]" not in result.stderr


def test_a_chat_that_compacted_replays_the_same_log_unchanged(tmp_path: Path) -> None:
    """seam ⑥：遮蔽反馈不是日志的投影——同一份日志的 `replay` 里没有出现那一行。"""
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
    assert any("[遮蔽]" in line for line in result.stderr.splitlines()), "这一跑得先真发生压缩"

    session_id = _log_files(tmp_path)[0].stem
    replay = _cli("replay", session_id, cwd=tmp_path)

    assert replay.returncode == 0
    assert "[遮蔽]" not in replay.stdout
    assert "[遮蔽]" not in replay.stderr
    assert "REPLAY_MISMATCH" not in replay.stderr
    assert "x" * 100000 not in replay.stdout


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


# ---------------------------------------------------------------------------
# change `fix-chat-screen-feedback`：屏幕上说了什么、怎么说（seam ⑥ 判排版，不只判「有没有」）
# ---------------------------------------------------------------------------


def test_the_prompt_does_not_carry_its_own_newline(tmp_path: Path) -> None:
    """seam ⑥ 1.1：提示符打在不带换行的同一行上，输入紧跟在它之后。

    判的是 stdout 的**排版**：此前 `print(_CHAT_PROMPT)` 自带一个回车，人输入的那一行落在空行上。
    """
    fixture = _fixture(tmp_path, "one.json", [{"content": "回复正文", "finish_reason": "stop"}])

    result = _chat("--fixture", fixture, cwd=tmp_path, stdin_text="第一条\n")

    assert result.returncode == 0
    assert result.stdout == "> 回复正文\n> "


def test_tool_only_turns_leave_no_blank_lines(tmp_path: Path) -> None:
    """seam ⑥ 1.2：只带工具调用的回合 `content` 是空串——它不该在 stdout 上留下空行。

    工具回合越多空行越多，提示符被推到很远下面；UAT 里人报的「工具调用看得见」其实就是这些空行。
    """
    (tmp_path / "a.md").write_text("工具结果的内容\n", encoding="utf-8")
    entries: list[dict[str, Any]] = [
        {
            "content": "",
            "finish_reason": "tool_calls",
            "tool_calls": [{"id": f"c{index}", "name": "read", "arguments": {"file_path": "a.md"}}],
        }
        for index in range(1, 4)
    ]
    entries.append({"content": "正文", "finish_reason": "stop"})
    fixture = _fixture(tmp_path, "blanks.json", entries)

    result = _chat("--fixture", fixture, cwd=tmp_path, stdin_text="读一下 a.md\n")

    assert result.returncode == 0
    assert result.stdout == "> 正文\n> "
    assert "\n\n" not in result.stdout


def _overflow_entries(tmp_path: Path) -> list[dict[str, Any]]:
    """照 UAT 复现的形状：三段工具回合，之后一条把预算读数校准到触发线之上的正常回复。

    第二个段一开局就压缩、压缩完仍超线；最后两条给压缩那一次摘要调用与第二个段的正常回复。
    """
    (tmp_path / "big.md").write_text("内容" * 30000, encoding="utf-8")
    entries: list[dict[str, Any]] = [
        {
            "content": "",
            "finish_reason": "tool_calls",
            "tool_calls": [
                {"id": f"c{index}", "name": "read", "arguments": {"file_path": "big.md"}}
            ],
            "usage": {"input_tokens": 1000, "output_tokens": 10},
        }
        for index in range(1, 4)
    ]
    entries += [
        {
            "content": "第一段收尾。",
            "finish_reason": "stop",
            "usage": {"input_tokens": 60000, "output_tokens": 10},
        },
        {"content": "压缩用的摘要。", "finish_reason": "stop", "usage": {"input_tokens": 1000}},
        {"content": "第二段照常回答。", "finish_reason": "stop", "usage": {"input_tokens": 1000}},
    ]
    return entries


def test_the_overflow_segment_note_carries_the_detail_once(tmp_path: Path) -> None:
    """seam ⑥ 1.3：溢出那一行不许把停止理由重复两遍——它得带上日志里那条非空 detail。

    形状照 UAT 复现：三段工具回合之后第一段以正常回复收尾，`usage.input_tokens` 把预算读数校准到
    触发线之上；第二个段一开局就压缩、压缩完仍超线，那一行说的是「压缩之后仍超线」，不是两遍词表名。
    """
    fixture = _fixture(tmp_path, "overflow.json", _overflow_entries(tmp_path))

    result = _chat("--fixture", fixture, cwd=tmp_path, stdin_text="第一条\n第二条\n")

    assert result.returncode == 0
    records = _records(tmp_path)
    overflows = [record for record in records if record["type"] == "error/context"]
    assert len(overflows) == 1, "第二个段开局溢出一次"
    detail = str(overflows[0]["payload"]["detail"])
    assert detail != "", "日志里那条 detail 非空"

    notes = [line for line in result.stderr.splitlines() if "CONTEXT_WINDOW_EXCEEDED" in line]
    assert len(notes) == 1, "溢出段在 stderr 上只有一行"
    assert notes[0].count("CONTEXT_WINDOW_EXCEEDED") == 1, "停止理由这个词在那一行里只出现一次"
    assert detail in notes[0], "那一行带着日志里那条非空 detail，不是把词表名重复两遍"
    assert notes[0] not in result.stdout
    assert notes[0] not in _log_text(tmp_path)


_NOT_WINDOWS_REASON = (
    "这一条判的是真 Ctrl-C 的投递，Windows 这一端此前只能跳过（design D8）："
    "Linux 那一半沿用既有的 SIGINT 判据，两条不重复"
)

_HANG_SCRIPT = "import time\n\nwhile True:\n    time.sleep(0.1)\n"


def _hang_fixture(tmp_path: Path) -> str:
    """一条挂很久的 `bash` + 一条给第二个段的正常回复。"""
    (tmp_path / "loop.py").write_text(_HANG_SCRIPT, encoding="utf-8")
    return _fixture(
        tmp_path,
        "hang.json",
        [
            {
                "content": "跑一条挂很久的命令",
                "finish_reason": "tool_calls",
                "tool_calls": [
                    {
                        "id": "c1",
                        "name": "bash",
                        "arguments": {"command": "python loop.py", "timeout_seconds": 30},
                    }
                ],
            },
            {"content": "第二条输入的回复", "finish_reason": "stop"},
        ],
    )


@pytest.mark.skipif(sys.platform != "win32", reason=_NOT_WINDOWS_REASON)
def test_ctrl_c_mid_segment_prints_the_aborted_note(tmp_path: Path) -> None:
    """seam ⑥ 1.5：真 Ctrl-C 落在段进行中 → stderr 有 `[段] ABORTED`，stdout 与日志里没有。

    同步点是 stdout 上先出现 `> `：提示符不带换行、且已经 flush 到管道里，黑盒才跟得上会话。
    """
    process = _cli_console_process(
        "chat",
        "--fixture",
        _hang_fixture(tmp_path),
        "--yes",
        cwd=tmp_path,
        keep_stdin_open=True,
    )
    streams = _LiveStreams(process).start()
    streams.wait_for_stdout("> ", "提示符还没打到管道里")
    assert process.stdin is not None
    process.stdin.write("第一条\n")
    process.stdin.flush()

    _wait_until_log_contains(tmp_path, process, '"tool/call"', "进入工具执行段")
    _send_ctrl_c(process.pid)
    _wait_until_log_contains(tmp_path, process, '"segment/end"', "写出被取消段的段边界")

    assert process.poll() is None, "取消当前段之后进程不该退出"
    process.stdin.write("第二条\n")
    process.stdin.flush()
    process.stdin.close()
    returncode, chat_stdout, chat_stderr = streams.finish()

    assert returncode == 0
    notes = [line for line in chat_stderr.splitlines() if "[段]" in line]
    assert len(notes) == 1, "被取消的段在 stderr 上该有一行"
    assert "ABORTED" in notes[0]
    assert "[段]" not in chat_stdout
    assert notes[0] not in _log_text(tmp_path)
    records = _records(tmp_path)
    types = [str(record["type"]) for record in records]
    assert "error/abort" in types
    segments = [record["payload"] for record in records if record["type"] == "segment/end"]
    assert segments[0]["stop_reason"] == "ABORTED"
    assert types.count("session/end") == 1, "会话还在：`session/end` 只在 stdin 关闭之后出现一次"
    assert types[-2:] == ["segment/end", "session/end"]
    assert records[-1]["payload"]["stop_reason"] == "MODEL_COMPLETED"


@pytest.mark.skipif(sys.platform != "win32", reason=_NOT_WINDOWS_REASON)
def test_ctrl_c_at_the_prompt_ends_the_session_without_traceback(tmp_path: Path) -> None:
    """seam ⑥ 1.6：真 Ctrl-C 落在没有段在跑时 → 退出码 0、stderr 里没有 `Traceback`。

    管道上的阻塞读不会被 Ctrl-C 打断（Windows 的 Ctrl-C 只在解释器回到字节码边界时才被消费），
    所以信号之后给 stdin 一个 EOF 让解释器回到边界上。收尾那一段缝隙里再连着送几次：
    落进缝隙里没人接，就是 design D7 要堵的那个洞。送不到（进程已经退出）不算失败。
    """
    fixture = _fixture(tmp_path, "unused.json", [{"content": "不该出现", "finish_reason": "stop"}])
    process = _cli_console_process(
        "chat",
        "--fixture",
        str(fixture),
        cwd=tmp_path,
        keep_stdin_open=True,
    )
    streams = _LiveStreams(process).start()
    streams.wait_for_stdout("> ", "提示符还没打到管道里")

    _send_ctrl_c(process.pid)
    assert process.stdin is not None
    process.stdin.close()
    # 连着送，直到进程自己退出：收尾那一段只有几毫秒，一次送进缝隙里的概率不够高。
    # 送不到（进程已经退出）不算失败——那条缝隙已经走完了。
    for _ in range(40):
        if process.poll() is not None:
            break
        try:
            _send_ctrl_c(process.pid)
        except RuntimeError:
            break

    returncode, chat_stdout, chat_stderr = streams.finish()

    assert returncode == 0, f"会话收尾里没人接取消：{chat_stderr}"
    assert "Traceback" not in chat_stderr, f"会话收尾里没人接取消：{chat_stderr}"
    assert "不该出现" not in chat_stdout
    records = _records(tmp_path)
    types = [str(record["type"]) for record in records]
    assert types[-1] == "session/end"
    assert records[-1]["payload"]["stop_reason"] == "MODEL_COMPLETED"


def test_chat_prints_the_session_id_on_stderr(tmp_path: Path) -> None:
    """seam ⑥ 1.7：会话开始时 stderr 上有一行 session id——不在 stdout，也不为它多写记录。

    那一行同时是「这次会话的日志在哪」的入口，所以判据拿它跑一遍 `minihns replay`。
    """
    fixture = _fixture(tmp_path, "one.json", [{"content": "回复正文", "finish_reason": "stop"}])

    result = _chat("--fixture", fixture, cwd=tmp_path, stdin_text="第一条\n")

    assert result.returncode == 0
    session_id = _log_files(tmp_path)[0].stem
    lines = [line for line in result.stderr.splitlines() if session_id in line]
    assert len(lines) == 1, "会话开始时 stderr 上该有一行 session id"
    assert session_id not in result.stdout
    assert lines[0] not in _log_text(tmp_path)

    replay = _cli("replay", session_id, cwd=tmp_path)

    assert replay.returncode == 0
    assert "REPLAY_MISMATCH" not in replay.stderr


def test_consecutive_overflows_say_the_session_cannot_come_down(tmp_path: Path) -> None:
    """seam ⑥ 1.8：连续两段溢出 → stderr 多出一行说明，且每个会话里恰一次。

    三段连续溢出只许说一次；判据只认那一行的前缀标记，不判措辞（design 的 open question）。
    """
    fixture = _fixture(
        tmp_path,
        "three.json",
        [{"content": f"摘要{n}", "finish_reason": "stop"} for n in range(1, 7)],
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
        stdin_text="第一条\n第二条\n第三条\n",
    )

    assert result.returncode == 0
    segments = [
        record["payload"] for record in _records(tmp_path) if record["type"] == "segment/end"
    ]
    assert [segment["stop_reason"] for segment in segments] == [
        "CONTEXT_WINDOW_EXCEEDED",
        "CONTEXT_WINDOW_EXCEEDED",
        "CONTEXT_WINDOW_EXCEEDED",
    ], "这一跑得先真发生连续溢出"

    lines = [line for line in result.stderr.splitlines() if line.startswith("[降不下去]")]
    assert len(lines) == 1, "连续溢出在 stderr 上多出一行说明，且只说一次"
    assert lines[0] not in result.stdout
    assert lines[0] not in _log_text(tmp_path)


def test_a_single_overflow_does_not_say_the_session_cannot_come_down(tmp_path: Path) -> None:
    """seam ⑥ 1.8：只有一段溢出（不连续）时不多出那一行。"""
    fixture = _fixture(tmp_path, "one-overflow.json", _overflow_entries(tmp_path))

    result = _chat("--fixture", fixture, cwd=tmp_path, stdin_text="第一条\n第二条\n")

    assert result.returncode == 0
    segments = [
        record["payload"] for record in _records(tmp_path) if record["type"] == "segment/end"
    ]
    assert [segment["stop_reason"] for segment in segments] == [
        "MODEL_COMPLETED",
        "CONTEXT_WINDOW_EXCEEDED",
    ], "这一跑得只有一段溢出"
    assert not [line for line in result.stderr.splitlines() if line.startswith("[降不下去]")]
