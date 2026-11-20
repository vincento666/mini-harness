"""seam ④：`replay` 对 goal 轮次的日志自洽校验。"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest

from cli_blackbox import _cli
from mini_harness.events import read_events
from mini_harness.loop import ENTRY_RUN, run_session_env
from mini_harness.provider import AssistantTurn, ProviderFailure, ToolCall
from mini_harness.tools import ToolRegistry
from mini_harness.tools.assistant import assistant_tool_definitions
from mini_harness.tools.goal import goal_tool_definitions
from tool_harness import build_session_env

OBJECTIVE = "修好失败的用例"


def _registry() -> ToolRegistry:
    return ToolRegistry([*assistant_tool_definitions(), *goal_tool_definitions()])


class _ThreeRounds:
    """第一次建目标（上限 3），其后每轮先探一下再收尾：跑满三轮后落 `round-limit`。

    零工具调用的 goal 轮会被停滞熔断（D14），所以每轮要有一个真实的工具调用。
    """

    def __init__(self) -> None:
        self.calls = 0

    async def generate(
        self, messages: Any, tools: Any, signal: Any, on_delta: Any = None
    ) -> AssistantTurn | ProviderFailure:
        self.calls += 1
        if self.calls == 1:
            return AssistantTurn(
                content="先立个目标",
                finish_reason="tool_calls",
                tool_calls=[
                    ToolCall(
                        id="c1",
                        name="create_goal",
                        arguments={"objective": OBJECTIVE, "max_rounds": 3},
                    )
                ],
            )
        if messages[-1].role == "tool":
            return AssistantTurn(content="这一轮做完了", finish_reason="stop")
        return AssistantTurn(
            content="先读一下目标",
            finish_reason="tool_calls",
            tool_calls=[ToolCall(id=f"g{self.calls}", name="get_goal", arguments={})],
        )


def _rounds_log(tmp_path: Path) -> tuple[str, Path]:
    """在进程内跑一份三轮续跑的日志；返回 session id 与文件路径。"""
    directory = tmp_path / "sessions"
    log, env = build_session_env(
        tmp_path, "s-goal-replay", _ThreeRounds(), registry=_registry(), session_dir=directory
    )
    asyncio.run(
        run_session_env(prompt="把这件活干完", entry=ENTRY_RUN, env=env, cancel=asyncio.Event())
    )
    return log.session_id, log.path


def _tamper(source: Path, target: Path, mutate: Any) -> None:
    """按行改一份日志：`mutate` 拿到整份记录列表，就地改，写回去。"""
    lines = [json.loads(line) for line in source.read_text(encoding="utf-8").splitlines()]
    mutate(lines)
    target.write_text(
        "\n".join(json.dumps(line, ensure_ascii=False) for line in lines) + "\n", encoding="utf-8"
    )


def _goal_message_indexes(lines: list[dict[str, Any]]) -> list[int]:
    return [
        index
        for index, line in enumerate(lines)
        if line["type"] == "user/message"
        and line["payload"].get("source", {}).get("kind") == "goal"
    ]


def _goal_update_indexes(lines: list[dict[str, Any]]) -> list[int]:
    return [index for index, line in enumerate(lines) if line["type"] == "goal/updated"]


def test_a_real_three_round_log_replays_cleanly(tmp_path: Path) -> None:
    session_id, path = _rounds_log(tmp_path)

    records = read_events(path)
    assert [
        record.payload["source"]["round"]
        for record in records
        if record.type == "user/message"
        and isinstance(record.payload.get("source"), dict)
        and record.payload["source"].get("kind") == "goal"
    ] == [1, 2, 3]

    result = _cli("replay", session_id, "--session-dir", str(path.parent), cwd=tmp_path)

    assert result.returncode == 0, result.stderr
    assert "REPLAY_MISMATCH" not in result.stderr


def _replay_tampered(tmp_path: Path, mutate: Any) -> Any:
    _, path = _rounds_log(tmp_path)
    broken = tmp_path / "sessions" / "broken.jsonl"
    _tamper(path, broken, mutate)
    return _cli("replay", "broken", "--session-dir", str(broken.parent), cwd=tmp_path)


def test_a_skipped_round_number_is_rejected(tmp_path: Path) -> None:
    def mutate(lines: list[dict[str, Any]]) -> None:
        second = _goal_message_indexes(lines)[1]
        lines[second]["payload"]["source"]["round"] = 5

    result = _replay_tampered(tmp_path, mutate)

    assert result.returncode != 0
    assert "goal" in result.stderr


def test_a_zero_round_number_is_rejected(tmp_path: Path) -> None:
    def mutate(lines: list[dict[str, Any]]) -> None:
        first = _goal_message_indexes(lines)[0]
        lines[first]["payload"]["source"]["round"] = 0

    result = _replay_tampered(tmp_path, mutate)

    assert result.returncode != 0


def test_a_round_beyond_the_cap_is_rejected(tmp_path: Path) -> None:
    def mutate(lines: list[dict[str, Any]]) -> None:
        for index in _goal_update_indexes(lines):
            lines[index]["payload"]["goal"]["max_rounds"] = 2

    result = _replay_tampered(tmp_path, mutate)

    assert result.returncode != 0


def test_a_stale_revision_is_rejected(tmp_path: Path) -> None:
    def mutate(lines: list[dict[str, Any]]) -> None:
        second = _goal_message_indexes(lines)[1]
        lines[second]["payload"]["source"]["revision"] = 9

    result = _replay_tampered(tmp_path, mutate)

    assert result.returncode != 0


def test_a_bumped_rounds_started_is_rejected(tmp_path: Path) -> None:
    def mutate(lines: list[dict[str, Any]]) -> None:
        first_update = _goal_update_indexes(lines)[1]
        lines[first_update]["payload"]["goal"]["rounds_started"] += 1

    result = _replay_tampered(tmp_path, mutate)

    assert result.returncode != 0


def test_a_goal_message_after_the_goal_stopped_is_rejected(tmp_path: Path) -> None:
    def mutate(lines: list[dict[str, Any]]) -> None:
        first_round = _goal_update_indexes(lines)[1]
        lines[first_round]["payload"]["goal"]["phase"] = "paused"

    result = _replay_tampered(tmp_path, mutate)

    assert result.returncode != 0


@pytest.mark.parametrize("mutate", [lambda lines: None])
def test_an_untouched_copy_replays_cleanly(tmp_path: Path, mutate: Any) -> None:
    """对照组：拷贝本身不该让 replay 变红，否则上面五条判据什么都没证明。"""
    result = _replay_tampered(tmp_path, mutate)

    assert result.returncode == 0, result.stderr


def test_a_goal_source_without_a_round_is_rejected(tmp_path: Path) -> None:
    def mutate(lines: list[dict[str, Any]]) -> None:
        first = _goal_message_indexes(lines)[0]
        lines[first]["payload"]["source"].pop("round")

    result = _replay_tampered(tmp_path, mutate)

    assert result.returncode != 0
    assert "来源字段不完整" in result.stderr


def test_a_goal_source_without_a_revision_is_rejected(tmp_path: Path) -> None:
    def mutate(lines: list[dict[str, Any]]) -> None:
        first = _goal_message_indexes(lines)[0]
        lines[first]["payload"]["source"].pop("revision")

    result = _replay_tampered(tmp_path, mutate)

    assert result.returncode != 0
    assert "缺 revision" in result.stderr


def test_a_goal_message_for_an_unknown_goal_is_rejected(tmp_path: Path) -> None:
    def mutate(lines: list[dict[str, Any]]) -> None:
        second = _goal_message_indexes(lines)[1]
        lines[second]["payload"]["source"]["goal_id"] = "g-other"

    result = _replay_tampered(tmp_path, mutate)

    assert result.returncode != 0
    assert "当前没有这个目标" in result.stderr
