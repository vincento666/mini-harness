"""围栏判定：工作区边界 + `--sandbox` 档位 + 派发上下文。只由 harness 自身判定，不做 OS 级强制。"""

from __future__ import annotations

import asyncio
import os
import sys
import threading
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, Protocol, TextIO

from mini_harness.events.record import EventRecord

if TYPE_CHECKING:
    # 只给类型检查看：运行时导入会绕成 fences → loop → tools.dispatch → fences 的环。
    from mini_harness.loop.settings import ApprovalMode, SandboxLevel, SessionSettings

FenceCode = Literal[
    "OUTSIDE_WORKSPACE",
    "SANDBOX_DENIES_WRITE",
    "APPROVAL_DENIED",
    "APPROVAL_UNAVAILABLE",
]
FenceOutcome = Literal["ALLOWED", "NEEDS_APPROVAL", "DENIED"]


@dataclass(frozen=True)
class PriorRead:
    """这段前缀里最后一次成功 `read` 留下的事实，CAS 与写前必读都只认它。"""

    raw_path: str
    offset: int
    limit: int | None
    content: str


@dataclass(frozen=True)
class DispatchContext:
    """一次派发能看到的全部事实：工具只读它，不读进程内状态。"""

    workspace: Path
    sandbox: SandboxLevel
    approval: ApprovalMode
    reads: Mapping[str, PriorRead] = field(default_factory=dict)

    @classmethod
    def from_settings(
        cls, settings: SessionSettings, *, reads: Mapping[str, PriorRead] | None = None
    ) -> DispatchContext:
        return cls(
            workspace=settings.workspace,
            sandbox=settings.sandbox,
            approval=settings.approval,
            reads=reads or {},
        )


@dataclass(frozen=True)
class FenceDecision:
    """围栏段的结论。被拒也是结果，不是异常。

    `path` 是判定实际使用的解析后键（档位轴先拒、或调用没有目标路径时是 `None`）；
    `raw_path` 是调用里写的原始写法。两者进 `error/fence` 的 payload。
    """

    outcome: FenceOutcome
    code: FenceCode | None = None
    detail: str = ""
    path: str | None = None
    raw_path: str | None = None


def path_key(workspace: Path, raw_path: str) -> str:
    """入参路径 → 判定用的键。

    相对工作区根解析；`os.path.realpath` 解析 junction 与符号链接；Windows 上 `normcase` 折叠
    大小写——否则同一个文件换一种写法就能绕过写前必读与 CAS。
    """
    candidate = Path(raw_path)
    if not candidate.is_absolute():
        candidate = workspace / candidate
    resolved = os.path.realpath(candidate)
    if os.name == "nt":
        resolved = os.path.normcase(resolved)
    return resolved


def _is_inside_workspace(workspace: Path, key: str) -> bool:
    root = Path(path_key(workspace, "."))
    target = Path(key)
    return target == root or target.is_relative_to(root)


ApprovalDecision = Literal["APPROVED", "DENIED", "UNAVAILABLE"]


class ApprovalGate(Protocol):
    """问一次 → 结论。内核只认这个接口：CLI 层接真实 stdin，测试注入固定结论。

    它是 awaitable：M3 之后提问可以被取消打断（ADR-0007）。挂在「等人回答」里的调用
    必须能被中断，否则取消只能等人先答完。
    """

    async def request(
        self, *, tool_call_id: str, tool_name: str, detail: str
    ) -> ApprovalDecision: ...


def _settle(target: asyncio.Future[str], text: str) -> None:
    """回答回来了，但等它的人可能已经被取消：已经定论的 future 不再写。"""
    if not target.done():
        target.set_result(text)


async def _await_readline(source: TextIO) -> str:
    """在一行回答上等待，同时允许等它的人被取消。

    `readline()` 是阻塞调用，放在 daemon 线程里等：事件循环不被一行回答钉住，取消才插得进来。
    用 daemon 线程而不是 `asyncio.to_thread`——后者的工作线程不是 daemon，解释器退出时要 join，
    一条永远等不到回答的 `readline` 会把退出一起挂住。
    """
    loop = asyncio.get_running_loop()
    answer: asyncio.Future[str] = loop.create_future()

    def read() -> None:
        try:
            text = source.readline()
        except OSError:
            # 流被关掉：读到的是 EOF，不是「人说了不」。
            text = ""
        if not loop.is_closed():
            loop.call_soon_threadsafe(_settle, answer, text)

    threading.Thread(target=read, name="approval-ask", daemon=True).start()
    return await answer


class StdinApprovalGate:
    """tty 时提问一次：问题写 stderr，回答读 stdin；非 tty 直接结论「不可问人」。

    不挂起等待，也不默认批准。问题不能写进 stdout：那条流归会话 id 与 `--events jsonl`，
    混进去就不再与日志逐行相等。
    """

    def __init__(
        self,
        *,
        stream: TextIO | None = None,
        prompt_stream: TextIO | None = None,
    ) -> None:
        self._stream = stream
        self._prompt_stream = prompt_stream

    async def request(self, *, tool_call_id: str, tool_name: str, detail: str) -> ApprovalDecision:
        answers = sys.stdin if self._stream is None else self._stream
        if not answers.isatty():
            return "UNAVAILABLE"
        prompt = sys.stderr if self._prompt_stream is None else self._prompt_stream
        prompt.write(f"允许 {tool_name} 改动 {detail}，输入 y 或 n：")
        prompt.flush()
        answer = await _await_readline(answers)
        if answer == "":
            # 读到 EOF：没有人在回答，不是「人说了不」。Windows 上 NUL 设备也算 tty。
            return "UNAVAILABLE"
        return "APPROVED" if answer.strip().lower() in {"y", "yes"} else "DENIED"


STDIN_APPROVAL_GATE = StdinApprovalGate()


def reads_from_records(records: Iterable[EventRecord], workspace: Path) -> dict[str, PriorRead]:
    """「算不算读过」= 这段前缀之前存在针对该路径且 `outcome` 为 `OK` 的 `read`。

    `tool/result` 的 payload 里没有工具名，所以先把 `tool/call` 的名字与入参记下来，
    再按配对结果判定；同一路径后来的成功读覆盖先前的。
    """
    called: dict[str, tuple[str, dict[str, Any]]] = {}
    reads: dict[str, PriorRead] = {}
    for record in records:
        if record.type == "tool/call":
            called[record.payload["tool_call_id"]] = (
                record.payload["name"],
                record.payload["arguments"],
            )
        elif record.type == "tool/result" and record.payload["outcome"] == "OK":
            name, arguments = called.get(record.payload["tool_call_id"], ("", {}))
            file_path = arguments.get("file_path")
            if name != "read" or not isinstance(file_path, str):
                continue
            offset = arguments.get("offset")
            limit = arguments.get("limit")
            content = record.payload["content"]
            reads[path_key(workspace, file_path)] = PriorRead(
                raw_path=file_path,
                offset=offset if isinstance(offset, int) else 1,
                limit=limit if isinstance(limit, int) else None,
                content=content if isinstance(content, str) else "",
            )
    return reads


def judge_fence(context: DispatchContext, *, raw_path: str | None, mutates: bool) -> FenceDecision:
    """三段判定里的围栏段：档位 → 工作区边界 → 要不要问人。

    边界只约束会改动的操作；`danger-full-access` 解除边界，但写前必读与 CAS 不在这里判。
    没有目标路径的会改动工具（`bash`）不受边界轴判定，只受档位轴判定（ADR-0008）。
    """
    if not mutates:
        return FenceDecision(outcome="ALLOWED", raw_path=raw_path)

    if context.sandbox == "read-only":
        target = f"：{raw_path}" if raw_path is not None else ""
        return FenceDecision(
            outcome="DENIED",
            code="SANDBOX_DENIES_WRITE",
            detail=f"{context.sandbox} 档位不许可会改动的操作{target}",
            raw_path=raw_path,
        )

    if raw_path is None:
        # 没有路径可判：边界轴无从生效，档位轴已经放行。
        if context.approval == "ask":
            return FenceDecision(outcome="NEEDS_APPROVAL")
        return FenceDecision(outcome="ALLOWED")

    key = path_key(context.workspace, raw_path)
    if context.sandbox == "workspace-write" and not _is_inside_workspace(context.workspace, key):
        return FenceDecision(
            outcome="DENIED",
            code="OUTSIDE_WORKSPACE",
            detail=f"解析后在工作区之外：{key}",
            path=key,
            raw_path=raw_path,
        )

    if context.approval == "ask":
        return FenceDecision(outcome="NEEDS_APPROVAL", detail=key, path=key, raw_path=raw_path)

    return FenceDecision(outcome="ALLOWED", detail=key, path=key, raw_path=raw_path)
