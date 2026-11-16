"""seam ①④：token 四桶计量（M14b）。"""

from __future__ import annotations

import json
from pathlib import Path

from mini_harness.events.record import EventRecord
from mini_harness.metering import collect_usage


def _rec(seq: int, event_type: str, payload: dict[str, object]) -> EventRecord:
    return EventRecord(
        schema_version=1,
        session_id="s-usage",
        seq=seq,
        ts=f"2026-11-14T00:00:{seq:02d}+00:00",
        type=event_type,
        payload=payload,
    )


def test_four_buckets_are_summed() -> None:
    records = [
        _rec(0, "session/start", {"prompt": "任务"}),
        _rec(
            1,
            "model/response",
            {
                "turn_id": "t1",
                "usage": {"input_tokens": 100, "cache_read_tokens": 20, "output_tokens": 30},
            },
        ),
        _rec(
            2,
            "model/response",
            {"turn_id": "t2", "usage": {"input_tokens": 50, "output_tokens": 10}},
        ),
    ]

    turns, total = collect_usage(records)

    assert [turn.turn_id for turn in turns] == ["t1", "t2"]
    # 适配器的 input_tokens 已是未缓存部分；命中单列在 cache_read。
    assert total.input_uncached == 150
    assert total.cache_read == 20
    assert total.cache_write == 0
    assert total.output == 40


def test_reasoning_is_not_added_twice() -> None:
    records = [
        _rec(
            0,
            "model/response",
            {"turn_id": "t1", "usage": {"output_tokens": 30, "reasoning_tokens": 12}},
        )
    ]

    _, total = collect_usage(records)

    assert total.output == 30


def test_a_turn_without_usage_is_skipped() -> None:
    records = [
        _rec(0, "model/response", {"turn_id": "t1"}),
        _rec(1, "model/response", {"turn_id": "t2", "usage": {"input_tokens": 5}}),
    ]

    turns, total = collect_usage(records)

    assert [turn.turn_id for turn in turns] == ["t2"]
    assert total.input_uncached == 5


def test_the_last_response_of_a_turn_wins() -> None:
    records = [
        _rec(0, "model/response", {"turn_id": "t1", "usage": {"input_tokens": 10}}),
        _rec(1, "model/response", {"turn_id": "t1", "usage": {"input_tokens": 20}}),
    ]

    turns, total = collect_usage(records)

    assert len(turns) == 1
    assert total.input_uncached == 20


def test_the_usage_command_prints_turns_and_total(tmp_path: Path) -> None:
    from cli_blackbox import _cli

    records = [
        {
            "schema_version": 1,
            "type": "session/start",
            "session_id": "s-usage",
            "seq": 0,
            "ts": "2026-11-14T00:00:00+00:00",
            "payload": {"prompt": "任务"},
        },
        {
            "schema_version": 1,
            "type": "model/response",
            "session_id": "s-usage",
            "seq": 1,
            "ts": "2026-11-14T00:00:01+00:00",
            "payload": {
                "turn_id": "t1",
                "usage": {"input_tokens": 10, "output_tokens": 5},
            },
        },
    ]
    log = tmp_path / "s-usage.jsonl"
    log.write_text("\n".join(json.dumps(item) for item in records) + "\n", encoding="utf-8")

    result = _cli("usage", "s-usage", "--session-dir", str(tmp_path), cwd=tmp_path)

    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    assert data["turns"][0]["turn_id"] == "t1"
    assert data["total"]["input_uncached"] == 10
    assert data["total"]["output"] == 5
    assert data["cost"] is None
