"""文件工具的执行入口与入参模型。注册表里的工具由这里造出来。"""

from __future__ import annotations

from pathlib import Path

from pydantic import Field

from mini_harness.tools.fences import DispatchContext, path_key
from mini_harness.tools.registry import ToolArgs, ToolDefinition, ToolResult

DEFAULT_READ_LIMIT = 2000


class ReadArgs(ToolArgs):
    file_path: str
    offset: int = Field(default=1, ge=1)
    limit: int = Field(default=DEFAULT_READ_LIMIT, ge=1)

    def target_path(self) -> str | None:
        return self.file_path


def resolve_target(workspace: Path, raw_path: str) -> Path:
    """`file_path` / `path` 相对工作区根解析；给了绝对路径就按绝对路径。"""
    candidate = Path(raw_path)
    if not candidate.is_absolute():
        candidate = workspace / candidate
    return candidate


async def read_file(args: ReadArgs, context: DispatchContext) -> ToolResult:
    target = resolve_target(context.workspace, args.file_path)
    if not target.exists():
        return ToolResult(outcome="PATH_NOT_FOUND", content=f"路径不存在：{target}")
    if target.is_dir():
        return ToolResult(outcome="IS_A_DIRECTORY", content=f"目标是目录而不是文件：{target}")
    try:
        text = target.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return ToolResult(outcome="NOT_UTF8_TEXT", content=f"不是合法 UTF-8 文本：{target}")

    start = args.offset - 1
    window = text.splitlines()[start : start + args.limit]
    numbered = [f"{index}: {line}" for index, line in enumerate(window, start=args.offset)]
    return ToolResult(outcome="OK", content="\n".join(numbered))


class WriteArgs(ToolArgs):
    file_path: str
    content: str

    def target_path(self) -> str | None:
        return self.file_path


async def write_file(args: WriteArgs, context: DispatchContext) -> ToolResult:
    target = resolve_target(context.workspace, args.file_path)
    if target.is_dir():
        return ToolResult(outcome="IS_A_DIRECTORY", content=f"目标是目录而不是文件：{target}")
    if target.exists() and path_key(context.workspace, args.file_path) not in context.read_paths:
        return ToolResult(
            outcome="WRITE_WITHOUT_READ",
            content=f"覆盖已存在的文件之前没有读过它：{target}",
        )

    if target.parent != target:
        target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(args.content, encoding="utf-8")
    return ToolResult(outcome="OK", content=f"写了 {target}（{len(args.content)} 个字符）")


def file_tool_definitions() -> list[ToolDefinition]:
    """注册表的内容：每个工具的定义、入参模型、会不会改动、执行入口。"""
    return [
        ToolDefinition(
            name="read",
            description="读取 UTF-8 文本文件，返回带行号前缀的窗口。",
            args_model=ReadArgs,
            mutates=False,
            run=read_file,
        ),
        ToolDefinition(
            name="write",
            description="覆盖式写入 UTF-8 文本文件；覆盖已存在的文件前必须先读过。",
            args_model=WriteArgs,
            mutates=True,
            run=write_file,
        ),
    ]
