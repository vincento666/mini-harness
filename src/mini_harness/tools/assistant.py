"""助理 UX 工具（M14c）：`exit_plan_mode` 先落，其余三件在后续切片。"""

from __future__ import annotations

import uuid
from typing import Literal

from pydantic import BaseModel, Field

from mini_harness.events.projection import render_todos
from mini_harness.events.writer import LogWriteFailure
from mini_harness.tools.fences import DispatchContext
from mini_harness.tools.registry import ToolArgs, ToolDefinition, ToolResult


class ExitPlanModeArgs(ToolArgs):
    """提交计划正文；批准由 dispatch 里的审批分支完成。"""

    plan: str = Field(description="完整计划正文，供人复核")


class AskUserArgs(ToolArgs):
    """一个普通问题；`options` 为空表示自由回答。"""

    question: str = Field(description="要问人的问题，一句话")
    options: list[str] = Field(default_factory=list, description="可选项；空表示自由回答")


async def _ask_user(args: AskUserArgs, context: DispatchContext) -> ToolResult:
    question_id = context.tool_call_id or uuid.uuid4().hex
    log = context.session.log if context.session is not None else None
    if log is not None:
        asked = log.append(
            "question/asked",
            {"question_id": question_id, "question": args.question, "options": args.options},
        )
        if isinstance(asked, LogWriteFailure):
            return ToolResult("TOOL_IO_FAILED", "问题写不进日志，没有向人提问")
    answer = await context.question_gate.request(
        question_id=question_id, question=args.question, options=args.options
    )
    if answer is None:
        # 记在会话上：自动轮次里问不到人时，驱动据此不再开下一段（design D11）。
        if context.session is not None:
            context.session.questions.pending = question_id
        return ToolResult("QUESTION_UNAVAILABLE", "没有问不到人的答案：问题保持未决")
    if context.session is not None:
        context.session.questions.pending = None
    if log is not None:
        answered = log.append("question/answered", {"question_id": question_id, "answer": answer})
        if isinstance(answered, LogWriteFailure):
            return ToolResult("TOOL_IO_FAILED", "答案写不进日志，本次问答作废")
    return ToolResult("OK", answer, meta={"question_id": question_id})


class PresentArgs(ToolArgs):
    """把工作区内的一个产物交给壳。"""

    path: str = Field(description="产物路径，相对工作区")
    title: str = Field(description="给产物起一个短标题")


async def _present(args: PresentArgs, context: DispatchContext) -> ToolResult:
    workspace = context.workspace.resolve()
    target = (workspace / args.path).resolve()
    if not target.is_relative_to(workspace) or not target.is_file():
        return ToolResult("PRESENT_INVALID_PATH", f"产物不在工作区内或不存在：{args.path}")
    relative = target.relative_to(workspace).as_posix()
    return ToolResult(
        "OK",
        f"产物：{relative}",
        meta={"present_path": relative, "present_title": args.title},
    )


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
    if not context.goal_policy.allow_parallel_in_progress:
        running = [item for item in args.items if item.status == "in_progress"]
        if len(running) > 1:
            return ToolResult(
                "TODO_PARALLEL_DISABLED",
                f"当前部署不允许同时进行多个任务（收到 {len(running)} 个）",
            )
    counts = {"pending": 0, "in_progress": 0, "completed": 0}
    for item in args.items:
        counts[item.status] += 1
    text = (
        f"已更新待办：{counts['pending']} 待办，"
        f"{counts['in_progress']} 进行中，{counts['completed']} 完成"
    )
    return ToolResult("OK", text, meta={"todo_updated": True})


class GetTodosArgs(ToolArgs):
    """无入参：读回当前待办表。"""


async def _get_todos(args: GetTodosArgs, context: DispatchContext) -> ToolResult:
    """读回这一段的待办表；只读，不写 `todo/updated`。

    事实只有一个来源：`todos` 投影。所以它读到的与 `/todo`、`GET /projections/todos`
    是同一个值——`segment/start` 清空之后这里也是空表。
    """
    items = list(context.todos)
    if not items:
        return ToolResult(
            "OK",
            "当前待办为空：本段还没有提交过待办表（`todo` 提交整表后才会出现）",
            meta={"todo_read": True, "todo_count": 0},
        )
    counts = {"pending": 0, "in_progress": 0, "completed": 0}
    for item in items:
        status = item.get("status")
        if status in counts:
            counts[status] += 1
    header = (
        f"当前待办：{counts['pending']} 待办，{counts['in_progress']} 进行中，"
        f"{counts['completed']} 完成"
    )
    return ToolResult(
        "OK",
        "\n".join([header, *render_todos(items)]),
        meta={"todo_read": True, "todo_count": len(items)},
    )


def assistant_tool_definitions() -> list[ToolDefinition]:
    """`exit_plan_mode`、`present`、`ask_user`、`todo` 与 `get_todos`。"""
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
            name="present",
            description="把工作区内的产物交给壳；只接受已存在的文件。",
            args_model=PresentArgs,
            mutates=False,
            concurrency="parallel",
            run=_present,
        ),
        ToolDefinition(
            name="ask_user",
            description="向人提一个普通问题并等待回答；问不到人时返回 QUESTION_UNAVAILABLE。",
            args_model=AskUserArgs,
            mutates=False,
            concurrency="exclusive",
            run=_ask_user,
        ),
        ToolDefinition(
            name="todo",
            description="提交完整待办列表；每次调用都替换整张表，用 status 标记进度。",
            args_model=TodoArgs,
            mutates=False,
            concurrency="parallel",
            run=_todo,
        ),
        ToolDefinition(
            name="get_todos",
            description="读回本段当前的待办表；上下文里看不见表（例如被压缩遮住）时用它。",
            args_model=GetTodosArgs,
            mutates=False,
            concurrency="parallel",
            run=_get_todos,
        ),
    ]
