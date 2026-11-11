"""`skill` 工具：按需把一个技能的正文读进上下文（M14 的渐进式披露）。

正文在调用时读盘，但结果作为 `tool/result` 落日志——回放只认日志，不认磁盘上的当前内容。
"""

from __future__ import annotations

from collections.abc import Sequence

from pydantic import Field

from mini_harness.skills import Skill, read_skill_body
from mini_harness.tools.fences import DispatchContext
from mini_harness.tools.registry import ToolArgs, ToolDefinition, ToolResult


class SkillArgs(ToolArgs):
    """`skill` 的入参：一个技能名（kebab-case）。"""

    name: str = Field(description="技能名，例如 tdd")


def skill_tool_definitions(skills: Sequence[Skill]) -> list[ToolDefinition]:
    """一个 `skill` 定义；结果用 DSH 同形的 XML 三段包正文。"""

    async def run(args: SkillArgs, context: DispatchContext) -> ToolResult:
        skill = next((candidate for candidate in skills if candidate.name == args.name), None)
        if skill is None:
            return ToolResult("TOOL_ARGS_INVALID", f"未知技能：{args.name}")
        content = (
            f'<skill_content name="{skill.name}">\n'
            f"<skill_resources>\n- {skill.path}\n</skill_resources>\n"
            f"<skill_instructions>\n{read_skill_body(skill)}\n</skill_instructions>\n"
            f"</skill_content>"
        )
        return ToolResult("OK", content)

    return [
        ToolDefinition(
            name="skill",
            description="按名字加载一个技能的正文；技能清单在受保护头部里。",
            args_model=SkillArgs,
            mutates=False,
            run=run,
            concurrency="parallel",
        )
    ]
