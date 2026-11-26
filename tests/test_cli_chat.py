"""seam ⑥：`minihns chat` 的黑盒（真实子进程）。"""

from __future__ import annotations

import asyncio
import json
import os
import re
import signal
import subprocess
import sys
import threading
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
from mini_harness.events import EventLog
from paths import REPO_ROOT, WRITE_OUTSIDE_SCENARIO


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
        'max_steps = 2\ntools = ["read"]\n', encoding="utf-8"
    )
    fixture = _fixture(tmp_path, "one.json", [{"content": "回复", "finish_reason": "stop"}])

    result = _chat("--fixture", fixture, cwd=tmp_path, stdin_text="第一条\n")

    assert result.returncode == 0
    payload = next(
        record["payload"] for record in _records(tmp_path) if record["type"] == "session/start"
    )
    assert payload["max_steps"] == 2
    assert payload["tools"] == ["read"]
    assert payload["entry"] == "chat"
    assert payload["prompt"] == ""


def test_two_inputs_make_one_log_two_turns_and_two_user_messages(tmp_path: Path) -> None:
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
    assert types.count("turn/start") == 2
    assert types.count("turn/end") == 2
    # `user/message` 在 `turn/start` 之后、该段第一个 `step/start` 之前。
    assert types[:4] == ["session/start", "turn/start", "user/message", "step/start"]
    messages = [record["payload"] for record in records if record["type"] == "user/message"]
    assert [message["content"] for message in messages] == ["第一条", "第二条"]
    assert [message["turn_id"] for message in messages] == ["s1", "s2"]
    assert records[-1]["type"] == "session/end"
    assert records[-1]["payload"]["stop_reason"] == "MODEL_COMPLETED"
    # `session/end.steps` 是会话跑掉的回合数，不是回合编号。
    assert records[-1]["payload"]["steps"] == 2


def test_an_empty_stdin_is_a_legal_session(tmp_path: Path) -> None:
    """seam ⑥：stdin 立刻 EOF 也是一份合法会话——没有段，也没有回合。"""
    fixture = _fixture(tmp_path, "unused.json", [{"content": "不该出现", "finish_reason": "stop"}])

    result = _chat("--fixture", fixture, cwd=tmp_path, stdin_text="")

    assert result.returncode == 0
    assert _types(tmp_path) == ["session/start", "session/end"]
    assert _records(tmp_path)[-1]["payload"]["steps"] == 0


def test_blank_input_writes_no_record_and_opens_no_turn(tmp_path: Path) -> None:
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
    assert [str(record["type"]) for record in records].count("turn/start") == 2
    messages = [record["payload"] for record in records if record["type"] == "user/message"]
    assert [message["content"] for message in messages] == ["第一条", "第二条"]


def test_blank_input_does_not_reprint_the_prompt(tmp_path: Path) -> None:
    """blank-input-no-reprompt：空白输入不再追加一条提示符，提示符只在回到等待状态时出现。"""
    fixture = _fixture(tmp_path, "reply.json", [{"content": "回复一", "finish_reason": "stop"}])

    # 首条前空白：开始时一条提示符，空白不加。管道不回显换行，所以初始提示符与回复同行；
    # 判别点是旧行为的 `> >` 前缀不再出现，且 `> ` 恰出现两次（开始一次、回复后一次）。
    result = _chat("--fixture", fixture, "--no-stream", cwd=tmp_path, stdin_text="\n第一条\n")
    assert result.returncode == 0
    assert result.stdout.splitlines() == ["> 回复一", "> "]
    assert "> >" not in result.stdout
    assert result.stdout.count("> ") == 2

    # 末尾空白：粘贴尾随空行不再多出一条 `> `。
    result = _chat("--fixture", fixture, "--no-stream", cwd=tmp_path, stdin_text="第一条\n\n")
    assert result.returncode == 0
    assert result.stdout.splitlines() == ["> 回复一", "> "]
    assert result.stdout.count("> ") == 2


def test_a_provider_failed_turn_says_so_on_stderr(tmp_path: Path) -> None:
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


def test_a_turn_that_uses_up_max_steps_returns_to_the_prompt(tmp_path: Path) -> None:
    """seam ⑥：`max_steps` 是段内上限；用完回到提示符，下一条输入额度完整、编号不重置。"""
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
        "--fixture", fixture, "--max-steps", "2", cwd=tmp_path, stdin_text="第一条\n第二条\n"
    )

    assert result.returncode == 0
    records = _records(tmp_path)
    turns = [record["payload"] for record in records if record["type"] == "turn/end"]
    assert [turn["turn_id"] for turn in turns] == ["s1", "s2"]
    assert [turn["stop_reason"] for turn in turns] == ["MAX_STEPS", "MAX_STEPS"]
    assert [turn["steps"] for turn in turns] == [2, 2]
    # 回合编号在整个会话里连续：第二个段从 t3 起，不重置。
    step_ids = [
        record["payload"]["step_id"] for record in records if record["type"] == "step/start"
    ]
    assert step_ids == ["t1", "t2", "t3", "t4"]
    assert records[-1]["type"] == "session/end"


def test_a_max_steps_turn_says_so_on_stderr(tmp_path: Path) -> None:
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
        "--fixture", fixture, "--max-steps", "2", cwd=tmp_path, stdin_text="第一条\n第二条\n"
    )

    assert result.returncode == 0
    notes = [line for line in result.stderr.splitlines() if "MAX_STEPS" in line]
    assert len(notes) == 2, "两个段各用完一次"
    assert all("PROVIDER" not in line for line in notes), "没有失败结果时只有停止理由"
    assert notes[0] not in result.stdout
    assert notes[0] not in _log_text(tmp_path)


def test_a_fence_denied_turn_says_so_on_stderr(tmp_path: Path) -> None:
    """seam ⑥：围栏拒绝收尾的段也不能无声——真实端点那一跑撞到它什么都不打。"""
    result = _chat("--fixture", str(WRITE_OUTSIDE_SCENARIO), cwd=tmp_path, stdin_text="越界写\n")

    assert result.returncode == 0
    notes = [line for line in result.stderr.splitlines() if "[轮] 收尾" in line]
    assert len(notes) == 1, "段以 FENCE_DENIED 收尾时 stderr 该有一行"
    assert "FENCE_DENIED" in notes[0]
    codes = [
        str(record["payload"]["code"])
        for record in _records(tmp_path)
        if record["type"] == "error/fence" and "code" in record["payload"]
    ]
    assert codes and codes[0] != "FENCE_DENIED"
    assert codes[0] in notes[0], "那一行含造成它的失败结果的 code，不是只有停止理由"
    assert notes[0] not in result.stdout
    assert notes[0] not in _log_text(tmp_path)


def test_a_turn_failure_does_not_end_the_session(tmp_path: Path) -> None:
    """seam ⑥：围栏拒绝落在盘上，会话继续；EOF 收尾是退出码 0。"""
    result = _chat("--fixture", str(WRITE_OUTSIDE_SCENARIO), cwd=tmp_path, stdin_text="越界写\n")

    assert result.returncode == 0
    records = _records(tmp_path)
    types = [str(record["type"]) for record in records]
    assert "error/fence" in types
    assert types[-2:] == ["turn/end", "session/end"]
    assert records[-2]["payload"]["stop_reason"] == "FENCE_DENIED"
    assert records[-1]["payload"]["stop_reason"] == "MODEL_COMPLETED"


def test_a_provider_failure_inside_a_turn_leaves_the_session_running(tmp_path: Path) -> None:
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
        "--fixture", fixture, "--max-steps", "4", cwd=tmp_path, stdin_text="第一条\n第二条\n"
    )

    assert result.returncode == 0
    records = _records(tmp_path)
    failures = [record for record in records if record["type"] == "error/model"]
    assert len(failures) == 2, "两个段各撞上一次 fixture 耗尽"
    assert {str(record["payload"]["code"]) for record in failures} == {"PROVIDER_EXHAUSTED"}
    turns = [record["payload"] for record in records if record["type"] == "turn/end"]
    assert [(turn["turn_id"], turn["stop_reason"]) for turn in turns] == [
        ("s1", "PROVIDER_ERROR"),
        ("s2", "PROVIDER_ERROR"),
    ]
    step_ids = [
        record["payload"]["step_id"] for record in records if record["type"] == "step/start"
    ]
    assert step_ids == ["t1", "t2", "t3", "t4"]
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


async def test_the_chat_handler_cancels_the_running_turn() -> None:
    """seam ⑥：段在跑时 Ctrl-C 只取消当前段——这条不看平台脸色。"""
    cancel = asyncio.Event()
    signals = _ChatSignals(active=cancel, loop=asyncio.get_running_loop())

    _chat_sigint_handler(signals)(signal.SIGINT, None)
    await asyncio.sleep(0)

    assert cancel.is_set()


async def test_the_chat_handler_ends_the_session_when_no_turn_is_running() -> None:
    """seam ⑥：提示符上 Ctrl-C 是「结束会话」，不是取消——这条也不看平台脸色。"""
    signals = _ChatSignals(active=None)

    with pytest.raises(KeyboardInterrupt):
        _chat_sigint_handler(signals)(signal.SIGINT, None)


@pytest.mark.skipif(sys.platform == "win32", reason=_WINDOWS_CTRL_C_REASON)
def test_sigint_mid_turn_cancels_the_turn_not_the_session(tmp_path: Path) -> None:
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
    _wait_until_log_contains(tmp_path, process, '"turn/end"', "写出被取消段的段边界")

    assert process.poll() is None, "取消当前段之后进程不该退出"

    process.stdin.write("第二条\n")
    process.stdin.flush()
    chat_stdout, chat_stderr = process.communicate(timeout=30)

    assert process.returncode == 0
    # 被取消的段（`ABORTED`）打那一行；正常收尾的那一段不打。
    notes = [line for line in chat_stderr.splitlines() if "[轮] 收尾" in line]
    assert len(notes) == 1, "只有被取消的那一段在 stderr 上留一行"
    assert "ABORTED" in notes[0]
    assert "[轮] 收尾" not in chat_stdout
    assert notes[0] not in _log_text(tmp_path)
    records = _records(tmp_path)
    types = [str(record["type"]) for record in records]
    assert "error/abort" in types
    turns = [record["payload"] for record in records if record["type"] == "turn/end"]
    assert turns[0] == {
        "turn_id": "s1",
        "stop_reason": "ABORTED",
        "steps": 1,
        "tool_calls": 0,
    }
    # 会话还在：`session/end` 只在 stdin 关闭之后出现一次。
    assert types.count("session/end") == 1
    assert types[-2:] == ["turn/end", "session/end"]
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

    result = _chat("--fixture", fixture, "--no-stream", cwd=tmp_path, stdin_text="读一下 a.md\n")

    assert result.returncode == 0
    assert result.stdout.splitlines() == ["> 先读一下", "这是回复正文", "> "]
    assert "工具结果的内容不该出现在 stdout" not in result.stdout
    assert "context/assembled" not in result.stdout


def test_an_overflowed_turn_returns_to_the_prompt(tmp_path: Path) -> None:
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
        "4000",
        "--reserve",
        "100",
        "--append-system-prompt",
        "说明" * 10000,
        cwd=tmp_path,
        stdin_text="第一条\n第二条\n",
    )

    assert result.returncode == 0
    records = _records(tmp_path)
    types = [str(record["type"]) for record in records]
    assert types.count("error/context") == 2
    # 溢出走自己那条路，不冒充 provider 失败。
    assert "error/model" not in types
    turns = [record["payload"] for record in records if record["type"] == "turn/end"]
    assert [turn["turn_id"] for turn in turns] == ["s1", "s2"]
    assert [turn["stop_reason"] for turn in turns] == [
        "CONTEXT_WINDOW_EXCEEDED",
        "CONTEXT_WINDOW_EXCEEDED",
    ]
    assert types.count("session/end") == 1
    assert records[-1]["payload"]["stop_reason"] == "MODEL_COMPLETED"


def test_an_overflowed_turn_says_so_on_stderr(tmp_path: Path) -> None:
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
        "4000",
        "--reserve",
        "100",
        "--append-system-prompt",
        "说明" * 10000,
        cwd=tmp_path,
        stdin_text="第一条\n第二条\n",
    )

    assert result.returncode == 0
    notes = [line for line in result.stderr.splitlines() if "CONTEXT_WINDOW_EXCEEDED" in line]
    assert len(notes) == 2
    assert notes[0] not in result.stdout
    assert notes[0] not in _log_text(tmp_path)
    turns = [record["payload"] for record in _records(tmp_path) if record["type"] == "turn/end"]
    assert [turn["stop_reason"] for turn in turns] == [
        "CONTEXT_WINDOW_EXCEEDED",
        "CONTEXT_WINDOW_EXCEEDED",
    ]


def test_a_chat_that_ends_cleanly_prints_no_turn_note(tmp_path: Path) -> None:
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
    assert "[轮] 收尾" not in result.stderr
    assert [
        record["payload"]["stop_reason"]
        for record in _records(tmp_path)
        if record["type"] == "turn/end"
    ] == ["MODEL_COMPLETED", "MODEL_COMPLETED"]


def test_a_turns_summary_never_appears_on_stdout(tmp_path: Path) -> None:
    """seam ⑥：段里真发生一次压缩时，那条摘要回复不打到 stdout。"""
    (tmp_path / "a.md").write_text(("x" * 100 + "\n") * 1000, encoding="utf-8")
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
        "--no-stream",
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
    (tmp_path / "a.md").write_text(("x" * 100 + "\n") * 1000, encoding="utf-8")
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
    (tmp_path / "a.md").write_text(("x" * 100 + "\n") * 1000, encoding="utf-8")
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
        "--no-stream",
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
    assert _flags(chat_help.stdout) == _flags(run_help.stdout) - {
        "-p",
        "--prompt",
        "--events",
    } | {"--resume", "--stream", "--no-stream"}

    for rejected in (("-p", "写一份报告"), ("--prompt", "写一份报告"), ("--events", "jsonl")):
        result = _cli("chat", *rejected, cwd=tmp_path)
        assert result.returncode == 2
        assert "unrecognized arguments" in result.stderr
    assert _log_files(tmp_path) == []

    conflict = _cli("chat", "--stream", "--no-stream", cwd=tmp_path)
    assert conflict.returncode == 2
    assert "not allowed with argument" in conflict.stderr


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
            # 第三条的 `content` 全是空白：规格说的是「空或全空白」那一半，两条都得喂。
            "content": "" if index < 3 else "   \n  ",
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


def test_the_overflow_turn_note_carries_the_detail_once(tmp_path: Path) -> None:
    """退休（2026-10-26）：这一条守的「第二段开局压缩、压完仍超线」在压力预算规则下不可达。

    它的断言（那一行带非空 detail、不把停止理由重复两遍）已并入
    `test_an_overflowed_turn_says_so_on_stderr`；场景不可达的理由记在 ADR-0026 与
    `docs/adr/0002` 的判据欠账里。判据本体保留成 skip，等 M11 重新设计小窗口形状时再判。
    """
    pytest.skip("第二段溢出这个形状在压力预算规则下不可达：压缩总会把对话体压到保留尾部之内")


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
def test_ctrl_c_mid_turn_prints_the_aborted_note(tmp_path: Path) -> None:
    """seam ⑥ 1.5：真 Ctrl-C 落在段进行中 → stderr 有 `[轮] 收尾 ABORTED`，stdout 与日志里没有。

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
    _wait_until_log_contains(tmp_path, process, '"turn/end"', "写出被取消段的段边界")

    assert process.poll() is None, "取消当前段之后进程不该退出"
    process.stdin.write("第二条\n")
    process.stdin.flush()
    process.stdin.close()
    returncode, chat_stdout, chat_stderr = streams.finish()

    assert returncode == 0
    notes = [line for line in chat_stderr.splitlines() if "[轮] 收尾" in line]
    assert len(notes) == 1, "被取消的段在 stderr 上该有一行"
    assert "ABORTED" in notes[0]
    assert "[轮] 收尾" not in chat_stdout
    assert notes[0] not in _log_text(tmp_path)
    records = _records(tmp_path)
    types = [str(record["type"]) for record in records]
    assert "error/abort" in types
    turns = [record["payload"] for record in records if record["type"] == "turn/end"]
    assert turns[0]["stop_reason"] == "ABORTED"
    assert types.count("session/end") == 1, "会话还在：`session/end` 只在 stdin 关闭之后出现一次"
    assert types[-2:] == ["turn/end", "session/end"]
    assert records[-1]["payload"]["stop_reason"] == "MODEL_COMPLETED"


@pytest.mark.skipif(sys.platform != "win32", reason=_NOT_WINDOWS_REASON)
def test_ctrl_c_at_the_prompt_ends_the_session_without_traceback(tmp_path: Path) -> None:
    """seam ⑥ 1.6：真 Ctrl-C 落在没有段在跑时 → 退出码 0、stderr 里没有 `Traceback`。

    管道上的阻塞读不会被 Ctrl-C 打断（Windows 的 Ctrl-C 只在解释器回到字节码边界时才被消费），
    所以信号之后给 stdin 一个 EOF 让解释器回到边界上。收尾那一段缝隙里再连着送几次：
    落进缝隙里没人接，就是 design D7 要堵的那个洞。`session/end` 一落盘就停止送。"""

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
    # 连着送，直到 `session/end` 落盘或进程退出：收尾那一段只有几毫秒，一次送进缝隙里的概率不够高。
    # `session/end` 之后 MUST NOT 再送——那时 `main` 正在返回，再落一次控制台事件会把已经收好的
    # 会话按 Ctrl-C 的默认处置杀掉（退出码 0xC000013A），判据就看不见 `session/end` 这个事实了。
    for _ in range(40):
        if process.poll() is not None or '"session/end"' in _log_text(tmp_path):
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
    assert types.count("session/end") == 1, "连着送几次 Ctrl-C 也不能写出第二条 `session/end`"
    assert types.count("session/start") == 1
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
    assert all(
        session_id not in json.dumps(record["payload"], ensure_ascii=False)
        for record in _records(tmp_path)
    ), "日志里没有一条记录是为了打印这一行而存在"

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
        "4000",
        "--reserve",
        "100",
        "--append-system-prompt",
        "说明" * 10000,
        cwd=tmp_path,
        stdin_text="第一条\n第二条\n第三条\n",
    )

    assert result.returncode == 0
    turns = [record["payload"] for record in _records(tmp_path) if record["type"] == "turn/end"]
    assert [turn["stop_reason"] for turn in turns] == [
        "CONTEXT_WINDOW_EXCEEDED",
        "CONTEXT_WINDOW_EXCEEDED",
        "CONTEXT_WINDOW_EXCEEDED",
    ], "这一跑得先真发生连续溢出"

    lines = [line for line in result.stderr.splitlines() if line.startswith("[降不下去]")]
    assert len(lines) == 1, "连续溢出在 stderr 上多出一行说明，且只说一次"
    assert lines[0] not in result.stdout
    assert lines[0] not in _log_text(tmp_path)


def test_a_single_overflow_does_not_say_the_session_cannot_come_down(tmp_path: Path) -> None:
    """退休（2026-10-26）：要的是「只有第二段溢出」这个形状，压力预算规则下不可达。

    「`[降不下去]` 只在连续两段溢出时出现一次」这件事仍由
    `test_consecutive_overflows_say_the_session_cannot_come_down` 判；不可达的理由记在 ADR-0026。
    """
    pytest.skip("第二段溢出这个形状在压力预算规则下不可达：压缩总会把对话体压到保留尾部之内")


def test_chat_prints_tool_call_and_result_to_stderr(tmp_path: Path) -> None:
    (tmp_path / "a.md").write_text("alpha\n", encoding="utf-8")
    fixture = _fixture(
        tmp_path,
        "tool.json",
        [
            {
                "content": "",
                "finish_reason": "tool_calls",
                "tool_calls": [
                    {
                        "id": "c1",
                        "name": "read",
                        "arguments": {"file_path": "a.md"},
                    }
                ],
            },
            {"content": "读到了 alpha", "finish_reason": "stop"},
        ],
    )

    result = _chat("--fixture", str(fixture), cwd=tmp_path, stdin_text="读 a.md\n")

    assert result.returncode == 0
    assert "[tool] read" in result.stderr
    assert "file_path" in result.stderr
    assert "-> OK" in result.stderr
    assert "读到了 alpha" in result.stdout
    assert "读到了 alpha" not in result.stderr


def test_chat_resume_appends_to_the_same_log(tmp_path: Path) -> None:
    fixture = _fixture(
        tmp_path,
        "resume.json",
        [
            {"content": "第一次", "finish_reason": "stop"},
            {"content": "第二次", "finish_reason": "stop"},
        ],
    )
    first = _chat("--fixture", str(fixture), cwd=tmp_path, stdin_text="一\n")
    assert first.returncode == 0
    session_id = _log_files(tmp_path)[0].stem

    second_fixture = _fixture(
        tmp_path, "resume-second.json", [{"content": "第二次", "finish_reason": "stop"}]
    )
    second = _chat(
        "--resume",
        session_id,
        "--fixture",
        str(second_fixture),
        cwd=tmp_path,
        stdin_text="二\n",
    )

    assert second.returncode == 0
    records = _records(tmp_path)
    assert sum(1 for record in records if record["type"] == "session/start") == 1
    assert sum(1 for record in records if record["type"] == "user/message") == 2
    assert "第一次" in first.stdout
    assert "第二次" in second.stdout

    replay = _cli("replay", session_id, cwd=tmp_path)
    assert replay.returncode == 0
    assert "REPLAY_MISMATCH" not in replay.stderr


def test_resume_closes_hard_kill_gap_without_rewriting(tmp_path: Path) -> None:
    sessions = tmp_path / "sessions"
    log = EventLog.create(sessions, "s-half")
    assert isinstance(log, EventLog)
    log.append("session/start", {})
    log.append("turn/start", {"turn_id": "s1"})
    log.append("user/message", {"turn_id": "s1", "content": "半截"})
    log.append("step/start", {"step_id": "t1"})
    original = log.path.read_bytes()

    fixture = _fixture(tmp_path, "unused.json", [{"content": "不该跑", "finish_reason": "stop"}])
    result = _chat("--resume", "s-half", "--fixture", str(fixture), cwd=tmp_path, stdin_text="")

    assert result.returncode == 0
    assert log.path.read_bytes().startswith(original), "旧记录必须逐字节保留"
    records = _records(tmp_path)
    assert records[-1]["type"] == "session/end"


async def test_the_chat_handler_wakes_the_loop_instead_of_only_queueing() -> None:
    """SIGINT 必须经 `call_soon_threadsafe` 叫醒循环，不能只 `Event.set()`。

    直接置位只排一个回调；循环睡在 selector 里时不会醒——真实端点 UAT 里表现为
    「Ctrl-C 之后 bash 还跑满 30 s」。这条锁住那条唤醒路径。
    """

    class _RecordingLoop:
        def __init__(self) -> None:
            self.scheduled: list[object] = []

        def call_soon_threadsafe(self, callback: object, *args: object) -> None:
            self.scheduled.append(callback)

    cancel = asyncio.Event()
    loop = _RecordingLoop()
    signals = _ChatSignals(active=cancel, loop=loop)  # type: ignore[arg-type]

    _chat_sigint_handler(signals)(signal.SIGINT, None)

    # 处理器只调度，不直接动 asyncio 对象；调度到之后才置位。
    assert cancel.is_set() is False
    assert len(loop.scheduled) == 1
    assert callable(loop.scheduled[0])
    loop.scheduled[0]()
    assert cancel.is_set() is True


# ---------------------------------------------------------------------------
# restore-chat-streaming：默认流式、按步去重与回退
# ---------------------------------------------------------------------------


def test_streaming_is_the_default_and_writes_deltas_in_order(tmp_path: Path) -> None:
    """不传 flag 就是流式：增量按序落到 stdout，轮末不再重复整段（tasks 2.1）。"""
    fixture = _fixture(
        tmp_path,
        "delta.json",
        [{"content": "你好", "finish_reason": "stop", "deltas": ["你", "好"]}],
    )

    result = _chat("--fixture", fixture, cwd=tmp_path, stdin_text="说句话\n")

    assert result.returncode == 0
    assert result.stdout.count("你好") == 1
    assert result.stdout.index("你") < result.stdout.index("好")
    # `[answer] ` 走 stderr，正文走 stdout（design D4）
    assert "[answer]" in result.stderr
    assert "[answer]" not in result.stdout


def test_no_stream_keeps_the_old_projection(tmp_path: Path) -> None:
    """`--no-stream` 是旧行为：轮内没有输出，轮末一次性打印，stderr 没有 `[answer]`。"""
    fixture = _fixture(
        tmp_path,
        "delta2.json",
        [{"content": "你好", "finish_reason": "stop", "deltas": ["你", "好"]}],
    )

    result = _chat("--fixture", fixture, "--no-stream", cwd=tmp_path, stdin_text="说句话\n")

    assert result.returncode == 0
    assert result.stdout.splitlines() == ["> 你好", "> "]
    assert "[answer]" not in result.stderr


def test_the_two_streaming_flags_are_mutually_exclusive(tmp_path: Path) -> None:
    """两个 flag 同时给：参数解析失败，退出码 2，不建日志（spec scenario）。"""
    result = _cli("chat", "--stream", "--no-stream", cwd=tmp_path, stdin_text="")

    assert result.returncode == 2
    assert "not allowed" in result.stderr
    assert list((tmp_path / "sessions").glob("*.jsonl")) == []


def test_a_step_without_deltas_falls_back_at_step_end_once(tmp_path: Path) -> None:
    """无 delta 的步在步末回退，整轮仍只出现一次（tasks 2.4）。"""
    fixture = _fixture(
        tmp_path,
        "nod.json",
        [{"content": "答案", "finish_reason": "stop"}],
    )

    result = _chat("--fixture", fixture, cwd=tmp_path, stdin_text="问个问题\n")

    assert result.returncode == 0
    assert result.stdout.count("答案") == 1


def test_a_mixed_turn_does_not_reverse_the_order(tmp_path: Path) -> None:
    """同轮两步：第一步无 delta（步末回退）、第二步流式——先甲甲后乙乙，且各一次。"""
    fixture = _fixture(
        tmp_path,
        "mixed.json",
        [
            {
                "content": "甲甲",
                "finish_reason": "tool_calls",
                "tool_calls": [{"id": "c1", "name": "read", "arguments": {"file_path": "a.md"}}],
            },
            {"content": "乙乙", "finish_reason": "stop", "deltas": ["乙", "乙"]},
        ],
    )
    (tmp_path / "a.md").write_text("内容\n", encoding="utf-8")

    result = _chat("--fixture", fixture, cwd=tmp_path, stdin_text="读一下\n")

    assert result.returncode == 0
    # 精确序列：一步的正文在前、二步的增量在后，拼成同一行；倒序或重复都会红
    assert result.stdout.startswith("> 甲甲乙乙")


def test_empty_deltas_do_not_trigger_the_marker(tmp_path: Path) -> None:
    """只发空串 delta：按「没有流过非空 delta」处理，回退打印，且没有 `[answer]`。"""
    fixture = _fixture(
        tmp_path,
        "empty.json",
        [{"content": "答案", "finish_reason": "stop", "deltas": ["", ""]}],
    )

    result = _chat("--fixture", fixture, cwd=tmp_path, stdin_text="问\n")

    assert result.returncode == 0
    assert result.stdout.count("答案") == 1
    assert "[answer]" not in result.stderr


def test_two_steps_in_one_turn_mark_answer_once(tmp_path: Path) -> None:
    """一轮两步都流式：`[answer] ` 只打一次（spec scenario）。"""
    fixture = _fixture(
        tmp_path,
        "two.json",
        [
            {
                "content": "先读",
                "finish_reason": "tool_calls",
                "deltas": ["先", "读"],
                "tool_calls": [{"id": "c1", "name": "read", "arguments": {"file_path": "a.md"}}],
            },
            {"content": "再答", "finish_reason": "stop", "deltas": ["再", "答"]},
        ],
    )
    (tmp_path / "a.md").write_text("内容\n", encoding="utf-8")

    result = _chat("--fixture", fixture, cwd=tmp_path, stdin_text="读一下\n")

    assert result.returncode == 0
    assert result.stderr.count("[answer]") == 1
    assert result.stdout.index("先读") < result.stdout.index("再答")


def test_a_tool_only_step_does_not_emit_a_blank_line(tmp_path: Path) -> None:
    """只调工具、`content` 为空的步：步末不回退，不出空行（spec scenario）。"""
    fixture = _fixture(
        tmp_path,
        "toolonly.json",
        [
            {
                "content": "",
                "finish_reason": "tool_calls",
                "tool_calls": [{"id": "c1", "name": "read", "arguments": {"file_path": "a.md"}}],
            },
            {"content": "好了", "finish_reason": "stop"},
        ],
    )
    (tmp_path / "a.md").write_text("内容\n", encoding="utf-8")

    result = _chat("--fixture", fixture, cwd=tmp_path, stdin_text="读一下\n")

    assert result.returncode == 0
    # 提示符那一行 + 正文那一行；没有额外空行
    assert result.stdout.splitlines() == ["> 好了", "> "]


def test_streaming_does_not_change_the_event_types(tmp_path: Path) -> None:
    """流式不改变日志：类型序列与 `model/response` 键集合和 `--no-stream` 相同（tasks 2.11）。"""
    entries = [{"content": "你好", "finish_reason": "stop", "deltas": ["你", "好"]}]

    streamed = tmp_path / "streamed"
    streamed.mkdir()
    fixture_a = _fixture(streamed, "s.json", entries)
    first = _chat("--fixture", fixture_a, cwd=streamed, stdin_text="说句话\n")
    assert first.returncode == 0

    plain = tmp_path / "plain"
    plain.mkdir()
    fixture_b = _fixture(plain, "p.json", entries)
    second = _chat("--fixture", fixture_b, "--no-stream", cwd=plain, stdin_text="说句话\n")
    assert second.returncode == 0

    def shape(root: Path) -> tuple[list[str], set[str]]:
        log = next((root / "sessions").glob("*.jsonl"))
        records = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
        types = [record["type"] for record in records]
        keys = next(
            set(record["payload"]) for record in records if record["type"] == "model/response"
        )
        return types, keys

    assert shape(streamed) == shape(plain)
    assert "model/delta" not in shape(streamed)[0]


def test_the_first_delta_is_visible_before_the_turn_ends(tmp_path: Path) -> None:
    """实时性：首 delta 写上管道之后、本轮结束之前就能读到（tasks 2.2）。

    用真子进程 + 真管道：渲染器写首帧后在 stdout 上 `flush`，脚本随后还要停一会儿，
    父进程此刻必须已经读得到那个字。把写攒到轮末的实现会在这里读不到。
    """
    script = (
        "import asyncio, sys\n"
        "from mini_harness.cli.main import _ChatStreamRenderer\n"
        "async def main():\n"
        "    r = _ChatStreamRenderer()\n"
        "    await r.text('t1', '你')\n"
        "    sys.stderr.write('FIRST\\n'); sys.stderr.flush()\n"
        "    await asyncio.sleep(3)\n"
        "    await r.text('t1', '好')\n"
        "    r.finish_turn()\n"
        "asyncio.run(main())\n"
    )
    process = subprocess.Popen(
        [sys.executable, "-c", script],
        cwd=str(REPO_ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
    )
    try:
        assert process.stderr is not None
        assert process.stdout is not None
        assert "FIRST" in process.stderr.readline()

        seen: dict[str, str] = {}

        def read_one() -> None:
            seen["char"] = process.stdout.read(1) or ""

        reader = threading.Thread(target=read_one, daemon=True)
        reader.start()
        reader.join(timeout=0.5)

        assert seen.get("char") == "你", f"首帧在轮末前不可读：{seen!r}"
    finally:
        process.kill()
        process.wait(timeout=5)


def test_goal_rounds_each_get_their_own_line(tmp_path: Path) -> None:
    """目标连续两轮：正文各自成行，不被粘成一行；`[轮] n/cap` 在该轮正文之前（tasks 2.7）。"""
    fixture = _fixture(
        tmp_path,
        "goal.json",
        [
            {
                "content": "先立目标",
                "finish_reason": "tool_calls",
                "tool_calls": [
                    {
                        "id": "c1",
                        "name": "create_goal",
                        "arguments": {"objective": "分两轮说完", "max_rounds": 2},
                    }
                ],
            },
            {"content": "第一段", "finish_reason": "stop", "deltas": ["第一", "段"]},
            {"content": "第二段", "finish_reason": "stop", "deltas": ["第二", "段"]},
        ],
    )

    result = _chat("--fixture", fixture, cwd=tmp_path, stdin_text="开始\n")

    assert result.returncode == 0
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    # 人类轮那句 + 两个目标轮各一句，各占一行
    assert "第一段" in result.stdout
    assert "第二段" in result.stdout
    assert not any("第一段第二段" in line for line in lines), f"目标轮被粘成一行：{lines!r}"
    # [轮] 说明在该轮正文之前（pty 合流时也是这个顺序）
    assert result.stderr.index("[轮] 1/2") < result.stderr.index("[轮] 2/2")


def test_a_compaction_summary_never_reaches_stdout_while_streaming(tmp_path: Path) -> None:
    """流式下压缩摘要也不进 stdout：钩子只取该步真正的回复（tasks 2.6）。"""
    (tmp_path / "a.md").write_text(("x" * 100 + "\n") * 1000, encoding="utf-8")
    fixture = _fixture(
        tmp_path,
        "compact-stream.json",
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
    assert "这是回复" in result.stdout


def test_a_streamed_log_still_replays(tmp_path: Path) -> None:
    """流式跑出的日志仍可 replay：退出码 0、无 `REPLAY_MISMATCH`（tasks 2.11）。"""
    fixture = _fixture(
        tmp_path,
        "replay.json",
        [{"content": "你好", "finish_reason": "stop", "deltas": ["你", "好"]}],
    )

    result = _chat("--fixture", fixture, cwd=tmp_path, stdin_text="说句话\n")
    assert result.returncode == 0

    session_id = next((tmp_path / "sessions").glob("*.jsonl")).stem
    replay = _cli("replay", session_id, cwd=tmp_path)

    assert replay.returncode == 0, replay.stderr
    assert "REPLAY_MISMATCH" not in replay.stderr
    assert "REPLAY_MISMATCH" not in replay.stdout


@pytest.mark.skipif(sys.platform == "win32", reason=_WINDOWS_CTRL_C_REASON)
def test_stream_cancel_keeps_partial_text_without_reprinting_final(
    tmp_path: Path,
) -> None:
    fixture = _fixture(
        tmp_path,
        "stream-cancel.json",
        [
            {
                "content": "半",
                "deltas": ["半"],
                "finish_reason": "tool_calls",
                "tool_calls": [
                    {
                        "id": "c1",
                        "name": "bash",
                        "arguments": {"command": "sleep 30", "timeout_seconds": 30},
                    }
                ],
            }
        ],
    )
    process = _cli_process(
        "chat",
        "--provider",
        "mock",
        "--stream",
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
    stdout, _ = process.communicate(timeout=30)

    assert process.returncode == 0
    assert stdout.count("半") == 1


def test_chat_stream_prints_text_deltas_without_repeating_final_content(
    tmp_path: Path,
) -> None:
    fixture = tmp_path / "deltas.json"
    fixture.write_text(
        json.dumps(
            [{"content": "你好", "deltas": ["你", "好"], "finish_reason": "stop"}],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    result = _chat("--fixture", str(fixture), cwd=tmp_path, stdin_text="任务\n")

    assert result.returncode == 0
    assert result.stdout.count("你好") == 1
    assert "[answer]" in result.stderr


def test_chat_stream_sends_reasoning_to_stderr_only(tmp_path: Path) -> None:
    fixture = tmp_path / "reasoning.json"
    fixture.write_text(
        json.dumps(
            [
                {
                    "content": "答案",
                    "reasoning_deltas": ["先想"],
                    "finish_reason": "stop",
                }
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    result = _chat("--stream", "--fixture", str(fixture), cwd=tmp_path, stdin_text="任务\n")

    assert result.returncode == 0
    assert "[thinking] 先想" in result.stderr
    assert "[answer]" in result.stderr
    assert "先想" not in result.stdout


def test_chat_stream_falls_back_when_provider_sends_no_delta(tmp_path: Path) -> None:
    fixture = tmp_path / "no-delta.json"
    fixture.write_text(
        json.dumps([{"content": "完整答案", "finish_reason": "stop"}], ensure_ascii=False),
        encoding="utf-8",
    )

    result = _chat("--stream", "--fixture", str(fixture), cwd=tmp_path, stdin_text="任务\n")

    assert result.returncode == 0
    assert result.stdout.count("完整答案") == 1
