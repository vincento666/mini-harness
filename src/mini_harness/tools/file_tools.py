"""文件工具的执行入口与入参模型。注册表里的工具由这里造出来。"""

from __future__ import annotations

import os
import re
from pathlib import Path

from pydantic import Field, field_validator

from mini_harness.tools.fences import DispatchContext, path_key
from mini_harness.tools.registry import ToolArgs, ToolDefinition, ToolResult

DEFAULT_READ_LIMIT = 2000
READ_MAX_BYTES = 51200
READ_MAX_LINE_LENGTH = 2000
GLOB_LIMIT = 100
GREP_LIMIT = 250
GREP_MAX_LINE_CHARS = 2000
GREP_RAW_MAX_BYTES = 20_000_000


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


class GlobArgs(ToolArgs):
    pattern: str
    path: str = "."

    def target_path(self) -> str | None:
        return self.path


class GrepArgs(ToolArgs):
    pattern: str
    path: str = "."

    @field_validator("pattern")
    @classmethod
    def compile_pattern(cls, value: str) -> str:
        try:
            re.compile(value)
        except re.error as exc:
            raise ValueError(f"不是合法的正则：{exc}") from exc
        return value

    def target_path(self) -> str | None:
        return self.path


def resolve_target(workspace: Path, raw_path: str) -> Path:
    """`file_path` / `path` 相对工作区根解析；给了绝对路径就按绝对路径。"""
    candidate = Path(raw_path)
    if not candidate.is_absolute():
        candidate = workspace / candidate
    return candidate


def _numbered_window(text: str, offset: int, limit: int | None) -> str:
    """read/edit 共用的窗口：行数、单行 2000 字符、总字节 51200，先到者生效。

    只有被字节/单行上限截断时才加 capped footer；显式 `limit` 的普通窗口保持原样。
    """
    start = offset - 1
    width = DEFAULT_READ_LIMIT if limit is None else limit
    selected = text.splitlines()[start : start + width]
    rendered: list[str] = []
    total_bytes = 0
    capped = False
    for index, line in enumerate(selected, start=offset):
        if len(line) > READ_MAX_LINE_LENGTH:
            line = line[:READ_MAX_LINE_LENGTH] + (
                f"... (line truncated to {READ_MAX_LINE_LENGTH} chars)"
            )
            capped = True
        numbered = f"{index}: {line}"
        cost = len(numbered.encode("utf-8")) + 1
        if rendered and total_bytes + cost > READ_MAX_BYTES:
            capped = True
            break
        rendered.append(numbered)
        total_bytes += cost
    content = "\n".join(rendered)
    if capped and rendered:
        end = offset + len(rendered) - 1
        content += (
            f"\n\n(Output capped. Showing lines {offset}-{end}. Use offset={end + 1} to continue.)"
        )
    return content


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


def _relative_to(workspace: Path, target: Path) -> str:
    try:
        return target.relative_to(workspace).as_posix()
    except ValueError:
        return os.path.relpath(target, workspace).replace("\\", "/")


def _search_root(context: DispatchContext, args: GlobArgs | GrepArgs) -> Path | ToolResult:
    root = resolve_target(context.workspace, args.path)
    if not root.exists():
        return ToolResult(outcome="PATH_NOT_FOUND", content=f"搜索根不存在：{root}")
    if not root.is_dir():
        return ToolResult(outcome="NOT_A_DIRECTORY", content=f"搜索根不是目录：{root}")
    return root


async def glob_files(args: GlobArgs, context: DispatchContext) -> ToolResult:
    root = _search_root(context, args)
    if isinstance(root, ToolResult):
        return root

    matches = [entry for entry in root.glob(args.pattern) if entry.is_file()]
    matches.sort(key=lambda entry: entry.stat().st_mtime, reverse=True)
    if not matches:
        return ToolResult(outcome="OK", content=f"没有文件匹配该模式：{args.pattern}")

    shown = matches[:GLOB_LIMIT]
    lines = [_relative_to(context.workspace, entry) for entry in shown]
    if len(matches) > len(shown):
        lines.append(f"共 {len(matches)} 个匹配，只列出前 {GLOB_LIMIT} 个。")
    return ToolResult(outcome="OK", content="\n".join(lines))


async def search_files(args: GrepArgs, context: DispatchContext) -> ToolResult:
    root = _search_root(context, args)
    if isinstance(root, ToolResult):
        return root

    expression = re.compile(args.pattern)
    hits: list[str] = []
    total = 0
    raw_bytes = 0
    for entry in sorted(root.rglob("*")):
        if not entry.is_file():
            continue
        body = _read_body(entry)
        if body is None:
            continue
        raw_bytes += len(body.encode("utf-8"))
        if raw_bytes > GREP_RAW_MAX_BYTES:
            hits.append(f"[raw output capped at {GREP_RAW_MAX_BYTES} bytes]")
            break
        for number, line in enumerate(body.splitlines(), start=1):
            if not expression.search(line):
                continue
            total += 1
            if len(hits) < GREP_LIMIT:
                preview = line
                if len(preview) > GREP_MAX_LINE_CHARS:
                    preview = (
                        preview[:GREP_MAX_LINE_CHARS]
                        + f"... (line truncated to {GREP_MAX_LINE_CHARS} chars)"
                    )
                relative = _relative_to(context.workspace, entry)
                hits.append(f"{relative}:{number}: {preview}")

    if total == 0:
        return ToolResult(outcome="OK", content=f"没有匹配：{args.pattern}")
    if total > len(hits):
        hits.append(f"共 {total} 条匹配，只列出前 {GREP_LIMIT} 条。")
    return ToolResult(outcome="OK", content="\n".join(hits))


def file_tool_definitions() -> list[ToolDefinition]:
    """注册表的内容：每个工具的定义、入参模型、会不会改动、执行入口。"""
    return [
        ToolDefinition(
            name="read",
            description=(
                "读取 UTF-8 文本文件，返回带行号前缀的窗口。"
                "要读文件就用它：不要用 bash 里的 cat 这类等价命令，也不必临时写脚本。"
            ),
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
        ToolDefinition(
            name="glob",
            description=(
                "按 glob 模式匹配工作区里的文件，返回相对路径，按修改时间从新到旧。"
                "要列文件就用它（只列文件，不含子目录）：不要用 bash 里的 ls 这类等价命令，"
                "也不必临时写脚本。"
            ),
            args_model=GlobArgs,
            mutates=False,
            run=glob_files,
        ),
        ToolDefinition(
            name="grep",
            description=(
                "按正则搜索文本文件，返回「文件:行号: 行内容」形式的匹配行。"
                "要搜内容就用它：不要用 bash 里的 grep 这类等价命令，也不必临时写脚本。"
            ),
            args_model=GrepArgs,
            mutates=False,
            run=search_files,
        ),
    ]
