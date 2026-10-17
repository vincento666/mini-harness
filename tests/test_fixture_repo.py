"""seam ③ 的前置判据：只读 fixture 仓库与「复制到 tmp 工作区」helper。

fixture 仓库只读：测试一律先复制再跑，绝不原地改（见 `docs/handoff-2026-10-15.md` 决策 32）。
"""

from __future__ import annotations

from pathlib import Path

from paths import FIXTURE_REPO_DIR, copy_repo_to

REPO_MARKDOWN_FILES = {
    "README.md",
    "notes/meeting.md",
    "notes/plan.md",
    "notes/retro.md",
    "notes/spec.md",
}


def test_copy_contains_the_five_markdown_files(tmp_path: Path) -> None:
    copied = copy_repo_to(tmp_path)

    found = {path.relative_to(copied).as_posix() for path in copied.rglob("*.md") if path.is_file()}

    assert found == REPO_MARKDOWN_FILES


def test_copying_leaves_the_fixture_repo_untouched(tmp_path: Path) -> None:
    def snapshot() -> dict[str, bytes]:
        return {
            path.relative_to(FIXTURE_REPO_DIR).as_posix(): path.read_bytes()
            for path in sorted(FIXTURE_REPO_DIR.rglob("*"))
            if path.is_file()
        }

    before = snapshot()

    copy_repo_to(tmp_path / "workspace")

    assert snapshot() == before
