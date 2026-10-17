"""seam ③：`edit` 的字面替换与 CAS——读到的原文不一致就是 STALE_EDIT。"""

from __future__ import annotations

from pathlib import Path

from mini_harness.events import read_events
from mini_harness.tools.dispatch import DispatchOutcome
from paths import copy_repo_to
from tool_harness import DONE, dispatch_call, run_fixture_session, tool_call_entry, tool_outcomes

_ORIGINAL = "第一行 目标\n第二行 别的\n第三行 目标\n"


async def _edit(workspace: Path, **arguments: object) -> DispatchOutcome:
    records = arguments.pop("records", None)
    return await dispatch_call(workspace, "edit", dict(arguments), records=records)


async def test_editing_a_read_file_replaces_only_the_one_match(tmp_path: Path) -> None:
    (tmp_path / "a.md").write_text("目标\n", encoding="utf-8")
    entries = [
        tool_call_entry("read", "c1", file_path="a.md"),
        tool_call_entry("edit", "c2", file_path="a.md", old_string="目标", new_string="换掉"),
        DONE,
    ]

    log, _ = await run_fixture_session(tmp_path, "s-edit", entries)

    assert tool_outcomes(log) == ["OK", "OK"]
    assert (tmp_path / "a.md").read_text(encoding="utf-8") == "换掉\n"


async def test_edit_replaces_only_the_first_match_unless_replace_all(tmp_path: Path) -> None:
    (tmp_path / "a.md").write_text(_ORIGINAL, encoding="utf-8")
    entries = [
        tool_call_entry("read", "c1", file_path="a.md"),
        tool_call_entry("edit", "c2", file_path="a.md", old_string="目标", new_string="换掉"),
        DONE,
    ]

    log, _ = await run_fixture_session(tmp_path, "s-one-match", entries)

    assert tool_outcomes(log) == ["OK", "EDIT_TARGET_AMBIGUOUS"]
    assert (tmp_path / "a.md").read_text(encoding="utf-8") == _ORIGINAL


async def test_replace_all_replaces_every_match(tmp_path: Path) -> None:
    (tmp_path / "a.md").write_text(_ORIGINAL, encoding="utf-8")
    entries = [
        tool_call_entry("read", "c1", file_path="a.md"),
        tool_call_entry(
            "edit",
            "c2",
            file_path="a.md",
            old_string="目标",
            new_string="换掉",
            replace_all=True,
        ),
        DONE,
    ]

    log, _ = await run_fixture_session(tmp_path, "s-all-match", entries)

    assert tool_outcomes(log) == ["OK", "OK"]
    assert (tmp_path / "a.md").read_text(encoding="utf-8") == _ORIGINAL.replace("目标", "换掉")


async def test_missing_target_and_ambiguous_target_are_two_different_results(
    tmp_path: Path,
) -> None:
    (tmp_path / "a.md").write_text(_ORIGINAL, encoding="utf-8")
    entries = [
        tool_call_entry("read", "c1", file_path="a.md"),
        tool_call_entry("edit", "c2", file_path="a.md", old_string="没有这个词", new_string="换掉"),
        tool_call_entry("edit", "c3", file_path="a.md", old_string="目标", new_string="换掉"),
        DONE,
    ]

    log, _ = await run_fixture_session(tmp_path, "s-two-results", entries)

    assert tool_outcomes(log) == ["OK", "EDIT_TARGET_NOT_FOUND", "EDIT_TARGET_AMBIGUOUS"]
    assert (tmp_path / "a.md").read_text(encoding="utf-8") == _ORIGINAL


async def test_editing_a_file_changed_outside_the_session_is_stale(tmp_path: Path) -> None:
    target = tmp_path / "a.md"
    target.write_text(_ORIGINAL, encoding="utf-8")
    entries = [
        tool_call_entry("read", "c1", file_path="a.md"),
        DONE,
    ]

    log, _ = await run_fixture_session(tmp_path, "s-stale", entries)
    assert tool_outcomes(log) == ["OK"]

    target.write_text("有人在外面改过这个文件\n", encoding="utf-8")
    outside = target.read_bytes()

    outcome = await _edit(
        tmp_path,
        file_path="a.md",
        old_string="目标",
        new_string="换掉",
        records=read_events(log.path),
    )

    assert outcome.result.outcome == "STALE_EDIT"
    assert target.read_bytes() == outside


async def test_edit_without_reading_first_is_refused(tmp_path: Path) -> None:
    (tmp_path / "a.md").write_text(_ORIGINAL, encoding="utf-8")

    outcome = await _edit(tmp_path, file_path="a.md", old_string="目标", new_string="换掉")

    assert outcome.result.outcome == "WRITE_WITHOUT_READ"
    assert (tmp_path / "a.md").read_text(encoding="utf-8") == _ORIGINAL


async def test_an_empty_old_string_is_an_argument_error(tmp_path: Path) -> None:
    (tmp_path / "a.md").write_text(_ORIGINAL, encoding="utf-8")
    entries = [
        tool_call_entry("read", "c1", file_path="a.md"),
        tool_call_entry("edit", "c2", file_path="a.md", old_string="", new_string="换掉"),
        DONE,
    ]

    log, _ = await run_fixture_session(tmp_path, "s-empty-old", entries)

    assert tool_outcomes(log) == ["OK", "TOOL_ARGS_INVALID"]
    invalid = [
        record.payload["content"]
        for record in read_events(log.path)
        if record.type == "tool/result" and record.payload["outcome"] == "TOOL_ARGS_INVALID"
    ]
    assert "old_string" in invalid[0]
    assert (tmp_path / "a.md").read_text(encoding="utf-8") == _ORIGINAL


async def test_edit_in_the_fixture_repo_replaces_a_todo_line(tmp_path: Path) -> None:
    copy_repo_to(tmp_path)
    old = "TODO：把覆盖率记账的三步写进交接文档，别靠记忆。"
    entries = [
        tool_call_entry("read", "c1", file_path="notes/retro.md"),
        tool_call_entry(
            "edit",
            "c2",
            file_path="notes/retro.md",
            old_string=old,
            new_string="DONE：覆盖率记账的三步见 AGENTS.md 命令段。",
        ),
        DONE,
    ]

    log, _ = await run_fixture_session(tmp_path, "s-fixture-edit", entries)

    assert tool_outcomes(log) == ["OK", "OK"]
    body = (tmp_path / "notes" / "retro.md").read_text(encoding="utf-8")
    assert "DONE：覆盖率记账的三步见 AGENTS.md 命令段。" in body
    assert "TODO" not in body


async def test_a_later_read_replaces_the_earlier_one(tmp_path: Path) -> None:
    """同一路径后来的成功读覆盖先前的：改完再读，第二次 `edit` 用的是新读到的原文。"""
    (tmp_path / "a.md").write_text("第一行\n第二行\n", encoding="utf-8")
    entries = [
        tool_call_entry("read", "c1", file_path="a.md"),
        tool_call_entry(
            "edit", "c2", file_path="a.md", old_string="第一行", new_string="改过的第一行"
        ),
        tool_call_entry("read", "c3", file_path="a.md"),
        tool_call_entry(
            "edit", "c4", file_path="a.md", old_string="改过的第一行", new_string="再改一次"
        ),
        DONE,
    ]

    log, _ = await run_fixture_session(tmp_path, "s-reread", entries)

    assert tool_outcomes(log) == ["OK", "OK", "OK", "OK"]
    assert (tmp_path / "a.md").read_text(encoding="utf-8") == "再改一次\n第二行\n"


async def test_a_write_does_not_count_as_having_read_it(tmp_path: Path) -> None:
    """写成功不算读过：紧接着的 `edit` 仍是 `WRITE_WITHOUT_READ`，不是 `STALE_EDIT`。"""
    entries = [
        tool_call_entry("write", "c1", file_path="new.md", content="新写的\n"),
        tool_call_entry("edit", "c2", file_path="new.md", old_string="新写的", new_string="改一下"),
        DONE,
    ]

    log, _ = await run_fixture_session(tmp_path, "s-write-not-read", entries)

    assert tool_outcomes(log) == ["OK", "WRITE_WITHOUT_READ"]
    assert (tmp_path / "new.md").read_text(encoding="utf-8") == "新写的\n"
