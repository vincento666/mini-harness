"""围栏判定：工作区边界 + `--sandbox` 档位 + 派发上下文。只由 harness 自身判定，不做 OS 级强制。"""

from __future__ import annotations

import asyncio
import os
import sys
import threading
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, Protocol, TextIO

from mini_harness.events.record import EventRecord
from mini_harness.goals import GoalPolicy, GoalSnapshot

if TYPE_CHECKING:
    # 只给类型检查看：运行时导入会绕成 fences → loop → tools.dispatch → fences 的环。
    from mini_harness.loop.settings import ApprovalMode, SandboxLevel, SessionSettings
    from mini_harness.loop.turn_loop import SessionEnv

FenceCode = Literal[
    "OUTSIDE_WORKSPACE",
    "SANDBOX_DENIES_WRITE",
    "SANDBOX_UNAVAILABLE",
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


class QuestionGate(Protocol):
    """问一次普通问题 → 答案文本；问不到人返回 None（M14c）。"""

    async def request(
        self, *, question_id: str, question: str, options: Sequence[str]
    ) -> str | None: ...


class UnavailableQuestionGate:
    """无人值守时的默认门：立即说问不到人，不伪造答案。"""

    async def request(
        self, *, question_id: str, question: str, options: Sequence[str]
    ) -> str | None:
        return None


UNAVAILABLE_QUESTION_GATE: QuestionGate = UnavailableQuestionGate()


@dataclass(frozen=True)
class DispatchContext:
    """一次派发能看到的全部事实：工具只读它，不读进程内状态。

    `session` 是委派要的那一层（子会话需要父的日志、设置、注册表与 provider）；
    `tool_call_id` 是这一次调用的身份，子会话的 `session/start` 靠它跟父结果对上。
    父段取消不经过这里：它到达工具的方式是 `CancelledError`（ADR-0007）。
    """

    workspace: Path
    sandbox: SandboxLevel
    approval: ApprovalMode
    reads: Mapping[str, PriorRead] = field(default_factory=dict)
    session: SessionEnv | None = None
    tool_call_id: str | None = None
    # 计划模式（M14c）：派发前拦写类工具；由回合循环按日志算好传进来。
    plan_active: bool = False
    question_gate: QuestionGate = UNAVAILABLE_QUESTION_GATE
    # 目标轮次策略（M13）：`todo` 的并行纪律读它；缺省即部署默认。
    goal_policy: GoalPolicy = field(default_factory=GoalPolicy)
    # 目标快照（M13）：派发前按日志折好传进来，工具不自己读日志。
    goal: GoalSnapshot | None = None
    # 待办表的当前值（`todos` 投影）：`get_todos` 读它；同一批共用一个前缀，
    # 所以同批里前一条 `todo` 的整表在这条里还看不到。
    todos: Sequence[Mapping[str, Any]] = ()
    # 本段是否由人类来源开启；goal 轮次里不能创建/改写目标（M13 权威）。
    human_driven: bool = True
    # 会话入口：子会话没有目标权威。取值与 `SessionEntry` 一致。
    entry: str = "chat"

    @classmethod
    def from_settings(
        cls,
        settings: SessionSettings,
        *,
        reads: Mapping[str, PriorRead] | None = None,
        session: SessionEnv | None = None,
        plan_active: bool = False,
        question_gate: QuestionGate | None = None,
        goal: GoalSnapshot | None = None,
        todos: Sequence[Mapping[str, Any]] = (),
        human_driven: bool = True,
        entry: str = "chat",
    ) -> DispatchContext:
        return cls(
            workspace=settings.workspace,
            sandbox=settings.sandbox,
            approval=settings.approval,
            reads=reads or {},
            session=session,
            plan_active=plan_active,
            question_gate=UNAVAILABLE_QUESTION_GATE if question_gate is None else question_gate,
            goal_policy=settings.goal,
            goal=goal,
            todos=todos,
            human_driven=human_driven,
            entry=entry,
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


class StdinQuestionGate:
    """tty 上问一个普通问题；非 tty 立即「问不到人」。

    不做定时器：超时后 `input()` 线程仍会消费下一行，把下一条输入吃掉。
    无人值守由非 tty 覆盖；人走开时用 Ctrl-C 取消这一次调用。
    """

    def __init__(
        self, *, stream: TextIO | None = None, prompt_stream: TextIO | None = None
    ) -> None:
        self._stream = stream
        self._prompt_stream = prompt_stream

    async def request(
        self, *, question_id: str, question: str, options: Sequence[str]
    ) -> str | None:
        answers = sys.stdin if self._stream is None else self._stream
        if not answers.isatty():
            return None
        prompt = sys.stderr if self._prompt_stream is None else self._prompt_stream
        suffix = f"（{'/'.join(options)}）" if options else ""
        prompt.write(f"\n问题：{question}{suffix}\n> ")
        prompt.flush()
        answer = await _await_readline(answers)
        if answer == "":
            return None
        return answer.strip() or None


STDIN_QUESTION_GATE: QuestionGate = StdinQuestionGate()


class UnavailableApprovalGate:
    """子代理的 approval 门：问人一律「不可用」，不继承父的放行（M12 design D4）。"""

    async def request(self, *, tool_call_id: str, tool_name: str, detail: str) -> ApprovalDecision:
        return "UNAVAILABLE"


UNAVAILABLE_APPROVAL_GATE = UnavailableApprovalGate()


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
