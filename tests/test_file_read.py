"""seam ③：`read` 的契约——带行号的窗口、参数取值范围、三种失败都是结果。"""

from __future__ import annotations

from pathlib import Path

from mini_harness.tools.dispatch import DispatchOutcome
from mini_harness.tools.file_tools import READ_MAX_BYTES, READ_MAX_LINE_LENGTH
from tool_harness import dispatch_call


async def _read(workspace: Path, **arguments: object) -> DispatchOutcome:
    return await dispatch_call(workspace, "read", dict(arguments))


async def test_a_three_line_file_comes_back_with_line_numbers(tmp_path: Path) -> None:
    (tmp_path / "notes.txt").write_text("一\n二\n三\n", encoding="utf-8")

    outcome = await _read(tmp_path, file_path="notes.txt")

    assert outcome.result.outcome == "OK"
    assert outcome.result.content.splitlines() == ["1: 一", "2: 二", "3: 三"]


async def test_offset_and_limit_select_one_line(tmp_path: Path) -> None:
    (tmp_path / "notes.txt").write_text("一\n二\n三\n", encoding="utf-8")

    outcome = await _read(tmp_path, file_path="notes.txt", offset=2, limit=1)

    assert outcome.result.outcome == "OK"
    assert outcome.result.content == "2: 二"


async def test_the_default_window_is_two_thousand_lines(tmp_path: Path) -> None:
    body = "\n".join(f"行{index}" for index in range(1, 2501))
    (tmp_path / "long.txt").write_text(f"{body}\n", encoding="utf-8")

    outcome = await _read(tmp_path, file_path="long.txt")

    lines = outcome.result.content.splitlines()
    assert len(lines) == 2000
    assert lines[0] == "1: 行1"
    assert lines[-1] == "2000: 行2000"


async def test_zero_offset_or_limit_is_an_argument_error(tmp_path: Path) -> None:
    (tmp_path / "notes.txt").write_text("一\n", encoding="utf-8")
    before = (tmp_path / "notes.txt").read_bytes()

    zero_offset = await _read(tmp_path, file_path="notes.txt", offset=0)
    zero_limit = await _read(tmp_path, file_path="notes.txt", limit=0)

    assert zero_offset.result.outcome == "TOOL_ARGS_INVALID"
    assert zero_limit.result.outcome == "TOOL_ARGS_INVALID"
    assert "offset" in zero_offset.result.content
    assert "limit" in zero_limit.result.content
    assert (tmp_path / "notes.txt").read_bytes() == before


async def test_missing_directory_and_non_text_are_results_with_bytes_untouched(
    tmp_path: Path,
) -> None:
    (tmp_path / "dir").mkdir()
    blob = tmp_path / "blob.bin"
    raw = bytes([0xFF, 0xFE, 0x00, 0x41])
    blob.write_bytes(raw)

    missing = await _read(tmp_path, file_path="nope.md")
    directory = await _read(tmp_path, file_path="dir")
    non_text = await _read(tmp_path, file_path="blob.bin")

    assert missing.result.outcome == "PATH_NOT_FOUND"
    assert "nope.md" in missing.result.content
    assert directory.result.outcome == "IS_A_DIRECTORY"
    assert non_text.result.outcome == "NOT_UTF8_TEXT"
    assert blob.read_bytes() == raw


async def test_a_missing_file_path_touches_nothing(tmp_path: Path) -> None:
    outcome = await _read(tmp_path, limit=5)

    assert outcome.result.outcome == "TOOL_ARGS_INVALID"
    assert "file_path" in outcome.result.content
    assert list(tmp_path.iterdir()) == []


async def test_read_has_a_50_kib_window_and_no_spill(tmp_path: Path) -> None:
    body = "\n".join("x" * 3000 for _ in range(40))
    (tmp_path / "big.txt").write_text(body, encoding="utf-8")

    outcome = await _read(tmp_path, file_path="big.txt")

    assert outcome.result.outcome == "OK"
    assert len(outcome.result.content.encode("utf-8")) <= READ_MAX_BYTES + 200
    assert "(Output capped." in outcome.result.content
    assert "offset=" in outcome.result.content
    assert ".mini-harness/spill" not in outcome.result.content


async def test_read_truncates_a_long_line(tmp_path: Path) -> None:
    (tmp_path / "long.txt").write_text("x" * 5000 + "\n", encoding="utf-8")

    outcome = await _read(tmp_path, file_path="long.txt")

    assert f"line truncated to {READ_MAX_LINE_LENGTH} chars" in outcome.result.content
    assert len(outcome.result.content) < 5000
