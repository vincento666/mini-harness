"""seam ②④⑥：技能发现、清单注入、`skill` 工具（M14）。"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Any

from cli_blackbox import _cli
from mini_harness.commands import command_catalog, direct_skill, execute_command
from mini_harness.config import build_registry
from mini_harness.events import EventRecord, read_events
from mini_harness.events.fold import fold
from mini_harness.loop import ENTRY_RUN, start_session
from mini_harness.provider import FixtureProvider
from mini_harness.skills import (
    BODY_LIMIT,
    DESCRIPTION_MAX,
    Skill,
    catalog_text,
    discover_skills,
    merge_skill_layer,
    read_skill_body,
    skill_content,
)
from paths import HELLO_SCENARIO
from tool_harness import build_session_env, dispatch_call


def _skill(root: Path, name: str, *, description: str = "描述", body: str = "正文") -> Path:
    """在 root 下放一个技能；返回 SKILL.md 的路径。"""
    directory = root / name
    directory.mkdir(parents=True)
    path = directory / "SKILL.md"
    path.write_text(
        f"---\nname: {name}\ndescription: {description}\n---\n\n{body}\n", encoding="utf-8"
    )
    return path


def _names(skills: tuple[Skill, ...]) -> list[str]:
    return [skill.name for skill in skills]


def test_four_roots_are_discovered_in_rank_order(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    home = tmp_path / "home"
    _skill(workspace / ".minihns" / "skills", "zeta")
    _skill(workspace / ".agents" / "skills", "mid")
    _skill(home / "skills", "alpha")

    skills = discover_skills(workspace, {"MINIHNS_HOME": str(home)}).skills

    assert _names(skills) == ["alpha", "mid", "zeta"]
    assert [skill.rank for skill in skills] == [400, 200, 100]


def test_same_name_prefers_the_lower_rank(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    home = tmp_path / "home"
    _skill(workspace / ".minihns" / "skills", "tdd", body="项目内")
    _skill(home / "skills", "tdd", body="用户级")

    skills = discover_skills(workspace, {"MINIHNS_HOME": str(home)}).skills

    assert _names(skills) == ["tdd"]
    assert skills[0].rank == 100
    assert read_skill_body(skills[0]).strip() == "项目内"


def test_invalid_names_and_nested_directories_are_skipped(tmp_path: Path) -> None:
    root = tmp_path / "workspace" / ".minihns" / "skills"
    (root / "Bad_Name").mkdir(parents=True)
    (root / "Bad_Name" / "SKILL.md").write_text("---\nname: Bad_Name\n---\n", encoding="utf-8")
    _skill(root, "good")
    nested = root / "outer" / "inner"
    nested.mkdir(parents=True)
    (nested / "SKILL.md").write_text("---\nname: inner\n---\n", encoding="utf-8")

    skills = discover_skills(tmp_path / "workspace", {"MINIHNS_HOME": str(tmp_path)}).skills

    assert _names(skills) == ["good"]


def test_flat_markdown_is_a_skill(tmp_path: Path) -> None:
    root = tmp_path / "workspace" / ".minihns" / "skills"
    root.mkdir(parents=True)
    (root / "flat.md").write_text(
        "---\nname: flat\ndescription: 扁平\n---\n正文\n", encoding="utf-8"
    )

    skills = discover_skills(tmp_path / "workspace", {"MINIHNS_HOME": str(tmp_path)}).skills

    assert _names(skills) == ["flat"]
    assert read_skill_body(skills[0]).strip() == "正文"


def test_description_is_capped(tmp_path: Path) -> None:
    root = tmp_path / "workspace" / ".minihns" / "skills"
    _skill(root, "long", description="x" * (DESCRIPTION_MAX + 100))

    skills = discover_skills(tmp_path / "workspace", {"MINIHNS_HOME": str(tmp_path)}).skills

    assert len(skills[0].description) == DESCRIPTION_MAX


def test_catalog_budget_truncates_with_a_marker() -> None:
    entries = [(f"skill-{index}", "描述" * 50) for index in range(20)]

    text = catalog_text(entries, budget=200)

    assert "（还有" in text
    assert text.endswith("个技能未列出）")


def test_body_is_capped(tmp_path: Path) -> None:
    skill = Skill(name="big", description="", rank=100, path=tmp_path / "big.md")
    skill.path.write_text("x" * (BODY_LIMIT + 10), encoding="utf-8")

    body = read_skill_body(skill)

    assert "已截断" in body
    assert len(body) < BODY_LIMIT + 200


async def test_the_skill_tool_returns_xml(tmp_path: Path) -> None:
    root = tmp_path / "ws" / ".minihns" / "skills"
    path = _skill(root, "tdd", description="先写判据", body="第一步：写红判据")
    registry = build_registry(None, skills=discover_skills(root.parent.parent, {}).skills)

    outcome = await dispatch_call(tmp_path, "skill", {"name": "tdd"}, registry=registry)

    assert outcome.result.outcome == "OK"
    assert "<skill_content" in outcome.result.content
    assert "<skill_instructions>" in outcome.result.content
    assert "第一步：写红判据" in outcome.result.content
    assert str(path) in outcome.result.content


async def test_an_unknown_skill_is_an_argument_error(tmp_path: Path) -> None:
    registry = build_registry(None, skills=())

    outcome = await dispatch_call(tmp_path, "skill", {"name": "nope"}, registry=registry)

    assert outcome.result.outcome == "TOOL_ARGS_INVALID"
    assert "nope" in outcome.result.content


def _rec(seq: int, event_type: str, payload: dict[str, Any]) -> EventRecord:
    return EventRecord(
        schema_version=1,
        type=event_type,
        session_id="s-skills",
        seq=seq,
        ts=f"2026-11-11T00:00:{seq:02d}+00:00",
        payload=payload,
    )


def test_the_header_carries_the_catalog_but_not_the_body() -> None:
    events = [
        _rec(
            0,
            "session/start",
            {
                "prompt": "任务",
                "tools": ["skill"],
                "skills": [
                    {"name": "tdd", "description": "先写判据", "rank": 100, "path": "/ws/tdd"},
                ],
            },
        ),
        _rec(1, "turn/start", {"turn_id": "t1"}),
        _rec(2, "model/response", {"turn_id": "t1", "content": "好", "tool_calls": []}),
        _rec(3, "turn/end", {"turn_id": "t1", "stop_reason": "MODEL_COMPLETED"}),
    ]

    header = fold(events).messages[0].content

    assert "可用技能" in header
    assert "tdd：先写判据" in header
    assert "第一步" not in header


def test_session_start_records_the_catalog(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    _skill(workspace / ".minihns" / "skills", "tdd", description="先写判据")

    result = _cli(
        "run",
        "-p",
        "任务",
        "--provider",
        "mock",
        "--fixture",
        str(HELLO_SCENARIO),
        cwd=workspace,
    )

    assert result.returncode == 0, result.stderr
    logs = sorted(workspace.glob("sessions/*.jsonl"))
    records = [json.loads(line) for line in logs[0].read_text(encoding="utf-8").splitlines()]
    start = next(record["payload"] for record in records if record["type"] == "session/start")
    assert start["skills"][0]["name"] == "tdd"
    assert start["skills"][0]["rank"] == 100
    assert "正文" not in json.dumps(start["skills"])


def _chat_log(workspace: Path) -> list[dict[str, Any]]:
    log = sorted(workspace.glob("sessions/*.jsonl"))[0]
    return [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]


def test_chat_lists_skills_without_a_segment(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    _skill(workspace / ".minihns" / "skills", "tdd", description="先写判据")

    result = _cli(
        "chat",
        "--provider",
        "mock",
        "--fixture",
        str(HELLO_SCENARIO),
        cwd=workspace,
        stdin_text="/skills\n",
    )

    assert result.returncode == 0, result.stderr
    assert "tdd" in result.stdout
    records = _chat_log(workspace)
    types = [record["type"] for record in records]
    assert types.count("command/run") == 1
    assert types.count("command/done") == 1
    assert "segment/start" not in types


def test_chat_loads_a_skill_without_a_segment(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    _skill(workspace / ".minihns" / "skills", "tdd", body="第一步：写红判据")

    result = _cli(
        "chat",
        "--provider",
        "mock",
        "--fixture",
        str(HELLO_SCENARIO),
        cwd=workspace,
        stdin_text="/skill tdd\n",
    )

    assert result.returncode == 0, result.stderr
    assert "第一步：写红判据" in result.stdout
    records = _chat_log(workspace)
    done = next(record["payload"] for record in records if record["type"] == "command/done")
    assert done["ok"] is True
    assert "第一步：写红判据" in done["text"]
    assert "user/message" not in [record["type"] for record in records]


def test_chat_rejects_an_unknown_command_without_logging(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()

    result = _cli(
        "chat",
        "--provider",
        "mock",
        "--fixture",
        str(HELLO_SCENARIO),
        cwd=workspace,
        stdin_text="/nope\n",
    )

    assert result.returncode == 0, result.stderr
    assert "未知命令" in result.stderr
    records = _chat_log(workspace)
    assert [record["type"] for record in records if record["type"].startswith("command/")] == []


def test_direct_skill_only_returns_user_invocable(tmp_path: Path) -> None:
    root = tmp_path / "ws" / ".minihns" / "skills"
    _skill(root, "tdd")
    _raw_skill(root, "model-only", "name: model-only\ndescription: d\nuser-invocable: false")
    skills = discover_skills(tmp_path / "ws", {}).skills

    assert direct_skill("tdd", skills) is not None
    assert direct_skill("model-only", skills) is None
    assert execute_command("tdd", "", skills) is None


def test_a_builtin_name_wins_over_a_skill(tmp_path: Path) -> None:
    root = tmp_path / "ws" / ".minihns" / "skills"
    _skill(root, "skills", body="这条是技能正文")
    skills = discover_skills(tmp_path / "ws", {}).skills

    listed = execute_command("skills", "", skills)

    assert listed is not None and listed.ok
    assert "技能正文" not in listed.text
    assert execute_command("help", "", skills) is None


def test_chat_runs_a_skill_directly(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    _skill(workspace / ".minihns" / "skills", "tdd", body="第一步：写红判据")

    result = _cli(
        "chat",
        "--provider",
        "mock",
        "--fixture",
        str(HELLO_SCENARIO),
        cwd=workspace,
        stdin_text="/tdd\n",
    )

    assert result.returncode == 0, result.stderr
    records = _chat_log(workspace)
    types = [record["type"] for record in records]
    assert types.count("command/run") == 1
    assert "segment/start" in types
    user = next(record["payload"] for record in records if record["type"] == "user/message")
    assert "第一步：写红判据" in user["content"]
    assert "请按技能执行" in user["content"]


def test_chat_help_lists_skill_commands(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    _skill(workspace / ".minihns" / "skills", "tdd", description="先写判据")

    result = _cli(
        "chat",
        "--provider",
        "mock",
        "--fixture",
        str(HELLO_SCENARIO),
        cwd=workspace,
        stdin_text="/help\n",
    )

    assert result.returncode == 0, result.stderr
    assert "/tdd" in result.stdout


def test_progressive_disclosure_end_to_end(tmp_path: Path) -> None:
    """第一轮上下文没有正文；`skill` 调用之后正文才作为工具结果进来。"""
    workspace = tmp_path / "ws"
    _skill(workspace / ".minihns" / "skills", "tdd", body="只在加载后才出现的正文")
    fixture = tmp_path / "turns.json"
    fixture.write_text(
        json.dumps(
            [
                {
                    "content": "",
                    "finish_reason": "tool_calls",
                    "tool_calls": [{"id": "c1", "name": "skill", "arguments": {"name": "tdd"}}],
                },
                {"content": "按技能做完了", "finish_reason": "stop"},
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    result = _cli(
        "run",
        "-p",
        "任务",
        "--provider",
        "mock",
        "--fixture",
        str(fixture),
        cwd=workspace,
    )

    assert result.returncode == 0, result.stderr
    records = _chat_log(workspace)
    start = next(record["payload"] for record in records if record["type"] == "session/start")
    assert "只在加载后才出现的正文" not in json.dumps(start, ensure_ascii=False)
    assembled = [
        json.dumps(record["payload"], ensure_ascii=False)
        for record in records
        if record["type"] == "context/assembled"
    ]
    assert assembled
    assert "只在加载后才出现的正文" not in assembled[0]
    assert any("只在加载后才出现的正文" in later for later in assembled[1:])
    replies = [
        str(record["payload"].get("content"))
        for record in records
        if record["type"] == "model/response" and record["payload"].get("purpose") is None
    ]
    assert "按技能做完了" in replies[-1]


def test_skill_content_renders_the_instruction(tmp_path: Path) -> None:
    skill = Skill(name="tdd", description="", rank=100, path=tmp_path / "tdd.md")
    skill.path.write_text("---\nname: tdd\n---\n\n正文\n", encoding="utf-8")

    rendered = skill_content(skill, "帮我改个函数")

    assert "<skill_content" in rendered
    assert "正文" in rendered
    assert rendered.endswith("帮我改个函数")


def test_chat_skill_command_with_an_instruction_opens_a_segment(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    _skill(workspace / ".minihns" / "skills", "tdd", body="第一步：写红判据")

    result = _cli(
        "chat",
        "--provider",
        "mock",
        "--fixture",
        str(HELLO_SCENARIO),
        cwd=workspace,
        stdin_text="/tdd 帮我改个函数\n",
    )

    assert result.returncode == 0, result.stderr
    records = _chat_log(workspace)
    types = [record["type"] for record in records]
    assert types.count("command/run") == 1
    assert types.count("command/done") == 1
    assert "segment/start" in types
    user = next(record["payload"] for record in records if record["type"] == "user/message")
    assert "第一步：写红判据" in user["content"]
    assert "帮我改个函数" in user["content"]


def _raw_skill(root: Path, name: str, frontmatter: str) -> Path:
    directory = root / name
    directory.mkdir(parents=True)
    path = directory / "SKILL.md"
    path.write_text(f"---\n{frontmatter}\n---\n正文\n", encoding="utf-8")
    return path


def test_default_policy_is_both_true(tmp_path: Path) -> None:
    root = tmp_path / "ws" / ".minihns" / "skills"
    _skill(root, "both")

    skill = discover_skills(tmp_path / "ws", {}).skills[0]

    assert skill.model_invocable is True
    assert skill.user_invocable is True


def test_policy_values_accept_the_dsh_boolean_forms(tmp_path: Path) -> None:
    root = tmp_path / "ws" / ".minihns" / "skills"
    _raw_skill(root, "a", "name: a\ndescription: d\ndisable-model-invocation: no")
    _raw_skill(root, "b", "name: b\ndescription: d\nuser-invocable: OFF")
    _raw_skill(root, "c", "name: c\ndescription: d\ndisable-model-invocation: 1")

    skills = {skill.name: skill for skill in discover_skills(tmp_path / "ws", {}).skills}

    assert skills["a"].model_invocable is True
    assert skills["a"].user_invocable is True
    assert skills["b"].user_invocable is False
    assert skills["c"].model_invocable is False


def test_an_invalid_policy_value_drops_the_skill(tmp_path: Path) -> None:
    root = tmp_path / "ws" / ".minihns" / "skills"
    _raw_skill(root, "bad", "name: bad\ndescription: d\ndisable-model-invocation: maybe")

    assert discover_skills(tmp_path / "ws", {}).skills == ()


def test_a_missing_description_drops_the_skill(tmp_path: Path) -> None:
    root = tmp_path / "ws" / ".minihns" / "skills"
    _raw_skill(root, "nodesc", "name: nodesc")
    (root / "plain.md").write_text("没有 frontmatter\n", encoding="utf-8")

    assert discover_skills(tmp_path / "ws", {}).skills == ()


def test_payload_lists_only_model_invocable(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    root = workspace / ".minihns" / "skills"
    _raw_skill(root, "both", "name: both\ndescription: d")
    _raw_skill(root, "user-only", "name: user-only\ndescription: d\ndisable-model-invocation: on")
    _raw_skill(root, "model-only", "name: model-only\ndescription: d\nuser-invocable: false")

    _cli("run", "-p", "任务", "--provider", "mock", "--fixture", str(HELLO_SCENARIO), cwd=workspace)

    payload = next(
        record["payload"] for record in _chat_log(workspace) if record["type"] == "session/start"
    )
    assert [item["name"] for item in payload["skills"]] == ["both", "model-only"]


async def test_the_skill_tool_rejects_a_model_disabled_skill(tmp_path: Path) -> None:
    root = tmp_path / "ws" / ".minihns" / "skills"
    _raw_skill(root, "user-only", "name: user-only\ndescription: d\ndisable-model-invocation: on")
    registry = build_registry(None, skills=discover_skills(tmp_path / "ws", {}).skills)

    outcome = await dispatch_call(tmp_path, "skill", {"name": "user-only"}, registry=registry)

    assert outcome.result.outcome == "TOOL_ARGS_INVALID"
    assert "不可由模型调用" in outcome.result.content


def test_commands_only_see_user_invocable(tmp_path: Path) -> None:
    root = tmp_path / "ws" / ".minihns" / "skills"
    _raw_skill(root, "both", "name: both\ndescription: d")
    _raw_skill(root, "user-only", "name: user-only\ndescription: d\ndisable-model-invocation: on")
    _raw_skill(root, "model-only", "name: model-only\ndescription: d\nuser-invocable: false")
    skills = discover_skills(tmp_path / "ws", {}).skills

    assert [command.name for command in command_catalog(skills)] == [
        "skills",
        "skill",
        "both",
        "user-only",
    ]
    assert execute_command("skill", "model-only", skills).ok is False
    listed = execute_command("skills", "", skills)
    assert listed is not None and "model-only" not in listed.text


def test_a_root_iterdir_failure_marks_the_discovery_incomplete(
    tmp_path: Path, monkeypatch: object
) -> None:
    workspace = tmp_path / "ws"
    home = tmp_path / "home"
    _skill(workspace / ".minihns" / "skills", "project")
    broken = workspace / ".agents" / "skills"
    broken.mkdir(parents=True)
    _skill(home / "skills", "user")
    original = Path.iterdir

    def fake_iterdir(self: Path):  # type: ignore[no-untyped-def]
        if self == broken:
            raise OSError("permission denied")
        return original(self)

    monkeypatch.setattr(Path, "iterdir", fake_iterdir)  # type: ignore[attr-defined]

    discovery = discover_skills(workspace, {"MINIHNS_HOME": str(home)})

    assert discovery.complete is False
    assert [skill.name for skill in discovery.skills] == ["project", "user"]


def test_incomplete_discovery_reaches_the_payload(tmp_path: Path) -> None:
    _, env = build_session_env(tmp_path, "s-incomplete", FixtureProvider(entries=[]))
    env = replace(env, settings=replace(env.settings, skills_complete=False))

    assert start_session(prompt="任务", entry=ENTRY_RUN, env=env) is None

    payload = read_events(env.log.path)[0].payload
    assert payload["skills_incomplete"] is True


def test_the_header_warns_about_incomplete_discovery() -> None:
    events = [
        _rec(
            0,
            "session/start",
            {"prompt": "任务", "tools": [], "skills_incomplete": True},
        ),
        _rec(1, "turn/start", {"turn_id": "t1"}),
        _rec(2, "model/response", {"turn_id": "t1", "content": "好", "tool_calls": []}),
        _rec(3, "turn/end", {"turn_id": "t1", "stop_reason": "MODEL_COMPLETED"}),
    ]

    header = fold(events).messages[0].content

    assert "没能检查到" in header


def test_merge_skill_layer_overrides_and_adds(tmp_path: Path) -> None:
    base_root = tmp_path / "ws" / ".minihns" / "skills"
    layer_root = tmp_path / "ws" / "preset-skills"
    _skill(base_root, "tdd", description="全局")
    _skill(layer_root, "tdd", description="preset")
    _skill(layer_root, "extra", description="新增")
    base = discover_skills(tmp_path / "ws", {}).skills

    merged, complete = merge_skill_layer(base, [layer_root])

    assert complete is True
    assert {skill.name: skill.description for skill in merged} == {"extra": "新增", "tdd": "preset"}


def test_a_missing_layer_dir_is_an_empty_layer(tmp_path: Path) -> None:
    base = (Skill(name="tdd", description="d", rank=100, path=tmp_path / "tdd.md"),)

    merged, complete = merge_skill_layer(base, [tmp_path / "nope"])

    assert complete is True
    assert [skill.name for skill in merged] == ["tdd"]


def test_an_unreadable_layer_dir_is_incomplete(tmp_path: Path, monkeypatch: object) -> None:
    layer = tmp_path / "layer"
    layer.mkdir()
    original = Path.iterdir

    def fake_iterdir(self: Path):  # type: ignore[no-untyped-def]
        if self == layer:
            raise OSError("permission denied")
        return original(self)

    monkeypatch.setattr(Path, "iterdir", fake_iterdir)  # type: ignore[attr-defined]

    _, complete = merge_skill_layer((), [layer])

    assert complete is False


def test_a_preset_skill_layer_reaches_the_child_only(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    _skill(workspace / ".minihns" / "skills", "tdd", description="全局", body="全局正文")
    layer = workspace / ".minihns" / "preset-skills"
    _skill(layer, "tdd", description="preset", body="preset 正文")
    _skill(layer, "extra", description="子会话独有")
    (workspace / "mini.config.toml").write_text(
        '[subagent]\npreset = "reader"\n\n'
        '[subagent.presets.reader]\ntools = ["read", "glob"]\n'
        'skill_dirs = [".minihns/preset-skills"]\n',
        encoding="utf-8",
    )
    fixture = workspace / "turns.json"
    fixture.write_text(
        json.dumps(
            [
                {
                    "content": "",
                    "finish_reason": "tool_calls",
                    "tool_calls": [{"id": "c1", "name": "subagent", "arguments": {"task": "看"}}],
                },
                {"content": "好", "finish_reason": "stop"},
                {"content": "完", "finish_reason": "stop"},
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    _cli(
        "run",
        "-p",
        "任务",
        "--provider",
        "mock",
        "--fixture",
        str(fixture),
        cwd=workspace,
    )

    starts = [
        record["payload"]
        for path in workspace.glob("sessions/*.jsonl")
        for record in map(json.loads, path.read_text(encoding="utf-8").splitlines())
        if record["type"] == "session/start"
    ]
    parent = next(payload for payload in starts if payload.get("entry") == "run")
    child = next(payload for payload in starts if payload.get("entry") == "subagent")
    assert {item["name"]: item["description"] for item in parent["skills"]} == {"tdd": "全局"}
    assert {item["name"]: item["description"] for item in child["skills"]} == {
        "extra": "子会话独有",
        "tdd": "preset",
    }
