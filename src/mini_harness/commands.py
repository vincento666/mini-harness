"""命令面（M14）：人机直连的 UI 动作，不创建模型消息、不开启段。

命令的语法/未知名字是 admission miss——调用方不落任何日志；已知命令的参数错误是
handler 的结果（`ok=false`），照样落 `command/run` + `command/done`（照 DSH）。
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from mini_harness.skills import Skill, read_skill_body


@dataclass(frozen=True)
class CommandSpec:
    """一条命令的名字与一句描述；CLI 与 host 共用这份清单。"""

    name: str
    description: str


COMMANDS: tuple[CommandSpec, ...] = (
    CommandSpec("skills", "列出可用技能"),
    CommandSpec("skill", "加载一个技能的正文"),
)


RESERVED = frozenset(command.name for command in COMMANDS) | {"help"}


def command_catalog(skills: Sequence[Skill]) -> list[CommandSpec]:
    """内置命令 + 技能命令；内置名优先（技能同名时不覆盖，仍可用 `/skill <名字>`）。"""
    catalog = list(COMMANDS)
    seen = set(RESERVED)
    for skill in skills:
        if skill.name in seen:
            continue
        seen.add(skill.name)
        catalog.append(CommandSpec(skill.name, skill.description))
    return catalog


@dataclass(frozen=True)
class CommandOutcome:
    """handler 的结果：成功与否 + 给 UI 的文本。"""

    ok: bool
    text: str


def execute_command(
    name: str, arguments: str, skills: Sequence[Skill]
) -> CommandOutcome | None:
    """执行一条命令；未知命令返回 `None`（admission miss，不落日志）。"""
    if name == "skills":
        if arguments.strip():
            return CommandOutcome(False, "用法：/skills")
        lines = [f"- {skill.name}（rank {skill.rank}）：{skill.description}" for skill in skills]
        return CommandOutcome(True, "\n".join(lines) if lines else "（没有发现技能）")
    if name == "skill":
        target = arguments.strip()
        if not target:
            return CommandOutcome(False, "用法：/skill <name>")
        skill = next((candidate for candidate in skills if candidate.name == target), None)
        if skill is None:
            return CommandOutcome(False, f"未知技能：{target}")
        return CommandOutcome(True, read_skill_body(skill))
    if name in RESERVED:
        # `help` 是壳本地的帮助，不在这里执行。
        return None
    direct = next((candidate for candidate in skills if candidate.name == name), None)
    if direct is None:
        return None
    if arguments.strip():
        return CommandOutcome(False, f"用法：/{name}")
    return CommandOutcome(True, read_skill_body(direct))
