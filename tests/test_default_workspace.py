"""default-session-workspace：默认工作区 = 用户目录下的会话专属目录。

判据分两层：装配层直测（默认/显式/发现根/resume 四条），黑盒层跑真 CLI（产物落点、
启动目录干净、越界写仍拒）。黑盒一律把 `MINIHNS_HOME` 指到临时目录，不碰真实家目录。
"""

from __future__ import annotations

import json
from pathlib import Path

from cli_blackbox import _cli
from mini_harness.session.assembly import AssemblyRequest, Failure, Prepared, assemble


def _fixture(tmp_path: Path, *turns: dict[str, object]) -> str:
    path = tmp_path / "turns.json"
    path.write_text(json.dumps(list(turns), ensure_ascii=False), encoding="utf-8")
    return str(path)


def _write_file_turn(*, path: str, content: str = "好") -> dict[str, object]:
    return {
        "content": "",
        "finish_reason": "tool_calls",
        "tool_calls": [
            {"id": "c1", "name": "write", "arguments": {"file_path": path, "content": content}}
        ],
    }


def test_default_workspace_is_the_session_directory(tmp_path: Path) -> None:
    """未给 workspace：工作区 = `$MINIHNS_HOME/workspaces/<sid>/`，装配期就建好。"""
    prepared = assemble(
        AssemblyRequest(
            provider="mock",
            fixture=_fixture(tmp_path, {"content": "好", "finish_reason": "stop"}),
            session_dir=str(tmp_path / "sessions"),
        ),
        {"MINIHNS_HOME": str(tmp_path / "home")},
    )

    assert isinstance(prepared, Prepared)
    expected = tmp_path / "home" / "workspaces" / prepared.log.session_id
    assert prepared.settings.workspace == expected
    assert expected.is_dir()


def test_explicit_workspace_keeps_the_old_semantics(tmp_path: Path) -> None:
    """显式 workspace：逐点同旧（绝对化、不自动创建），会话目录不出现。"""
    workspace = tmp_path / "explicit"
    prepared = assemble(
        AssemblyRequest(
            workspace=str(workspace),
            provider="mock",
            fixture=_fixture(tmp_path, {"content": "好", "finish_reason": "stop"}),
            session_dir=str(tmp_path / "sessions"),
        ),
        {"MINIHNS_HOME": str(tmp_path / "home")},
    )

    assert isinstance(prepared, Prepared)
    assert prepared.settings.workspace == workspace
    assert not workspace.exists()  # 旧语义：不自动创建
    assert not (tmp_path / "home" / "workspaces").exists()


def test_discovery_root_stays_at_the_startup_directory(tmp_path: Path, monkeypatch) -> None:
    """发现根与围栏根分离：默认模式下技能/契约仍锚启动目录。"""
    project = tmp_path / "project"
    skill_dir = project / ".minihns" / "skills" / "demo"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: demo\ndescription: 只在项目里\n---\n体\n", encoding="utf-8"
    )
    (project / "AGENTS.md").write_text("项目契约：只写结论。\n", encoding="utf-8")
    monkeypatch.chdir(project)

    prepared = assemble(
        AssemblyRequest(
            provider="mock",
            fixture=_fixture(tmp_path, {"content": "好", "finish_reason": "stop"}),
            session_dir=str(tmp_path / "sessions"),
        ),
        {"MINIHNS_HOME": str(tmp_path / "home")},
    )

    assert isinstance(prepared, Prepared)
    # 围栏根是会话目录，发现根是启动目录。
    assert prepared.settings.workspace == (
        tmp_path / "home" / "workspaces" / prepared.log.session_id
    )
    assert prepared.settings.discovery_workspace == project
    assert [skill.name for skill in prepared.settings.skills] == ["demo"]


def test_resume_restores_the_workspace_from_the_log(tmp_path: Path) -> None:
    """resume 不给 workspace：读回 `session/start.workspace`。"""
    environ = {"MINIHNS_HOME": str(tmp_path / "home")}
    fixture = _fixture(tmp_path, {"content": "好", "finish_reason": "stop"})
    first = assemble(
        AssemblyRequest(
            provider="mock",
            fixture=fixture,
            session_dir=str(tmp_path / "sessions"),
        ),
        environ,
    )
    assert isinstance(first, Prepared)
    # 装配只建空日志；`session/start` 由开跑时写，这里补上它（resume 读的就是这条）。
    first.log.append("session/start", {"workspace": str(first.settings.workspace)})

    resumed = assemble(
        AssemblyRequest(
            provider="mock",
            fixture=fixture,
            session_dir=str(tmp_path / "sessions"),
            resume=first.log.session_id,
        ),
        environ,
    )

    assert isinstance(resumed, Prepared)
    assert resumed.resumed
    assert resumed.settings.workspace == first.settings.workspace


def test_resume_prefers_the_explicit_workspace(tmp_path: Path) -> None:
    """resume 同时给了 workspace：显式优先于日志。"""
    environ = {"MINIHNS_HOME": str(tmp_path / "home")}
    fixture = _fixture(tmp_path, {"content": "好", "finish_reason": "stop"})
    first = assemble(
        AssemblyRequest(
            provider="mock",
            fixture=fixture,
            session_dir=str(tmp_path / "sessions"),
        ),
        environ,
    )
    assert isinstance(first, Prepared)
    first.log.append("session/start", {"workspace": str(first.settings.workspace)})

    explicit = tmp_path / "other"
    explicit.mkdir()
    resumed = assemble(
        AssemblyRequest(
            workspace=str(explicit),
            provider="mock",
            fixture=fixture,
            session_dir=str(tmp_path / "sessions"),
            resume=first.log.session_id,
        ),
        environ,
    )

    assert isinstance(resumed, Prepared)
    assert resumed.settings.workspace == explicit


def test_resume_reports_a_missing_workspace(tmp_path: Path) -> None:
    """恢复的目录被人删了：`WORKSPACE_MISSING`（退出码 1），不静默重建。"""
    environ = {"MINIHNS_HOME": str(tmp_path / "home")}
    fixture = _fixture(tmp_path, {"content": "好", "finish_reason": "stop"})
    first = assemble(
        AssemblyRequest(
            provider="mock",
            fixture=fixture,
            session_dir=str(tmp_path / "sessions"),
        ),
        environ,
    )
    assert isinstance(first, Prepared)
    first.log.append("session/start", {"workspace": str(first.settings.workspace)})
    # 用改名模拟「目录被人删掉」：沙箱拦 rmdir，改名等价且可逆。
    first.settings.workspace.rename(first.settings.workspace.with_name("moved"))

    resumed = assemble(
        AssemblyRequest(
            provider="mock",
            fixture=fixture,
            session_dir=str(tmp_path / "sessions"),
            resume=first.log.session_id,
        ),
        environ,
    )

    assert isinstance(resumed, Failure)
    assert resumed.code == "WORKSPACE_MISSING"
    assert resumed.exit_code == 1
    assert not first.settings.workspace.exists()


def test_resume_rejects_a_log_without_a_workspace_field(tmp_path: Path) -> None:
    """旧日志没有 `session/start.workspace`：`INVALID_ARGUMENT`（退出码 2）。"""
    session_dir = tmp_path / "sessions"
    session_dir.mkdir()
    log = session_dir / "old.jsonl"
    log.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "type": "session/start",
                "session_id": "old",
                "seq": 0,
                "ts": "2026-01-01T00:00:00+00:00",
                "payload": {"entry": "chat"},
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    resumed = assemble(
        AssemblyRequest(
            provider="mock",
            fixture=_fixture(tmp_path, {"content": "好", "finish_reason": "stop"}),
            session_dir=str(session_dir),
            resume="old",
        ),
        {"MINIHNS_HOME": str(tmp_path / "home")},
    )

    assert isinstance(resumed, Failure)
    assert resumed.code == "INVALID_ARGUMENT"
    assert resumed.exit_code == 2


def test_default_mode_keeps_products_out_of_the_startup_directory(tmp_path: Path) -> None:
    """黑盒：不传 workspace，模型写的文件落会话目录，启动目录与仓库根无新文件。"""
    project = tmp_path / "project"
    project.mkdir()
    home = tmp_path / "home"
    result = _cli(
        "run",
        "-p",
        "写一个笔记",
        "--yes",
        "--provider",
        "mock",
        "--fixture",
        _fixture(
            tmp_path,
            _write_file_turn(path="snake/core.py", content="print(1)\n"),
            {"content": "好", "finish_reason": "stop"},
        ),
        "--session-dir",
        str(tmp_path / "sessions"),
        cwd=project,
        workspace=None,
        env={"MINIHNS_HOME": str(home)},
    )

    assert result.returncode == 0, result.stderr
    logs = sorted((tmp_path / "sessions").glob("*.jsonl"))
    assert len(logs) == 1
    session_id = logs[0].stem
    assert (home / "workspaces" / session_id / "snake" / "core.py").read_text(
        encoding="utf-8"
    ) == "print(1)\n"
    assert list(project.iterdir()) == []
    assert f"工作区 {home / 'workspaces' / session_id}" in result.stderr
    # stdout 契约不变：只有 session id，工作区路径不许混进去（design D4 / M6）。
    assert str(home / "workspaces" / session_id) not in result.stdout


def test_default_mode_still_refuses_escapes(tmp_path: Path) -> None:
    """黑盒：围栏根是会话目录，默认模式下 `../` 仍然被拒。"""
    project = tmp_path / "project"
    project.mkdir()
    result = _cli(
        "run",
        "-p",
        "写到外面",
        "--yes",
        "--provider",
        "mock",
        "--fixture",
        _fixture(
            tmp_path,
            _write_file_turn(path="../escape.txt", content="x"),
            {"content": "好", "finish_reason": "stop"},
        ),
        "--session-dir",
        str(tmp_path / "sessions"),
        cwd=project,
        workspace=None,
        env={"MINIHNS_HOME": str(tmp_path / "home")},
    )

    assert result.returncode != 0
    assert "OUTSIDE_WORKSPACE" in result.stderr
    assert not list((tmp_path / "home" / "workspaces").rglob("escape.txt"))
    assert not (project / "escape.txt").exists()


def test_config_discovery_still_anchors_the_startup_directory(tmp_path: Path, monkeypatch) -> None:
    """默认模式下 `mini.config.toml` 仍从启动目录发现（发现根不是会话目录）。"""
    project = tmp_path / "project"
    project.mkdir()
    (project / "mini.config.toml").write_text('tools = ["read"]\n', encoding="utf-8")
    monkeypatch.chdir(project)

    prepared = assemble(
        AssemblyRequest(
            provider="mock",
            fixture=_fixture(tmp_path, {"content": "好", "finish_reason": "stop"}),
            session_dir=str(tmp_path / "sessions"),
        ),
        {"MINIHNS_HOME": str(tmp_path / "home")},
    )

    assert isinstance(prepared, Prepared)
    assert [spec.name for spec in prepared.registry.specs()] == ["read"]
    # 配置文件没有把工作区带跑：围栏根仍是会话目录。
    assert prepared.settings.workspace == (
        tmp_path / "home" / "workspaces" / prepared.log.session_id
    )


def _session_id(result) -> str:
    """从 chat 的 stderr 横幅取会话 id。"""
    for line in result.stderr.splitlines():
        if line.startswith("会话 "):
            return line.split(" ", 1)[1].strip()
    raise AssertionError(result.stderr)


def test_chat_resume_restores_the_default_workspace(tmp_path: Path) -> None:
    """黑盒：断点后 resume 不给 workspace，工作区恢复为日志里的会话目录。"""
    project = tmp_path / "project"
    project.mkdir()
    home = tmp_path / "home"
    env = {"MINIHNS_HOME": str(home)}
    fixture = _fixture(
        tmp_path,
        _write_file_turn(path="note.md", content="记一笔\n"),
        {"content": "好", "finish_reason": "stop"},
    )

    first = _cli(
        "chat",
        "--provider",
        "mock",
        "--fixture",
        fixture,
        "--session-dir",
        str(tmp_path / "sessions"),
        "--yes",
        cwd=project,
        workspace=None,
        env=env,
        stdin_text="写个笔记\n",
    )
    assert first.returncode == 0, first.stderr
    session_id = _session_id(first)
    workspace = home / "workspaces" / session_id
    assert (workspace / "note.md").read_text(encoding="utf-8") == "记一笔\n"

    resumed = _cli(
        "chat",
        "--resume",
        session_id,
        "--provider",
        "mock",
        "--fixture",
        fixture,
        "--session-dir",
        str(tmp_path / "sessions"),
        "--yes",
        cwd=project,
        workspace=None,
        env=env,
        stdin_text="再写一次\n",
    )

    assert resumed.returncode == 0, resumed.stderr
    assert f"工作区 {workspace}" in resumed.stderr
    assert (workspace / "note.md").exists()


def test_chat_resume_reports_workspace_missing(tmp_path: Path) -> None:
    """黑盒：恢复的目录不在时报 `WORKSPACE_MISSING`（退出码 1），不静默重建。"""
    project = tmp_path / "project"
    project.mkdir()
    home = tmp_path / "home"
    env = {"MINIHNS_HOME": str(home)}
    fixture = _fixture(tmp_path, {"content": "好", "finish_reason": "stop"})

    first = _cli(
        "chat",
        "--provider",
        "mock",
        "--fixture",
        fixture,
        "--session-dir",
        str(tmp_path / "sessions"),
        "--yes",
        cwd=project,
        workspace=None,
        env=env,
        stdin_text="你好\n",
    )
    assert first.returncode == 0, first.stderr
    session_id = _session_id(first)
    workspace = home / "workspaces" / session_id
    workspace.rename(workspace.with_name("moved"))

    resumed = _cli(
        "chat",
        "--resume",
        session_id,
        "--provider",
        "mock",
        "--fixture",
        fixture,
        "--session-dir",
        str(tmp_path / "sessions"),
        "--yes",
        cwd=project,
        workspace=None,
        env=env,
        stdin_text="",
    )

    assert resumed.returncode == 1
    assert "WORKSPACE_MISSING" in resumed.stderr
    assert not workspace.exists()


def test_resume_restores_an_explicit_workspace_from_the_log(tmp_path: Path) -> None:
    """首场用显式 workspace，resume 不给：恢复的是日志里那个目录，不是默认路径。

    默认目录与 `<sid>` 推导出的路径恰好相同，会掩盖「真的读了日志」这一步——所以必须
    用与默认路径不同的工作区钉住它（变异 M3「resume 静默落到默认目录」的杀手）。
    """
    environ = {"MINIHNS_HOME": str(tmp_path / "home")}
    fixture = _fixture(tmp_path, {"content": "好", "finish_reason": "stop"})
    explicit = tmp_path / "explicit-workspace"
    explicit.mkdir()
    first = assemble(
        AssemblyRequest(
            workspace=str(explicit),
            provider="mock",
            fixture=fixture,
            session_dir=str(tmp_path / "sessions"),
        ),
        environ,
    )
    assert isinstance(first, Prepared)
    first.log.append("session/start", {"workspace": str(explicit)})

    resumed = assemble(
        AssemblyRequest(
            provider="mock",
            fixture=fixture,
            session_dir=str(tmp_path / "sessions"),
            resume=first.log.session_id,
        ),
        environ,
    )

    assert isinstance(resumed, Prepared)
    assert resumed.settings.workspace == explicit
    assert not (tmp_path / "home" / "workspaces" / first.log.session_id).exists()


def _log_records(session_dir: Path) -> list[dict[str, object]]:
    files = sorted(session_dir.glob("*.jsonl"))
    assert len(files) == 1
    return [json.loads(line) for line in files[0].read_text(encoding="utf-8").splitlines()]


def test_creation_failure_is_an_argument_error_without_a_log(tmp_path: Path) -> None:
    """`MINIHNS_HOME` 下没法建目录：退出码 2、`INVALID_ARGUMENT`、不建日志。"""
    home = tmp_path / "home"
    home.mkdir()
    (home / "workspaces").write_text("这是文件不是目录", encoding="utf-8")
    project = tmp_path / "project"
    project.mkdir()

    result = _cli(
        "run",
        "-p",
        "任务",
        "--yes",
        "--provider",
        "mock",
        "--fixture",
        _fixture(tmp_path, {"content": "好", "finish_reason": "stop"}),
        "--session-dir",
        str(tmp_path / "sessions"),
        cwd=project,
        workspace=None,
        env={"MINIHNS_HOME": str(home)},
    )

    assert result.returncode == 2
    assert "INVALID_ARGUMENT" in result.stderr
    assert not (tmp_path / "sessions").exists()


def test_session_start_workspace_is_named_after_the_session(tmp_path: Path) -> None:
    """`session/start.workspace` 的目录名 == 会话 id（id 先于工作区生成）。"""
    project = tmp_path / "project"
    project.mkdir()
    result = _cli(
        "run",
        "-p",
        "任务",
        "--yes",
        "--provider",
        "mock",
        "--fixture",
        _fixture(tmp_path, {"content": "好", "finish_reason": "stop"}),
        "--session-dir",
        str(tmp_path / "sessions"),
        cwd=project,
        workspace=None,
        env={"MINIHNS_HOME": str(tmp_path / "home")},
    )

    assert result.returncode == 0, result.stderr
    records = _log_records(tmp_path / "sessions")
    start = next(record for record in records if record["type"] == "session/start")
    payload = start["payload"]
    assert Path(str(payload["workspace"])).name == start["session_id"]


def test_config_and_contracts_still_anchor_the_startup_directory(tmp_path: Path) -> None:
    """默认模式下 `mini.config.toml` 的 max_steps 与 `AGENTS.md` 契约都从启动目录生效。"""
    project = tmp_path / "project"
    project.mkdir()
    (project / "mini.config.toml").write_text("max_steps = 2\n", encoding="utf-8")
    (project / "AGENTS.md").write_text("项目契约：只写结论。\n", encoding="utf-8")

    result = _cli(
        "run",
        "-p",
        "任务",
        "--yes",
        "--provider",
        "mock",
        "--fixture",
        _fixture(tmp_path, {"content": "好", "finish_reason": "stop"}),
        "--session-dir",
        str(tmp_path / "sessions"),
        cwd=project,
        workspace=None,
        env={"MINIHNS_HOME": str(tmp_path / "home")},
    )

    assert result.returncode == 0, result.stderr
    records = _log_records(tmp_path / "sessions")
    start = next(record for record in records if record["type"] == "session/start")
    assert start["payload"]["max_steps"] == 2
    assembled = next(record for record in records if record["type"] == "context/assembled")
    joined = "\n".join(
        str(message.get("content") or "") for message in assembled["payload"]["messages"]
    )
    assert "项目契约：只写结论" in joined


def test_default_mode_still_applies_the_bash_sandbox_level(tmp_path: Path) -> None:
    """默认模式下 bash 仍按沙箱档位判：read-only 直接拒绝，命令一次都没跑。

    （bash 的围栏不静态分析 `../`——那是既有语义，本 change 不动围栏实现；这里钉的是
    「围栏根换了位置，档位判定不受影响」。）
    """
    project = tmp_path / "project"
    project.mkdir()
    turn = {
        "content": "",
        "finish_reason": "tool_calls",
        "tool_calls": [
            {
                "id": "c1",
                "name": "bash",
                "arguments": {"command": "touch ../escaped-by-bash.txt"},
            }
        ],
    }
    result = _cli(
        "run",
        "-p",
        "跑命令",
        "--yes",
        "--sandbox",
        "read-only",
        "--provider",
        "mock",
        "--fixture",
        _fixture(tmp_path, turn, {"content": "好", "finish_reason": "stop"}),
        "--session-dir",
        str(tmp_path / "sessions"),
        cwd=project,
        workspace=None,
        env={"MINIHNS_HOME": str(tmp_path / "home")},
    )

    assert result.returncode != 0
    assert "SANDBOX_DENIES_WRITE" in result.stderr
    assert not list((tmp_path / "home" / "workspaces").rglob("escaped-by-bash.txt"))
    assert not (project / "escaped-by-bash.txt").exists()
