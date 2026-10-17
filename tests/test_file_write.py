"""seam ③④：`write` 与写前必读——「算不算读过」只由日志前缀派生。"""

from __future__ import annotations

import asyncio
from pathlib import Path

from mini_harness.events import EventLog, read_events
from mini_harness.loop import RunOutcome, SessionSettings, run_session
from mini_harness.provider import FixtureProvider
from mini_harness.tools import ToolRegistry
from mini_harness.tools.dispatch import DispatchOutcome
from mini_harness.tools.fences import path_key, read_paths_from_records
from mini_harness.tools.file_tools import file_tool_definitions
from paths import copy_repo_to
from tool_harness import dispatch_call

_RAW_BLOB = bytes([0xFF, 0xFE, 0x00, 0x41])


def _call(name: str, call_id: str, **arguments: object) -> dict[str, object]:
    return {
        "content": f"调用 {name}",
        "finish_reason": "tool_calls",
        "tool_calls": [{"id": call_id, "name": name, "arguments": dict(arguments)}],
    }


_DONE: dict[str, object] = {"content": "算了", "finish_reason": "stop"}


async def _write(workspace: Path, **arguments: object) -> DispatchOutcome:
    return await dispatch_call(workspace, "write", dict(arguments))


async def _run_session(
    tmp_path: Path, session_id: str, entries: list[dict[str, object]]
) -> tuple[EventLog, RunOutcome]:
    log = EventLog.create(session_dir=tmp_path, session_id=session_id)
    settings = SessionSettings(
        workspace=tmp_path, provider_name="mock", max_turns=4, approval="auto"
    )
    outcome = await run_session(
        prompt="任务",
        provider=FixtureProvider(entries=entries),
        log=log,
        registry=ToolRegistry(file_tool_definitions()),
        settings=settings,
        cancel=asyncio.Event(),
    )
    return log, outcome


def _outcomes(log: EventLog) -> list[str]:
    results = [record for record in read_events(log.path) if record.type == "tool/result"]
    return [record.payload["outcome"] for record in results]


async def test_writing_a_new_file_creates_it_and_the_parent_dirs(tmp_path: Path) -> None:
    outcome = await _write(tmp_path, file_path="notes/deep/a.md", content="新文件\n")

    assert outcome.result.outcome == "OK"
    assert (tmp_path / "notes" / "deep" / "a.md").read_text(encoding="utf-8") == "新文件\n"


async def test_overwriting_an_unread_file_is_refused_and_leaves_the_bytes_alone(
    tmp_path: Path,
) -> None:
    target = tmp_path / "a.md"
    target.write_bytes(b"original\r\nbytes\xff")
    before = target.read_bytes()

    outcome = await _write(tmp_path, file_path="a.md", content="覆盖\n")

    assert outcome.result.outcome == "WRITE_WITHOUT_READ"
    assert target.read_bytes() == before


async def test_danger_full_access_still_requires_reading_first(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    outside = tmp_path / "outside.md"
    outside.write_text("原文\n", encoding="utf-8")

    outcome = await dispatch_call(
        workspace,
        "write",
        {"file_path": str(outside), "content": "改写\n"},
        sandbox="danger-full-access",
    )

    assert outcome.result.outcome == "WRITE_WITHOUT_READ"
    assert outside.read_text(encoding="utf-8") == "原文\n"


async def test_reading_first_then_writing_succeeds_in_the_same_session(tmp_path: Path) -> None:
    (tmp_path / "a.md").write_text("原文\n", encoding="utf-8")
    entries = [
        _call("read", "c1", file_path="a.md"),
        _call("write", "c2", file_path="a.md", content="改写\n"),
        _DONE,
    ]

    log, _ = await _run_session(tmp_path, "s-readwrite", entries)

    assert _outcomes(log) == ["OK", "OK"]
    assert (tmp_path / "a.md").read_text(encoding="utf-8") == "改写\n"


async def test_a_failed_read_does_not_count_as_reading(tmp_path: Path) -> None:
    blob = tmp_path / "blob.bin"
    blob.write_bytes(_RAW_BLOB)
    entries = [
        _call("read", "c1", file_path="blob.bin"),
        _call("write", "c2", file_path="blob.bin", content="覆盖\n"),
        _DONE,
    ]

    log, _ = await _run_session(tmp_path, "s-failedread", entries)

    assert _outcomes(log) == ["NOT_UTF8_TEXT", "WRITE_WITHOUT_READ"]
    assert blob.read_bytes() == _RAW_BLOB


async def test_a_new_session_does_not_inherit_the_read_set(tmp_path: Path) -> None:
    (tmp_path / "a.md").write_text("原文\n", encoding="utf-8")

    log_a, _ = await _run_session(tmp_path, "s-a", [_call("read", "c1", file_path="a.md"), _DONE])
    assert _outcomes(log_a) == ["OK"]

    log_b, _ = await _run_session(
        tmp_path, "s-b", [_call("write", "c1", file_path="a.md", content="改写\n"), _DONE]
    )

    assert _outcomes(log_b) == ["WRITE_WITHOUT_READ"]
    assert (tmp_path / "a.md").read_text(encoding="utf-8") == "原文\n"


async def test_the_same_log_prefix_yields_the_same_read_set(tmp_path: Path) -> None:
    copy_repo_to(tmp_path)
    (tmp_path / "blob.bin").write_bytes(_RAW_BLOB)
    entries = [
        {
            "content": "读两个",
            "finish_reason": "tool_calls",
            "tool_calls": [
                {"id": "c1", "name": "read", "arguments": {"file_path": "notes/plan.md"}},
                {"id": "c2", "name": "read", "arguments": {"file_path": "blob.bin"}},
            ],
        },
        _DONE,
    ]

    log, _ = await _run_session(tmp_path, "s-prefix", entries)
    records = read_events(log.path)

    first = read_paths_from_records(records, tmp_path)
    second = read_paths_from_records(records, tmp_path)

    assert first == second
    assert path_key(tmp_path, "notes/plan.md") in first
    assert path_key(tmp_path, "blob.bin") not in first
