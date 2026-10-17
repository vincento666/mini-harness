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


class WriteArgs(ToolArgs):
    file_path: str
    content: str

    def target_path(self) -> str | None:
        return self.file_path


class EditArgs(ToolArgs):
    file_path: str
    old_string: str = Field(min_length=1)
    new_string: str
    replace_all: bool = False

    def target_path(self) -> str | None:
        return self.file_path


def resolve_target(workspace: Path, raw_path: str) -> Path:
    """`file_path` / `path` 相对工作区根解析；给了绝对路径就按绝对路径。"""
    candidate = Path(raw_path)
    if not candidate.is_absolute():
        candidate = workspace / candidate
    return candidate


def _numbered_window(text: str, offset: int, limit: int | None) -> str:
    start = offset - 1
    width = DEFAULT_READ_LIMIT if limit is None else limit
    window = text.splitlines()[start : start + width]
    return "\n".join(f"{index}: {line}" for index, line in enumerate(window, start=offset))


def _read_body(target: Path) -> str | None:
    """读文本；不是合法 UTF-8 就返回 None。"""
    try:
        return target.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return None


async def read_file(args: ReadArgs, context: DispatchContext) -> ToolResult:
    target = resolve_target(context.workspace, args.file_path)
    if not target.exists():
        return ToolResult(outcome="PATH_NOT_FOUND", content=f"路径不存在：{target}")
    if target.is_dir():
        return ToolResult(outcome="IS_A_DIRECTORY", content=f"目标是目录而不是文件：{target}")
    body = _read_body(target)
    if body is None:
        return ToolResult(outcome="NOT_UTF8_TEXT", content=f"不是合法 UTF-8 文本：{target}")
    return ToolResult(outcome="OK", content=_numbered_window(body, args.offset, args.limit))


async def write_file(args: WriteArgs, context: DispatchContext) -> ToolResult:
    target = resolve_target(context.workspace, args.file_path)
    if target.is_dir():
        return ToolResult(outcome="IS_A_DIRECTORY", content=f"目标是目录而不是文件：{target}")
    if target.exists() and path_key(context.workspace, args.file_path) not in context.reads:
        return ToolResult(
            outcome="WRITE_WITHOUT_READ",
            content=f"覆盖已存在的文件之前没有读过它：{target}",
        )

    if target.parent != target:
        target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(args.content, encoding="utf-8")
    return ToolResult(outcome="OK", content=f"写了 {target}（{len(args.content)} 个字符）")


async def edit_file(args: EditArgs, context: DispatchContext) -> ToolResult:
    target = resolve_target(context.workspace, args.file_path)
    prior = context.reads.get(path_key(context.workspace, args.file_path))
    if prior is None:
        return ToolResult(outcome="WRITE_WITHOUT_READ", content=f"edit 之前没有读过它：{target}")
    if not target.exists():
        return ToolResult(outcome="PATH_NOT_FOUND", content=f"路径不存在：{target}")
    if target.is_dir():
        return ToolResult(outcome="IS_A_DIRECTORY", content=f"目标是目录而不是文件：{target}")
    body = _read_body(target)
    if body is None:
        return ToolResult(outcome="NOT_UTF8_TEXT", content=f"不是合法 UTF-8 文本：{target}")
    if _numbered_window(body, prior.offset, prior.limit) != prior.content:
        return ToolResult(
            outcome="STALE_EDIT",
            content=f"文件内容与读到的不一致，先重新 read：{target}",
        )

    matches = body.count(args.old_string)
    if matches == 0:
        return ToolResult(
            outcome="EDIT_TARGET_NOT_FOUND",
            content=f"没有找到要替换的字面串：{args.old_string}",
        )
    if matches > 1 and not args.replace_all:
        return ToolResult(
            outcome="EDIT_TARGET_AMBIGUOUS",
            content=f"该字面串出现 {matches} 次，要么给更长的串，要么 replace_all",
        )

    count = matches if args.replace_all else 1
    target.write_text(body.replace(args.old_string, args.new_string, count), encoding="utf-8")
    return ToolResult(outcome="OK", content=f"替换了 {count} 处：{target}")


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
        ToolDefinition(
            name="edit",
            description="在已读过的文件里做字面替换；old_string 必须恰好出现一次。",
            args_model=EditArgs,
            mutates=True,
            run=edit_file,
        ),
    ]
