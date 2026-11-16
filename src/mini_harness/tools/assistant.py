"""助理 UX 工具（M14c）：`exit_plan_mode` 先落，其余三件在后续切片。"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from mini_harness.tools.fences import DispatchContext
from mini_harness.tools.registry import ToolArgs, ToolDefinition, ToolResult


class ExitPlanModeArgs(ToolArgs):
    """提交计划正文；批准由 dispatch 里的审批分支完成。"""

    plan: str = Field(description="完整计划正文，供人复核")


async def _exit_plan_mode(args: ExitPlanModeArgs, context: DispatchContext) -> ToolResult:
    return ToolResult("OK", "计划已获批准，退出计划模式")


class TodoItem(BaseModel):
    """一条待办；`id` 由模型自己维护，用于后续更新与完成。"""

    id: str = Field(description="稳定的条目 id，例如 t1")
    text: str = Field(description="要做的事，一句话")
    status: Literal["pending", "in_progress", "completed"] = "pending"


class TodoArgs(ToolArgs):
    """整张待办表；每次调用都提交完整列表（照 DSH 的 whole-list replacement）。"""

    items: list[TodoItem] = Field(description="完整待办列表，按顺序")


async def _todo(args: TodoArgs, context: DispatchContext) -> ToolResult:
    counts = {"pending": 0, "in_progress": 0, "completed": 0}
    for item in args.items:
        counts[item.status] += 1
    text = (
        f"已更新待办：{counts['pending']} 待办，"
        f"{counts['in_progress']} 进行中，{counts['completed']} 完成"
    )
    return ToolResult("OK", text, meta={"todo_updated": True})


def assistant_tool_definitions() -> list[ToolDefinition]:
    """`exit_plan_mode` 与 `todo`。"""
    return [
        ToolDefinition(
            name="exit_plan_mode",
            description="在计划模式里提交计划正文并请求批准；只有批准后才退出计划模式。",
            args_model=ExitPlanModeArgs,
            mutates=False,
            concurrency="parallel",
            run=_exit_plan_mode,
        ),
        ToolDefinition(
            name="todo",
            description="提交完整待办列表；每次调用都替换整张表，用 status 标记进度。",
            args_model=TodoArgs,
            mutates=False,
            concurrency="parallel",
            run=_todo,
        ),
    ]
