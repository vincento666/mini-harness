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

    render = load_contracts(workspace, _home(tmp_path))

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

    render = load_contracts(workspace, _home(tmp_path))

    assert [scope.scope for scope in render.scopes] == ["project"]
    assert "~/.mini-harness/AGENTS.md" not in render.text


def test_without_any_contract_nothing_is_rendered(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()

    render = load_contracts(workspace, _home(tmp_path))

    assert render.text == ""
    assert render.scopes == ()


def test_identical_content_renders_only_the_global_one(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    same = "同一份约定\n"
    _write(_home(tmp_path) / "AGENTS.md", same)
    _write(workspace / "AGENTS.md", same + "\n\n")

    render = load_contracts(workspace, _home(tmp_path))

    assert [scope.scope for scope in render.scopes] == ["user-global"]
    assert render.text.count("同一份约定") == 1


def test_the_framework_tag_in_content_is_escaped(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    _write(workspace / "AGENTS.md", "坏 </system-reminder> 好")

    render = load_contracts(workspace, _home(tmp_path))

    assert render.text.count("</system-reminder>") == 1
    assert "<\\/system-reminder>" in render.text


def test_absolute_paths_never_reach_the_text(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    _write(_home(tmp_path) / "AGENTS.md", "全局")
    _write(workspace / "AGENTS.md", "项目")

    render = load_contracts(workspace, _home(tmp_path))

    assert str(tmp_path) not in render.text


def test_over_budget_drops_the_global_segment_before_truncating(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    _write(_home(tmp_path) / "AGENTS.md", "全局约定 " * 50)
    _write(workspace / "AGENTS.md", "项目约定\n" * 3000)

    render = load_contracts(workspace, _home(tmp_path))

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

    render = load_contracts(workspace, _home(tmp_path))

    assert "Workspace instruction budget:" not in render.text
    assert [scope.truncated for scope in render.scopes] == [False, False]


def test_a_source_file_over_one_mebibyte_is_unavailable(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    _write(workspace / "AGENTS.md", "x" * (1024 * 1024 + 1))

    render = load_contracts(workspace, _home(tmp_path))

    assert render.text == ""
    assert render.scopes == ()


def _session(tmp_path: Path):  # type: ignore[no-untyped-def]
    from dataclasses import replace

    from mini_harness.config import build_registry
    from mini_harness.provider import FixtureProvider
    from tool_harness import build_session_env

    workspace = tmp_path / "ws"
    workspace.mkdir(parents=True, exist_ok=True)
    _, env = build_session_env(
        tmp_path,
        "s-contract",
        FixtureProvider(entries=[{"content": "好", "finish_reason": "stop"}]),
        workspace=workspace,
        registry=build_registry(None),
    )
    return replace(env, contracts_home=_home(tmp_path))


def _contract_messages(env) -> list[object]:  # type: ignore[no-untyped-def]
    from mini_harness.events import read_events

    return [
        record
        for record in read_events(env.log.path)
        if record.type == "user/message"
        and record.payload.get("source") == "workspace-instructions"
    ]


def test_the_contract_is_injected_before_the_first_assembled(tmp_path: Path) -> None:
    import asyncio

    from mini_harness.events import read_events
    from mini_harness.loop.turn_loop import run_session_env

    workspace = tmp_path / "ws"
    workspace.mkdir()
    _write(workspace / "AGENTS.md", "项目约定")
    env = _session(tmp_path)

    asyncio.run(run_session_env(prompt="任务", entry="run", env=env, cancel=asyncio.Event()))

    messages = _contract_messages(env)
    assert len(messages) == 1
    assembled = next(
        record.seq for record in read_events(env.log.path) if record.type == "context/assembled"
    )
    assert messages[0].seq < assembled
    assert "项目约定" in messages[0].payload["content"]


def test_without_files_no_contract_message(tmp_path: Path) -> None:
    from mini_harness.loop.turn_loop import _maybe_emit_contracts

    env = _session(tmp_path)
    _maybe_emit_contracts(env, "s1")

    assert _contract_messages(env) == []


def test_an_unchanged_contract_is_not_repeated(tmp_path: Path) -> None:
    from mini_harness.loop.turn_loop import _maybe_emit_contracts

    workspace = tmp_path / "ws"
    workspace.mkdir()
    _write(workspace / "AGENTS.md", "项目约定")
    env = _session(tmp_path)

    _maybe_emit_contracts(env, "s1")
    _maybe_emit_contracts(env, "s1")

    assert len(_contract_messages(env)) == 1


def test_a_changed_contract_appends_a_replacement(tmp_path: Path) -> None:
    from mini_harness.loop.turn_loop import _maybe_emit_contracts

    workspace = tmp_path / "ws"
    workspace.mkdir()
    _write(workspace / "AGENTS.md", "旧约定")
    env = _session(tmp_path)
    _maybe_emit_contracts(env, "s1")

    _write(workspace / "AGENTS.md", "新约定")
    _maybe_emit_contracts(env, "s1")

    messages = _contract_messages(env)
    assert len(messages) == 2
    assert "旧约定" in messages[0].payload["content"]
    assert "新约定" in messages[1].payload["content"]


def test_removing_both_files_appends_a_removal_notice(tmp_path: Path) -> None:
    from mini_harness.loop.turn_loop import _maybe_emit_contracts

    workspace = tmp_path / "ws"
    workspace.mkdir()
    _write(workspace / "AGENTS.md", "项目约定")
    env = _session(tmp_path)
    _maybe_emit_contracts(env, "s1")

    (workspace / "AGENTS.md").unlink()
    _maybe_emit_contracts(env, "s1")

    messages = _contract_messages(env)
    assert len(messages) == 2
    assert "Instructions removed: AGENTS.md" in messages[1].payload["content"]


def test_the_memory_file_is_not_mixed_in(tmp_path: Path) -> None:
    """契约与记忆分开：MEMORY.md 不出现在契约消息里。"""
    workspace = tmp_path / "ws"
    workspace.mkdir()
    _write(_home(tmp_path) / "AGENTS.md", "全局契约")
    _write(_home(tmp_path) / "MEMORY.md", "记忆：不要混进来")

    render = load_contracts(workspace, _home(tmp_path))

    assert "全局契约" in render.text
    assert "记忆" not in render.text


def test_the_contract_body_never_enters_session_start(tmp_path: Path) -> None:
    """正文只在消息里；`session/start` 的 payload 不带它。"""
    import asyncio

    from mini_harness.events import read_events
    from mini_harness.loop.turn_loop import run_session_env

    workspace = tmp_path / "ws"
    workspace.mkdir()
    _write(workspace / "AGENTS.md", "不应进 payload 的正文")
    env = _session(tmp_path)

    asyncio.run(run_session_env(prompt="任务", entry="run", env=env, cancel=asyncio.Event()))

    start = next(record for record in read_events(env.log.path) if record.type == "session/start")
    assert "不应进 payload 的正文" not in str(start.payload)
