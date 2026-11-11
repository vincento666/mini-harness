"""seam ②④⑥：技能发现、清单注入、`skill` 工具（M14）。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from cli_blackbox import _cli
from mini_harness.config import build_registry
from mini_harness.events import EventRecord
from mini_harness.events.fold import fold
from mini_harness.skills import (
    BODY_LIMIT,
    DESCRIPTION_MAX,
    Skill,
    catalog_text,
    discover_skills,
    read_skill_body,
)
from paths import HELLO_SCENARIO
from tool_harness import dispatch_call


def _skill(root: Path, name: str, *, description: str = "", body: str = "正文") -> Path:
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

    skills = discover_skills(workspace, {"MINIHNS_HOME": str(home)})

    assert _names(skills) == ["alpha", "mid", "zeta"]
    assert [skill.rank for skill in skills] == [400, 200, 100]


def test_same_name_prefers_the_lower_rank(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    home = tmp_path / "home"
    _skill(workspace / ".minihns" / "skills", "tdd", body="项目内")
    _skill(home / "skills", "tdd", body="用户级")

    skills = discover_skills(workspace, {"MINIHNS_HOME": str(home)})

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

    skills = discover_skills(tmp_path / "workspace", {"MINIHNS_HOME": str(tmp_path)})

    assert _names(skills) == ["good"]


def test_flat_markdown_is_a_skill(tmp_path: Path) -> None:
    root = tmp_path / "workspace" / ".minihns" / "skills"
    root.mkdir(parents=True)
    (root / "flat.md").write_text("正文\n", encoding="utf-8")

    skills = discover_skills(tmp_path / "workspace", {"MINIHNS_HOME": str(tmp_path)})

    assert _names(skills) == ["flat"]
    assert read_skill_body(skills[0]).strip() == "正文"


def test_description_is_capped(tmp_path: Path) -> None:
    root = tmp_path / "workspace" / ".minihns" / "skills"
    _skill(root, "long", description="x" * (DESCRIPTION_MAX + 100))

    skills = discover_skills(tmp_path / "workspace", {"MINIHNS_HOME": str(tmp_path)})

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
    registry = build_registry(None, skills=discover_skills(root.parent.parent, {}))

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
