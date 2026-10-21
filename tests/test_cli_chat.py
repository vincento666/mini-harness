"""seam ⑥：`minihns chat` 的黑盒（真实子进程）。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from cli_blackbox import _cli
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


def test_an_empty_stdin_is_a_legal_session(tmp_path: Path) -> None:
    """seam ⑥：stdin 立刻 EOF 也是一份合法会话——没有段，也没有回合。"""
    fixture = _fixture(tmp_path, "unused.json", [{"content": "不该出现", "finish_reason": "stop"}])

    result = _chat("--fixture", fixture, cwd=tmp_path, stdin_text="")

    assert result.returncode == 0
    assert _types(tmp_path) == ["session/start", "session/end"]


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
            "tool_calls": [
                {"id": f"c{index}", "name": "read", "arguments": {"file_path": "a.md"}}
            ],
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
    turn_ids = [record["payload"]["turn_id"] for record in records if record["type"] == "turn/start"]
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
