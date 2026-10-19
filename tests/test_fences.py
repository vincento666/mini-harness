"""seam ②：围栏判定——路径键、工作区边界、档位、两条轴各自独立。"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from mini_harness.loop.settings import ApprovalMode, SandboxLevel
from mini_harness.tools.fences import DispatchContext, judge_fence, path_key
from tool_harness import dispatch_context


def _context(
    workspace: Path,
    *,
    sandbox: SandboxLevel = "workspace-write",
    approval: ApprovalMode = "ask",
) -> DispatchContext:
    return dispatch_context(workspace, sandbox=sandbox, approval=approval)


def test_the_same_file_written_two_ways_gets_one_path_key(tmp_path: Path) -> None:
    (tmp_path / "Notes").mkdir()
    (tmp_path / "Notes" / "Plan.MD").write_text("内容\n", encoding="utf-8")

    upper = path_key(tmp_path, "Notes/Plan.MD")
    lower = path_key(tmp_path, "notes/plan.md")

    if os.name == "nt":
        assert upper == lower, "Windows 上大小写折叠成同一个键，否则换一种写法就能绕过 CAS"
    else:
        assert upper != lower, "大小写敏感的平台上它们本来就是两个文件"


def test_dot_dot_segments_collapse_into_one_key(tmp_path: Path) -> None:
    assert path_key(tmp_path, "a/../b.md") == path_key(tmp_path, "b.md")


def test_a_symlink_key_resolves_to_its_target(tmp_path: Path) -> None:
    target = tmp_path / "target.md"
    target.write_text("内容\n", encoding="utf-8")
    link = tmp_path / "link.md"
    try:
        os.symlink(target, link)
    except OSError as exc:
        pytest.skip(f"这台机器不允许创建符号链接：{exc}")

    assert path_key(tmp_path, "link.md") == path_key(tmp_path, "target.md")


def test_a_junction_key_resolves_to_its_target_without_privileges(tmp_path: Path) -> None:
    """seam ②：Windows 侧的链接判据用 junction——建它不需要特权。

    上面那条符号链接判据在这台机器上跑不起来（创建符号链接要特权），它在 CI 的 Linux 上真跑；
    两条判据断言同一件事：键解析到目标，不解析到链接本身。
    """
    if os.name != "nt":
        pytest.skip("junction 是 Windows 的形状；POSIX 侧看上面那条符号链接判据")
    target = tmp_path / "nested"
    target.mkdir()
    (target / "a.md").write_text("内容\n", encoding="utf-8")
    link = tmp_path / "via"

    made = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(link), str(target)],
        capture_output=True,
        text=True,
    )
    if made.returncode != 0:
        pytest.skip(f"这台机器不允许创建 junction：{made.stdout.strip() or made.stderr.strip()}")

    assert path_key(tmp_path, "via/a.md") == path_key(tmp_path, "nested/a.md")
    assert path_key(tmp_path, "via/a.md") != path_key(tmp_path, "a.md")


def test_a_write_outside_the_workspace_is_denied(tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside.md"

    decision = judge_fence(_context(tmp_path), raw_path=str(outside), mutates=True)

    assert decision.outcome == "DENIED"
    assert decision.code == "OUTSIDE_WORKSPACE"
    assert not outside.exists()


def test_read_like_tools_are_not_bounded_by_the_workspace(tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside.md"

    decision = judge_fence(_context(tmp_path), raw_path=str(outside), mutates=False)

    assert decision.outcome == "ALLOWED"


def test_read_only_denies_every_mutating_tool(tmp_path: Path) -> None:
    decision = judge_fence(_context(tmp_path, sandbox="read-only"), raw_path="a.md", mutates=True)

    assert decision.outcome == "DENIED"
    assert decision.code == "SANDBOX_DENIES_WRITE"

    read_only = _context(tmp_path, sandbox="read-only")
    assert judge_fence(read_only, raw_path="a.md", mutates=False).outcome == "ALLOWED"


def test_danger_full_access_lifts_the_workspace_boundary(tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside.md"

    decision = judge_fence(
        _context(tmp_path, sandbox="danger-full-access", approval="auto"),
        raw_path=str(outside),
        mutates=True,
    )

    assert decision.outcome == "ALLOWED"


def test_the_two_axes_stay_independent(tmp_path: Path) -> None:
    # 最高档位仍默认问人。
    top_level = judge_fence(
        _context(tmp_path, sandbox="danger-full-access"), raw_path="a.md", mutates=True
    )
    assert top_level.outcome == "NEEDS_APPROVAL"

    # 全自动不放宽档位。
    auto_read_only = judge_fence(
        _context(tmp_path, sandbox="read-only", approval="auto"), raw_path="a.md", mutates=True
    )
    assert auto_read_only.outcome == "DENIED"
    assert auto_read_only.code == "SANDBOX_DENIES_WRITE"
