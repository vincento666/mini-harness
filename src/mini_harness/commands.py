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
        if not skill.user_invocable or skill.name in seen:
            continue
        seen.add(skill.name)
        catalog.append(CommandSpec(skill.name, skill.description))
    return catalog


def direct_skill(name: str, skills: Sequence[Skill]) -> Skill | None:
    """`/<技能名>` 命中的用户可调技能；内置命令名优先，返回 None。"""
    if name in RESERVED:
        return None
    return next(
        (
            candidate
            for candidate in skills
            if candidate.name == name and candidate.user_invocable
        ),
        None,
    )


def find_skill(name: str, skills: Sequence[Skill]) -> Skill | None:
    """按名字找技能（不分策略），供命令面区分「未知」与「不可由用户调用」。"""
    return next((candidate for candidate in skills if candidate.name == name), None)


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
        lines = [
            f"- {skill.name}（rank {skill.rank}）：{skill.description}"
            for skill in skills
            if skill.user_invocable
        ]
        return CommandOutcome(True, "\n".join(lines) if lines else "（没有发现技能）")
    if name == "skill":
        target = arguments.strip()
        if not target:
            return CommandOutcome(False, "用法：/skill <name>")
        skill = find_skill(target, skills)
        if skill is None:
            return CommandOutcome(False, f"未知技能：{target}")
        if not skill.user_invocable:
            return CommandOutcome(False, f"技能 {target} 不可由用户调用")
        return CommandOutcome(True, read_skill_body(skill))
    # 直接技能名由壳走「注入 + 开段」的执行路径；这里只处理 /skills 与 /skill。
    return None
