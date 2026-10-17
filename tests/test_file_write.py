"""seam ③④：`write` 与写前必读——「算不算读过」只由日志前缀派生。"""

from __future__ import annotations

from pathlib import Path

from mini_harness.events import read_events
from mini_harness.tools.dispatch import DispatchOutcome
from mini_harness.tools.fences import path_key, reads_from_records
from paths import copy_repo_to
from tool_harness import (
    DONE,
    dispatch_call,
    run_fixture_session,
    tool_call_entry,
    tool_outcomes,
)

_RAW_BLOB = bytes([0xFF, 0xFE, 0x00, 0x41])


async def _write(workspace: Path, **arguments: object) -> DispatchOutcome:
    return await dispatch_call(workspace, "write", dict(arguments))


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
        tool_call_entry("read", "c1", file_path="a.md"),
        tool_call_entry("write", "c2", file_path="a.md", content="改写\n"),
        DONE,
    ]

    log, _ = await run_fixture_session(tmp_path, "s-readwrite", entries)

    assert tool_outcomes(log) == ["OK", "OK"]
    assert (tmp_path / "a.md").read_text(encoding="utf-8") == "改写\n"


async def test_a_failed_read_does_not_count_as_reading(tmp_path: Path) -> None:
    blob = tmp_path / "blob.bin"
    blob.write_bytes(_RAW_BLOB)
    entries = [
        tool_call_entry("read", "c1", file_path="blob.bin"),
        tool_call_entry("write", "c2", file_path="blob.bin", content="覆盖\n"),
        DONE,
    ]

    log, _ = await run_fixture_session(tmp_path, "s-failedread", entries)

    assert tool_outcomes(log) == ["NOT_UTF8_TEXT", "WRITE_WITHOUT_READ"]
    assert blob.read_bytes() == _RAW_BLOB


async def test_a_new_session_does_not_inherit_the_read_set(tmp_path: Path) -> None:
    (tmp_path / "a.md").write_text("原文\n", encoding="utf-8")

    log_a, _ = await run_fixture_session(
        tmp_path, "s-a", [tool_call_entry("read", "c1", file_path="a.md"), DONE]
    )
    assert tool_outcomes(log_a) == ["OK"]

    log_b, _ = await run_fixture_session(
        tmp_path, "s-b", [tool_call_entry("write", "c1", file_path="a.md", content="改写\n"), DONE]
    )

    assert tool_outcomes(log_b) == ["WRITE_WITHOUT_READ"]
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
        DONE,
    ]

    log, _ = await run_fixture_session(tmp_path, "s-prefix", entries)
    records = read_events(log.path)

    first = reads_from_records(records, tmp_path)
    second = reads_from_records(records, tmp_path)

    assert first == second
    assert path_key(tmp_path, "notes/plan.md") in first
    assert path_key(tmp_path, "blob.bin") not in first


async def test_writing_to_a_directory_is_refused(tmp_path: Path) -> None:
    """规格追认：`write` 的目标是目录时是 `IS_A_DIRECTORY`，目录内容不变。"""
    (tmp_path / "sub").mkdir()

    outcome = await _write(tmp_path, file_path="sub", content="x\n")

    assert outcome.result.outcome == "IS_A_DIRECTORY"
    assert list((tmp_path / "sub").iterdir()) == []


async def test_a_parent_path_that_is_a_file_is_an_io_failure_not_an_exception(
    tmp_path: Path,
) -> None:
    """不变量 B：失败也是结果。父路径是已存在的文件时不抛异常，也不写任何东西。"""
    (tmp_path / "a.md").write_text("原文\n", encoding="utf-8")

    outcome = await _write(tmp_path, file_path="a.md/b.md", content="新文件\n")

    assert outcome.result.outcome == "TOOL_IO_FAILED"
    assert outcome.fence_code is None
    assert not (tmp_path / "b.md").exists()


async def test_an_io_failure_stays_a_result_and_the_turn_still_closes(tmp_path: Path) -> None:
    """seam ①：执行段的 I/O 失败不打断回合，`turn/end` 照写，会话正常收尾。"""
    (tmp_path / "a.md").write_text("原文\n", encoding="utf-8")
    entries = [
        tool_call_entry("write", "c1", file_path="a.md/b.md", content="新文件\n"),
        DONE,
    ]

    log, outcome = await run_fixture_session(tmp_path, "s-io-failure", entries)

    assert tool_outcomes(log) == ["TOOL_IO_FAILED"]
    assert (tmp_path / "a.md").read_text(encoding="utf-8") == "原文\n"
    turn_ends = [record for record in read_events(log.path) if record.type == "turn/end"]
    assert [str(record.payload["stop_reason"]) for record in turn_ends] == [
        "TOOL_CALLS",
        "MODEL_COMPLETED",
    ]
    assert outcome.failure_code is None
    assert outcome.stop_reason == "MODEL_COMPLETED"
