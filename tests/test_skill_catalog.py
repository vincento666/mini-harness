"""seam ①④：模型目录消息（skill-catalog-live）。"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from mini_harness.config import build_registry
from mini_harness.events import EventLog, read_events
from mini_harness.loop.turn_loop import _maybe_emit_catalog, run_session_env
from mini_harness.provider import FixtureProvider
from mini_harness.skill_providers import FilesystemProvider, SkillRegistry
from mini_harness.skills import (
    Skill,
    SkillDiscovery,
    catalog_digest,
    discover_skills,
    render_catalog_message,
)
from tool_harness import build_session_env, tool_call_entry


def _write_skill(root: Path, name: str, description: str = "描述", body: str = "正文") -> Path:
    directory = root / name
    directory.mkdir(parents=True)
    path = directory / "SKILL.md"
    path.write_text(
        f"---\nname: {name}\ndescription: {description}\n---\n{body}\n", encoding="utf-8"
    )
    return path


def _catalog_messages(log: EventLog) -> list[dict[str, object]]:
    return [
        record.payload
        for record in read_events(log.path)
        if record.type == "user/message" and record.payload.get("source") == "skill-catalog"
    ]


def _env(tmp_path: Path, load=None) -> object:  # type: ignore[no-untyped-def]
    """一个带全局注册表的会话环境；`load` 覆盖发现，用来演「中途多/少/不完整」。"""
    workspace = tmp_path / "ws"
    workspace.mkdir(parents=True, exist_ok=True)
    _, env = build_session_env(
        tmp_path, "s-catalog", FixtureProvider(entries=[]), workspace=workspace
    )
    provider = FilesystemProvider(
        "filesystem", (lambda: discover_skills(workspace, {})) if load is None else load
    )
    return replace(env, skills_registry=SkillRegistry(provider))


def test_the_catalog_message_is_injected_once_and_not_repeated(tmp_path: Path) -> None:
    root = tmp_path / "ws" / ".minihns" / "skills"
    _write_skill(root, "tdd")
    env = _env(tmp_path)

    _maybe_emit_catalog(env, "s1")  # type: ignore[arg-type]
    _maybe_emit_catalog(env, "s1")  # type: ignore[arg-type]

    messages = _catalog_messages(env.log)  # type: ignore[attr-defined]
    assert len(messages) == 1
    assert "tdd" in str(messages[0]["content"])
    assert messages[0]["source"] == "skill-catalog"


def test_a_changed_catalog_appends_a_replacement(tmp_path: Path) -> None:
    root = tmp_path / "ws" / ".minihns" / "skills"
    _write_skill(root, "tdd")
    env = _env(tmp_path)

    _maybe_emit_catalog(env, "s1")  # type: ignore[arg-type]
    _write_skill(root, "review")
    _maybe_emit_catalog(env, "s2")  # type: ignore[arg-type]

    messages = _catalog_messages(env.log)  # type: ignore[attr-defined]
    assert len(messages) == 2
    assert "review" in str(messages[-1]["content"])


def test_an_empty_catalog_retires_the_old_names(tmp_path: Path) -> None:
    root = tmp_path / "ws" / ".minihns" / "skills"
    path = _write_skill(root, "tdd")
    env = _env(tmp_path)

    _maybe_emit_catalog(env, "s1")  # type: ignore[arg-type]
    path.unlink()
    _maybe_emit_catalog(env, "s2")  # type: ignore[arg-type]

    messages = _catalog_messages(env.log)  # type: ignore[attr-defined]
    assert len(messages) == 2
    assert "不要使用之前目录里的技能名" in str(messages[-1]["content"])


def test_an_incomplete_catalog_warns_and_recovers(tmp_path: Path) -> None:
    root = tmp_path / "ws" / ".minihns" / "skills"
    _write_skill(root, "tdd")
    state = {"incomplete": True}
    env = _env(
        tmp_path,
        lambda: SkillDiscovery(
            discover_skills(tmp_path / "ws", {}).skills, complete=not state["incomplete"]
        ),
    )

    _maybe_emit_catalog(env, "s1")  # type: ignore[arg-type]
    state["incomplete"] = False
    _maybe_emit_catalog(env, "s2")  # type: ignore[arg-type]

    messages = _catalog_messages(env.log)  # type: ignore[attr-defined]
    assert len(messages) == 2
    assert "没能检查到" in str(messages[0]["content"])
    assert messages[0]["incomplete"] is True
    assert "没能检查到" not in str(messages[1]["content"])
    assert messages[1]["incomplete"] is False


def test_a_shadowed_catalog_is_reinjected(tmp_path: Path) -> None:
    root = tmp_path / "ws" / ".minihns" / "skills"
    _write_skill(root, "tdd")
    env = _env(tmp_path)
    _maybe_emit_catalog(env, "s1")  # type: ignore[arg-type]
    first = _catalog_messages(env.log)[0]  # type: ignore[attr-defined]
    seq = next(
        record.seq
        for record in read_events(env.log.path)  # type: ignore[attr-defined]
        if record.type == "user/message" and record.payload.get("source") == "skill-catalog"
    )
    env.log.append(  # type: ignore[attr-defined]
        "compaction/summary",
        {"shadowed_range": {"start": 0, "end": seq}, "tokens_before": 1, "tokens_after": 0},
    )

    _maybe_emit_catalog(env, "s2")  # type: ignore[arg-type]

    messages = _catalog_messages(env.log)  # type: ignore[attr-defined]
    assert len(messages) == 2
    assert messages[0]["digest"] == first["digest"]


def test_render_catalog_escapes_and_truncates() -> None:
    skill = Skill(
        name="tdd",
        description="<script> & " + "x" * 600,
        rank=100,
        path=Path("/tmp/tdd.md"),
    )

    content = render_catalog_message([skill], True)

    assert "&lt;script&gt;" in content
    assert "&amp;" in content
    assert "x" * 600 not in content
    assert "x" * 400 in content


def test_digest_includes_completeness() -> None:
    skills = (Skill(name="tdd", description="d", rank=100, path=Path("/tmp/tdd.md")),)

    assert catalog_digest(skills, True) != catalog_digest(skills, False)


def test_the_loop_emits_the_catalog_each_turn(tmp_path: Path) -> None:
    root = tmp_path / "ws" / ".minihns" / "skills"
    _write_skill(root, "tdd")
    calls = {"n": 0}

    def refresh() -> SkillDiscovery:
        calls["n"] += 1
        if calls["n"] == 2:
            _write_skill(root, "review")
        return discover_skills(tmp_path / "ws", {})

    _, env = build_session_env(
        tmp_path,
        "s-loop",
        FixtureProvider(
            entries=[
                tool_call_entry("read", "c1", path="a.md"),
                {"content": "完", "finish_reason": "stop"},
            ]
        ),
        workspace=tmp_path / "ws",
        registry=build_registry(None),
    )
    (tmp_path / "ws" / "a.md").write_text("内容\n", encoding="utf-8")
    env = replace(env, skills_registry=SkillRegistry(FilesystemProvider("filesystem", refresh)))
    import asyncio

    outcome = asyncio.run(
        run_session_env(prompt="任务", entry="run", env=env, cancel=asyncio.Event())
    )

    assert outcome.stop_reason == "MODEL_COMPLETED"
    messages = _catalog_messages(env.log)
    assert len(messages) == 2
    assert "review" in str(messages[-1]["content"])
