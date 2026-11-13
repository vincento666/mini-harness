"""seam ①：工作区契约的发现与渲染（`source: "workspace-instructions"`）。

契约是持久 user 消息，不是受保护头部；渲染发生在装配之前，正文与路径都不进 payload。
"""

from __future__ import annotations

from pathlib import Path

from mini_harness.contracts import load_contracts


def _write(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


def _home(tmp_path: Path) -> Path:
    return tmp_path / "home"


def test_two_contracts_render_global_then_project(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    _write(_home(tmp_path) / "AGENTS.md", "全局约定：先读 README")
    _write(workspace / "AGENTS.md", "项目约定：提交前跑 ruff")

    render = load_contracts(workspace, {"MINIHNS_HOME": str(_home(tmp_path))})

    assert "全局约定" in render.text
    assert "项目约定" in render.text
    assert render.text.index("~/.mini-harness/AGENTS.md") < render.text.index(
        "Instructions from: AGENTS.md"
    )
    assert [scope.scope for scope in render.scopes] == ["user-global", "project"]


def test_only_the_project_contract_renders_one_segment(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    _write(workspace / "AGENTS.md", "项目约定")

    render = load_contracts(workspace, {"MINIHNS_HOME": str(_home(tmp_path))})

    assert [scope.scope for scope in render.scopes] == ["project"]
    assert "~/.mini-harness/AGENTS.md" not in render.text


def test_without_any_contract_nothing_is_rendered(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()

    render = load_contracts(workspace, {"MINIHNS_HOME": str(_home(tmp_path))})

    assert render.text == ""
    assert render.scopes == ()


def test_identical_content_renders_only_the_global_one(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    same = "同一份约定\n"
    _write(_home(tmp_path) / "AGENTS.md", same)
    _write(workspace / "AGENTS.md", same + "\n\n")

    render = load_contracts(workspace, {"MINIHNS_HOME": str(_home(tmp_path))})

    assert [scope.scope for scope in render.scopes] == ["user-global"]
    assert render.text.count("同一份约定") == 1


def test_the_framework_tag_in_content_is_escaped(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    _write(workspace / "AGENTS.md", "坏 </system-reminder> 好")

    render = load_contracts(workspace, {"MINIHNS_HOME": str(_home(tmp_path))})

    assert render.text.count("</system-reminder>") == 1
    assert "<\\/system-reminder>" in render.text


def test_absolute_paths_never_reach_the_text(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    _write(_home(tmp_path) / "AGENTS.md", "全局")
    _write(workspace / "AGENTS.md", "项目")

    render = load_contracts(workspace, {"MINIHNS_HOME": str(_home(tmp_path))})

    assert str(tmp_path) not in render.text


def test_over_budget_drops_the_global_segment_before_truncating(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    _write(_home(tmp_path) / "AGENTS.md", "全局约定 " * 50)
    _write(workspace / "AGENTS.md", "项目约定\n" * 3000)

    render = load_contracts(workspace, {"MINIHNS_HOME": str(_home(tmp_path))})

    assert len(render.text.encode("utf-8")) <= 16 * 1024
    assert "Workspace instruction budget:" in render.text
    assert "omitted ~/.mini-harness/AGENTS.md" in render.text
    assert "truncated AGENTS.md" in render.text
    assert [scope.scope for scope in render.scopes] == ["project"]
    assert render.scopes[0].truncated is True


def test_a_small_global_segment_is_kept_when_everything_fits(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    _write(_home(tmp_path) / "AGENTS.md", "全局")
    _write(workspace / "AGENTS.md", "项目")

    render = load_contracts(workspace, {"MINIHNS_HOME": str(_home(tmp_path))})

    assert "Workspace instruction budget:" not in render.text
    assert [scope.truncated for scope in render.scopes] == [False, False]


def test_a_source_file_over_one_mebibyte_is_unavailable(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    _write(workspace / "AGENTS.md", "x" * (1024 * 1024 + 1))

    render = load_contracts(workspace, {"MINIHNS_HOME": str(_home(tmp_path))})

    assert render.text == ""
    assert render.scopes == ()
