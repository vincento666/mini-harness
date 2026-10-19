"""seam ①：超时与取消落进回合——`tool/cancelled` 与它的配对。"""

from __future__ import annotations

from pathlib import Path

from mini_harness.events import EventRecord, read_events
from mini_harness.provider import FixtureProvider
from tool_harness import (
    DONE,
    full_registry,
    result_outcomes,
    run_session_fixture,
    tool_call,
    turn_entry,
)

_LOOP_SCRIPT = "import time\n\nwhile True:\n    time.sleep(0.1)\n"


def _cancelled(records: list[EventRecord]) -> list[EventRecord]:
    return [record for record in records if record.type == "tool/cancelled"]


async def test_a_timed_out_call_does_not_stop_the_rest_of_the_batch(tmp_path: Path) -> None:
    """规格 scenario「超时后回合继续」：第一个 `bash` 超时，后面那个 `read` 照常派发。"""
    (tmp_path / "a.md").write_text("甲\n", encoding="utf-8")
    (tmp_path / "loop.py").write_text(_LOOP_SCRIPT, encoding="utf-8")

    log, outcome = await run_session_fixture(
        tmp_path,
        "s-timeout-continues",
        FixtureProvider(
            entries=[
                turn_entry(
                    tool_call("bash", "c1", command="python loop.py", timeout_seconds=1),
                    tool_call("read", "c2", file_path="a.md"),
                ),
                DONE,
            ]
        ),
        registry=full_registry(),
        max_turns=4,
    )

    records = read_events(log.path)
    assert isinstance(records, list)
    assert result_outcomes(records) == [("c1", "TOOL_TIMEOUT"), ("c2", "OK")]

    # 1.3 的 payload 形状：只有 `turn_id` 与 `tool_call_id`，不带命令输出。
    assert len(_cancelled(records)) == 1
    assert _cancelled(records)[0].payload["tool_call_id"] == "c1"
    assert set(_cancelled(records)[0].payload) == {"turn_id", "tool_call_id"}

    turn_end = [record for record in records if record.type == "turn/end"]
    assert [record.payload["stop_reason"] for record in turn_end] == [
        "TOOL_CALLS",
        "MODEL_COMPLETED",
    ]
    assert outcome.stop_reason == "MODEL_COMPLETED"


async def test_a_run_without_interruption_writes_no_tool_cancelled(tmp_path: Path) -> None:
    """规格 scenario「没有打断就没有该记录」。"""
    (tmp_path / "a.md").write_text("甲\n", encoding="utf-8")

    log, _ = await run_session_fixture(
        tmp_path,
        "s-no-cancelled",
        FixtureProvider(entries=[turn_entry(tool_call("read", "c1", file_path="a.md")), DONE]),
        registry=full_registry(),
        max_turns=4,
    )

    records = read_events(log.path)
    assert isinstance(records, list)
    assert _cancelled(records) == []
