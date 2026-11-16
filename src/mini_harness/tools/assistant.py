"""助理 UX 工具（M14c）：`exit_plan_mode` 先落，其余三件在后续切片。"""

from __future__ import annotations

from pydantic import Field

from mini_harness.tools.fences import DispatchContext
from mini_harness.tools.registry import ToolArgs, ToolDefinition, ToolResult


class ExitPlanModeArgs(ToolArgs):
    """提交计划正文；批准由 dispatch 里的审批分支完成。"""

    plan: str = Field(description="完整计划正文，供人复核")


async def _exit_plan_mode(args: ExitPlanModeArgs, context: DispatchContext) -> ToolResult:
    return ToolResult("OK", "计划已获批准，退出计划模式")


def assistant_tool_definitions() -> list[ToolDefinition]:
    """当前只有一个：`exit_plan_mode`。"""
    return [
        ToolDefinition(
            name="exit_plan_mode",
            description="在计划模式里提交计划正文并请求批准；只有批准后才退出计划模式。",
            args_model=ExitPlanModeArgs,
            mutates=False,
            concurrency="parallel",
            run=_exit_plan_mode,
        )
    ]
