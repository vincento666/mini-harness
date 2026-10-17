"""seam ⑥：跨模块集成与退出码表。"""

from __future__ import annotations

import json
from pathlib import Path

from cli_blackbox import _cli
from paths import (
    HELLO_SCENARIO,
    TOOL_THEN_DONE_SCENARIO,
    TOOL_THEN_EXHAUST_SCENARIO,
    UNKNOWN_TOOL_SCENARIO,
)


def _run_scenario(
    tmp_path: Path, session_dir: Path, fixture: Path, *extra: str
) -> tuple[int, list[dict[str, object]]]:
    result = _cli(
        "run",
        "-p",
        "任务",
        "--provider",
        "mock",
        "--fixture",
        str(fixture),
        "--session-dir",
        str(session_dir),
        *extra,
        cwd=tmp_path,
    )
    files = sorted(session_dir.glob("*.jsonl"))
    events: list[dict[str, object]] = []
    if files:
        events = [json.loads(line) for line in files[0].read_text(encoding="utf-8").splitlines()]
    return result.returncode, events


def test_multi_turn_scenario_with_tool_call_and_fixture_exhaustion(tmp_path: Path) -> None:
    session_dir = tmp_path / "sessions"

    ok_code, ok_events = _run_scenario(tmp_path, session_dir / "ok", TOOL_THEN_DONE_SCENARIO)
    fail_code, fail_events = _run_scenario(
        tmp_path, session_dir / "fail", TOOL_THEN_EXHAUST_SCENARIO
    )

    assert ok_code == 0
    assert [event["type"] for event in ok_events].count("tool/call") == 1
    assert [event["type"] for event in ok_events].count("tool/result") == 1
    assert all(not str(event["type"]).startswith("error/") for event in ok_events)

    assert fail_code == 1
    errors = [event for event in fail_events if str(event["type"]).startswith("error/")]
    assert len(errors) == 1
    assert errors[0]["type"] == "error/model"
    assert errors[0]["payload"]["code"] == "PROVIDER_EXHAUSTED"


def test_the_registered_read_tool_reports_a_missing_path_as_a_result(tmp_path: Path) -> None:
    session_dir = tmp_path / "sessions"

    code, events = _run_scenario(tmp_path, session_dir / "missing", TOOL_THEN_DONE_SCENARIO)
    results = [event for event in events if event["type"] == "tool/result"]

    assert code == 0
    assert [event["payload"]["outcome"] for event in results] == ["PATH_NOT_FOUND"]
    assert all(not str(event["type"]).startswith("error/") for event in events)


def test_an_unregistered_tool_name_is_still_unknown_tool(tmp_path: Path) -> None:
    session_dir = tmp_path / "sessions"

    code, events = _run_scenario(tmp_path, session_dir / "unknown", UNKNOWN_TOOL_SCENARIO)
    results = [event for event in events if event["type"] == "tool/result"]

    assert code == 0
    assert [event["payload"]["outcome"] for event in results] == ["UNKNOWN_TOOL"]
    assert all(not str(event["type"]).startswith("error/") for event in events)


def test_no_m1_scenario_exits_with_the_reserved_codes(tmp_path: Path) -> None:
    session_dir = tmp_path / "sessions"
    broken = tmp_path / "broken.json"
    broken.write_text("{not json", encoding="utf-8")

    cases = [
        _run_scenario(tmp_path, session_dir / "happy", HELLO_SCENARIO),
        _run_scenario(tmp_path, session_dir / "tool", TOOL_THEN_DONE_SCENARIO),
        _run_scenario(tmp_path, session_dir / "max", TOOL_THEN_DONE_SCENARIO, "--max-turns", "1"),
        _run_scenario(tmp_path, session_dir / "exhaust", TOOL_THEN_EXHAUST_SCENARIO),
        _cli("run", cwd=tmp_path).returncode,
        _cli("run", "-p", "任务", "--max-turns", "0", cwd=tmp_path).returncode,
        _cli("run", "-p", "任务", "--provider", "deepseek", cwd=tmp_path).returncode,
        _run_scenario(tmp_path, session_dir / "broken", broken),
    ]

    codes = [case if isinstance(case, int) else case[0] for case in cases]
    assert codes == [0, 0, 0, 1, 2, 2, 2, 2]
    assert all(code not in (3, 4) for code in codes)

    for case in cases:
        if isinstance(case, int):
            continue
        code, events = case
        if code not in (0, 2):
            assert any(str(event["type"]).startswith("error/") for event in events)

    outcomes = [
        event["payload"]["outcome"]
        for case in cases
        if not isinstance(case, int)
        for event in case[1]
        if event["type"] == "tool/result"
    ]
    assert outcomes
    assert set(outcomes) == {"PATH_NOT_FOUND"}
