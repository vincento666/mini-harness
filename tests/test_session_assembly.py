"""seam ②：装配从 CLI 私有函数抽成库——四个入口共用同一条装配路（H1 design D2）。

判据只碰 `assemble` 的返回值，不碰 CLI 的退出码表：退出码是入口的事，装配只回答
「材料齐不齐、失败是什么码」。
"""

from __future__ import annotations

import json
from pathlib import Path

from mini_harness.session.assembly import AssemblyRequest, Failure, Prepared, assemble


def test_assemble_returns_a_prepared_for_a_mock_request(tmp_path: Path) -> None:
    fixture = tmp_path / "turns.json"
    fixture.write_text(
        json.dumps([{"content": "好", "finish_reason": "stop"}], ensure_ascii=False),
        encoding="utf-8",
    )
    session_dir = tmp_path / "sessions"

    prepared = assemble(
        AssemblyRequest(
            provider="mock",
            fixture=str(fixture),
            session_dir=str(session_dir),
        ),
        {},
    )

    assert isinstance(prepared, Prepared)
    assert prepared.settings.provider_name == "mock"
    assert prepared.log.path.parent == session_dir
    assert prepared.log.path.is_file()
    assert prepared.log.path.read_text(encoding="utf-8") == ""
    assert [spec.name for spec in prepared.registry.specs()] == [
        "read",
        "write",
        "edit",
        "glob",
        "grep",
        "bash",
        "subagent",
        "skill",
    ]


def test_assemble_builds_one_registry_behind_the_settings_snapshot(tmp_path: Path) -> None:
    """装配期只观察一次：注册表快照与 `settings.skills`（审计快照）是同一份。"""
    workspace = tmp_path / "ws"
    skill_dir = workspace / ".minihns" / "skills" / "tdd"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: tdd\ndescription: 先写判据\n---\n正文\n", encoding="utf-8"
    )
    fixture = tmp_path / "turns.json"
    fixture.write_text(
        json.dumps([{"content": "好", "finish_reason": "stop"}], ensure_ascii=False),
        encoding="utf-8",
    )

    prepared = assemble(
        AssemblyRequest(
            workspace=str(workspace),
            provider="mock",
            fixture=str(fixture),
            session_dir=str(tmp_path / "sessions"),
        ),
        {"MINIHNS_HOME": str(tmp_path / "home")},
    )

    assert isinstance(prepared, Prepared)
    assert prepared.skills_registry is not None
    assert prepared.skills_registry.snapshot().skills == prepared.settings.skills
    assert [skill.name for skill in prepared.settings.skills] == ["tdd"]


def test_assemble_failure_happens_before_any_log(tmp_path: Path) -> None:
    """配置、窗口、工具、provider/密钥的失败都在 `EventLog.start` 之前（design D10）。"""
    fixture = tmp_path / "turns.json"
    fixture.write_text(
        json.dumps([{"content": "好", "finish_reason": "stop"}], ensure_ascii=False),
        encoding="utf-8",
    )
    session_dir = tmp_path / "sessions"

    missing_key_workspace = tmp_path / "missing-key"
    missing_key_workspace.mkdir()
    invalid_config_workspace = tmp_path / "invalid-config"
    invalid_config_workspace.mkdir()
    (invalid_config_workspace / "mini.config.toml").write_text(
        'max_turns = "three"\n', encoding="utf-8"
    )
    unknown_tool_workspace = tmp_path / "unknown-tool"
    unknown_tool_workspace.mkdir()
    (unknown_tool_workspace / "mini.config.toml").write_text(
        'tools = ["web_search"]\n', encoding="utf-8"
    )

    requests = [
        AssemblyRequest(
            provider="deepseek",
            workspace=str(missing_key_workspace),
            session_dir=str(session_dir),
        ),
        AssemblyRequest(
            provider="mock",
            fixture=str(fixture),
            workspace=str(invalid_config_workspace),
            session_dir=str(session_dir),
        ),
        AssemblyRequest(
            provider="mock",
            fixture=str(fixture),
            workspace=str(unknown_tool_workspace),
            session_dir=str(session_dir),
        ),
    ]

    for request in requests:
        failure = assemble(request, {})
        assert isinstance(failure, Failure)
        assert failure.code == "INVALID_ARGUMENT"
        assert list(session_dir.glob("*.jsonl")) == []
