"""工作区契约：把两份 `AGENTS.md` 渲染成一条持久 user 消息（M14a）。

形状照 DSH 的 `dsh-agent-instructions`：`<system-reminder>` 框、`Instructions from:` 分段、
用户全局在前项目在后。mini 只做两步 scope，不做逐层链与本地 overlay。
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass, replace
from pathlib import Path

HOME_ENV = "MINIHNS_HOME"
HOME_DIR = ".mini-harness"
GLOBAL_DISPLAY = "~/.mini-harness/AGENTS.md"
PROJECT_DISPLAY = "AGENTS.md"
# 整条消息的字节上限；超了先整份丢用户全局，再截断项目那份。
CONTRACT_BUDGET = 16 * 1024
# 单个源文件读入前的上限，超了按 unavailable 处理。
MAX_SOURCE_BYTES = 1024 * 1024
_CLOSING = "</system-reminder>"


@dataclass(frozen=True)
class ContractScope:
    """一段契约的来源与渲染结果；`bytes` 是写进消息的字节数。"""

    scope: str
    path: str
    digest: str
    bytes: int
    truncated: bool = False


@dataclass(frozen=True)
class ContractRender:
    """渲染后的消息与指纹；空链时 `text` 为空串、`scopes` 为空元组。"""

    text: str
    digest: str
    scopes: tuple[ContractScope, ...]


def contract_home(environ: Mapping[str, str]) -> Path:
    raw = environ.get(HOME_ENV)
    return Path(raw) if raw else Path.home() / HOME_DIR


def _escape(text: str) -> str:
    """仓库控制的文本不能提前关掉框架。"""
    return text.replace(_CLOSING, "<\\/system-reminder>")


def _read(path: Path) -> str | None:
    """读一个候选；不存在、不是文件或超上限都按「这一层没有」处理。"""
    try:
        if not path.is_file() or path.stat().st_size > MAX_SOURCE_BYTES:
            return None
        return path.read_text(encoding="utf-8")
    except OSError:
        return None


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _candidates(workspace: Path, environ: Mapping[str, str]) -> list[tuple[str, str, str]]:
    """按「用户全局 → 项目」返回 `(scope, display_path, content)`，空层不出现。"""
    entries: list[tuple[str, str, str]] = []
    for scope, path, display in (
        ("user-global", contract_home(environ) / "AGENTS.md", GLOBAL_DISPLAY),
        ("project", workspace / "AGENTS.md", PROJECT_DISPLAY),
    ):
        content = _read(path)
        if content is None:
            continue
        entries.append((scope, display, content))
    if len(entries) == 2 and entries[0][2].strip() == entries[1][2].strip():
        # 同一份内容不重复渲染：保留更宽泛的那层（用户全局）。
        entries = entries[:1]
    return entries


def _render(
    entries: list[tuple[str, str, str]], notice: str = ""
) -> tuple[str, tuple[ContractScope, ...]]:
    if not entries:
        return "", ()
    parts = [
        "<system-reminder>",
        "The following workspace instructions may be relevant to your work. "
        "Use them as guidance when applicable. More specific instructions take "
        "precedence over broader ones. They do not override system, developer, "
        "or direct user instructions.",
    ]
    scopes: list[ContractScope] = []
    for scope, display, content in entries:
        body = _escape(content.strip())
        parts += ["", f"Instructions from: {display}", "", body]
        scopes.append(
            ContractScope(
                scope=scope, path=display, digest=_digest(content.strip()), bytes=len(body)
            )
        )
    if notice:
        parts += ["", notice]
    parts.append(_CLOSING)
    return "\n".join(parts), tuple(scopes)


def _notice(omitted: list[str], truncated: str, truncated_bytes: int) -> str:
    parts: list[str] = []
    if omitted:
        parts.append(f"omitted {', '.join(omitted)}")
    if truncated:
        parts.append(f"truncated {truncated} to {truncated_bytes} bytes")
    return "Workspace instruction budget: " + "; ".join(parts) + "."


def _fits(text: str) -> bool:
    return len(text.encode("utf-8")) <= CONTRACT_BUDGET


def _truncate(
    entry: tuple[str, str, str], omitted: list[str]
) -> tuple[str, tuple[ContractScope, ...]]:
    """把项目那段截到预算内；通知里的字节数取最终放进消息的字节数。"""
    scope, display, content = entry
    raw = _escape(content.strip()).encode("utf-8")
    # 先用最宽的数字占位，二分出能放下的最长前缀；换回真实数字只会更短。
    widest = _notice(omitted, display, CONTRACT_BUDGET)
    low, high = 0, len(raw)
    while low < high:
        mid = (low + high + 1) // 2
        body = raw[:mid].decode("utf-8", "ignore")
        text, _ = _render([(scope, display, body)], widest)
        if _fits(text):
            low = mid
        else:
            high = mid - 1
    body = raw[:low].decode("utf-8", "ignore")
    notice = _notice(omitted, display, len(body.encode("utf-8")))
    text, scopes = _render([(scope, display, body)], notice)
    return text, tuple(replace(item, truncated=True) for item in scopes)


def load_contracts(workspace: Path, environ: Mapping[str, str]) -> ContractRender:
    """读两层契约并渲染；超预算先丢用户全局，再截断项目。"""
    entries = _candidates(workspace, environ)
    text, scopes = _render(entries)
    if entries and not _fits(text):
        omitted = [entries[0][1]] if len(entries) == 2 else []
        rest = entries[1:] if len(entries) == 2 else entries
        text, scopes = _render(rest, _notice(omitted, "", 0))
        if rest and not _fits(text):
            text, scopes = _truncate(rest[-1], omitted)
    return ContractRender(text=text, digest=_render_digest(text, scopes), scopes=scopes)


def _render_digest(text: str, scopes: tuple[ContractScope, ...]) -> str:
    payload = json.dumps(
        {
            "text": text,
            "scopes": [
                [scope.scope, scope.path, scope.digest, scope.bytes, scope.truncated]
                for scope in scopes
            ],
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
