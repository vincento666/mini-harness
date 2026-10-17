"""seam ③：`glob` 与 `grep`——相对路径与带行号的命中，无匹配不是失败。"""

from __future__ import annotations

import os
from pathlib import Path

from mini_harness.tools.dispatch import DispatchOutcome
from paths import copy_repo_to
from tool_harness import dispatch_call

_FIXTURE_MD = {"README.md", "notes/plan.md", "notes/meeting.md", "notes/retro.md", "notes/spec.md"}


async def _glob(workspace: Path, **arguments: object) -> DispatchOutcome:
    return await dispatch_call(workspace, "glob", dict(arguments))


async def _grep(workspace: Path, **arguments: object) -> DispatchOutcome:
    return await dispatch_call(workspace, "grep", dict(arguments))


async def test_glob_returns_the_five_markdown_files_relative_to_the_workspace(
    tmp_path: Path,
) -> None:
    copy_repo_to(tmp_path)

    outcome = await _glob(tmp_path, pattern="**/*.md")

    assert outcome.result.outcome == "OK"
    assert set(outcome.result.content.splitlines()) == _FIXTURE_MD


async def test_glob_never_returns_a_directory(tmp_path: Path) -> None:
    (tmp_path / "notes").mkdir()
    (tmp_path / "notes" / "a.md").write_text("内容\n", encoding="utf-8")

    outcome = await _glob(tmp_path, pattern="**/*")

    assert outcome.result.outcome == "OK"
    assert outcome.result.content.splitlines() == ["notes/a.md"]


async def test_glob_orders_by_modification_time_newest_first(tmp_path: Path) -> None:
    copy_repo_to(tmp_path)
    oldest_first = [
        "notes/meeting.md",
        "notes/plan.md",
        "README.md",
        "notes/spec.md",
        "notes/retro.md",
    ]
    base = 1_700_000_000
    for index, name in enumerate(oldest_first):
        stamp = base + index * 10
        os.utime(tmp_path / name, (stamp, stamp))

    outcome = await _glob(tmp_path, pattern="**/*.md")

    assert outcome.result.content.splitlines() == list(reversed(oldest_first))


async def test_glob_lists_at_most_one_hundred_paths(tmp_path: Path) -> None:
    for index in range(130):
        (tmp_path / f"f{index}.md").write_text("内容\n", encoding="utf-8")

    outcome = await _glob(tmp_path, pattern="*.md")

    lines = outcome.result.content.splitlines()
    assert len(lines) == 101
    assert "130" in lines[-1]


async def test_glob_with_no_match_is_ok_and_says_so(tmp_path: Path) -> None:
    copy_repo_to(tmp_path)

    outcome = await _glob(tmp_path, pattern="**/*.rst")

    assert outcome.result.outcome == "OK"
    assert "没有" in outcome.result.content


async def test_grep_returns_file_line_number_and_line_text(tmp_path: Path) -> None:
    copy_repo_to(tmp_path)

    outcome = await _grep(tmp_path, pattern="TODO")

    assert outcome.result.outcome == "OK"
    lines = outcome.result.content.splitlines()
    assert len(lines) == 3
    assert {line.split(":")[0] for line in lines} == {
        "notes/plan.md",
        "notes/meeting.md",
        "notes/retro.md",
    }
    for line in lines:
        _, number, text = line.split(":", 2)
        assert number.strip().isdigit()
        assert text.startswith(" TODO")


async def test_grep_lists_at_most_two_hundred_and_fifty_matches(tmp_path: Path) -> None:
    (tmp_path / "many.txt").write_text("命中\n" * 300, encoding="utf-8")

    outcome = await _grep(tmp_path, pattern="命中")

    lines = outcome.result.content.splitlines()
    assert len(lines) == 251
    assert "300" in lines[-1]


async def test_grep_with_no_hit_is_ok_and_says_so(tmp_path: Path) -> None:
    copy_repo_to(tmp_path)

    outcome = await _grep(tmp_path, pattern="这个词不存在于任何文件里")

    assert outcome.result.outcome == "OK"
    assert "没有" in outcome.result.content


async def test_an_invalid_pattern_is_an_argument_error(tmp_path: Path) -> None:
    copy_repo_to(tmp_path)
    before = (tmp_path / "notes" / "plan.md").read_bytes()

    outcome = await _grep(tmp_path, pattern="[")

    assert outcome.result.outcome == "TOOL_ARGS_INVALID"
    assert "正则" in outcome.result.content
    assert (tmp_path / "notes" / "plan.md").read_bytes() == before


async def test_a_search_root_that_is_a_file_is_not_a_directory(tmp_path: Path) -> None:
    """搜索根必须是目录：给了文件不能报成标签与语义相反的 `IS_A_DIRECTORY`。"""
    (tmp_path / "a.md").write_text("命中\n", encoding="utf-8")

    grep = await _grep(tmp_path, pattern="命中", path="a.md")
    glob = await _glob(tmp_path, pattern="*", path="a.md")
    missing = await _glob(tmp_path, pattern="*", path="不存在")

    assert grep.result.outcome == "NOT_A_DIRECTORY"
    assert glob.result.outcome == "NOT_A_DIRECTORY"
    assert "目录" in grep.result.content
    assert missing.result.outcome == "PATH_NOT_FOUND"
