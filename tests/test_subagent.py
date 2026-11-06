"""seam ⑦：委派。子会话的日志与父会话的那一对 tool 记录是这一缝的中心。"""

from __future__ import annotations

import asyncio
from pathlib import Path

from mini_harness.events import read_events
from mini_harness.loop import RunOutcome
from mini_harness.provider import FixtureProvider
from mini_harness.tools import ToolRegistry
from mini_harness.tools.bash_tools import bash_tool_definitions
from mini_harness.tools.fences import ApprovalDecision
from mini_harness.tools.file_tools import file_tool_definitions
from mini_harness.tools.subagent import subagent_tool_definitions
from tool_harness import (
    DONE,
    build_session_env,
    dispatch_call,
    run_fixture_session,
    tool_call_entry,
)


def delegation_registry() -> ToolRegistry:
    """父会话的工具表：五个文件工具、`bash` 与 `subagent`。"""
    return ToolRegistry(
        [*file_tool_definitions(), *bash_tool_definitions(), *subagent_tool_definitions()]
    )


async def _run(tmp_path: Path, entries: list[dict[str, object]]) -> tuple[Path, RunOutcome]:
    log, outcome = await run_fixture_session(
        tmp_path, "s-parent", entries, registry=delegation_registry(), prompt="父任务"
    )
    return log.path, outcome


def _child_paths(tmp_path: Path) -> list[Path]:
    return [path for path in sorted(tmp_path.glob("*.jsonl")) if path.stem != "s-parent"]


async def test_subagent_writes_its_own_log(tmp_path: Path) -> None:
    """子会话从空对话起步：自己的 `session/start` 带 entry / parent_session_id / depth。"""
    entries = [
        tool_call_entry("subagent", "c1", task="读 a.md 并总结"),
        {"content": "子会话的最终答案", "finish_reason": "stop"},
        DONE,
    ]

    _, outcome = await _run(tmp_path, entries)

    assert outcome.stop_reason == "MODEL_COMPLETED"
    children = _child_paths(tmp_path)
    assert len(children) == 1
    start = read_events(children[0])[0]
    assert start.type == "session/start"
    assert start.payload["entry"] == "subagent"
    assert start.payload["parent_session_id"] == "s-parent"
    assert start.payload["parent_tool_call_id"] == "c1"
    assert start.payload["depth"] == 1
    # spawn 不 fork：子会话的第一条内容就是它的任务，没有父会话的历史。
    messages = read_events(children[0])
    assert [record.type for record in messages[:3]] == [
        "session/start",
        "segment/start",
        "turn/start",
    ]


async def test_parent_log_has_only_the_tool_pair(tmp_path: Path) -> None:
    """子会话内部调了工具、调了两次模型，父日志里仍只有一对 subagent 记录。"""
    (tmp_path / "a.md").write_text("内容\n", encoding="utf-8")
    entries = [
        tool_call_entry("subagent", "c1", task="读 a.md 并总结"),
        tool_call_entry("read", "c2", file_path="a.md"),
        {"content": "子会话读完了 a.md", "finish_reason": "stop"},
        DONE,
    ]

    log_path, outcome = await _run(tmp_path, entries)

    assert outcome.stop_reason == "MODEL_COMPLETED"
    records = read_events(log_path)
    assert [record.payload["name"] for record in records if record.type == "tool/call"] == [
        "subagent"
    ]
    assert len([record for record in records if record.type == "tool/result"]) == 1
    assert not any(record.type == "session/start" for record in records[1:])
    # 子会话的模型回复与工具过程都在它自己的日志里。
    child = read_events(_child_paths(tmp_path)[0])
    assert [record.payload["name"] for record in child if record.type == "tool/call"] == ["read"]


async def test_subagent_result_is_the_final_text_not_the_child_log(tmp_path: Path) -> None:
    """父上下文只装子会话的最终文本：不是 JSONL、不是子会话的完整过程。"""
    (tmp_path / "a.md").write_text("内容\n", encoding="utf-8")
    entries = [
        tool_call_entry("subagent", "c1", task="读 a.md 并总结"),
        tool_call_entry("read", "c2", file_path="a.md"),
        {"content": "子会话的结论：内容两个字", "finish_reason": "stop"},
        DONE,
    ]

    log_path, _ = await _run(tmp_path, entries)

    result = next(record for record in read_events(log_path) if record.type == "tool/result")
    assert result.payload["content"] == "子会话的结论：内容两个字"
    assert "session/start" not in str(result.payload["content"])
    assert "tool_call_id" not in str(result.payload["content"])


async def test_child_session_context_is_empty_but_for_the_task(tmp_path: Path) -> None:
    """子会话的上下文只有受保护头部加任务本身：父会话的历史一个字都不进去。"""
    entries = [
        tool_call_entry("subagent", "c1", task="只做这一件事"),
        {"content": "收到", "finish_reason": "stop"},
        DONE,
    ]

    await _run(tmp_path, entries)

    child = read_events(_child_paths(tmp_path)[0])
    assembled = next(record for record in child if record.type == "context/assembled")
    roles = [message["role"] for message in assembled.payload["messages"]]
    assert roles == ["system", "user"]
    assert "父任务" not in str(assembled.payload["messages"])
    assert assembled.payload["messages"][-1]["content"] == "只做这一件事"


async def test_depth_exceeded_is_a_result(tmp_path: Path) -> None:
    """`maxDepth = 1`：子代理（depth 1）再派子代理得到结果词，父回合继续（design D3）。"""
    entries = [
        tool_call_entry("subagent", "c1", task="先派一个子代理"),
        tool_call_entry("subagent", "c2", task="子代理又想派子代理"),
        {"content": "我不该派子代理", "finish_reason": "stop"},
        DONE,
    ]

    _, outcome = await _run(tmp_path, entries)

    assert outcome.stop_reason == "MODEL_COMPLETED"
    child = read_events(_child_paths(tmp_path)[0])
    results = [record.payload for record in child if record.type == "tool/result"]
    assert [result["outcome"] for result in results] == ["DEPTH_EXCEEDED"]
    # 被拒的那次没有建出孙会话：目录里只有父子两份日志。
    assert len(_child_paths(tmp_path)) == 1


async def test_activation_limit_is_a_result(tmp_path: Path) -> None:
    """每父会话 8 个活跃子代理：额度用完时是结果词，不是异常（design D3）。"""
    _, env = build_session_env(tmp_path, "s-parent", FixtureProvider(entries=[]))
    env.delegation.active = env.delegation.max_active

    outcome = await dispatch_call(
        tmp_path,
        "subagent",
        {"task": "再来一个"},
        registry=delegation_registry(),
        session=env,
        cancel=asyncio.Event(),
    )

    assert outcome.result.outcome == "ACTIVATION_LIMIT_REACHED"
    assert str(env.delegation.max_active) in outcome.result.content
    # 被拒的调用既不动额度，也不建子日志。
    assert env.delegation.active == env.delegation.max_active
    assert [path.name for path in tmp_path.glob("*.jsonl")] == ["s-parent.jsonl"]


class _RecordingGate:
    """父会话的问人门：一律批准，并记下被问过哪些工具。"""

    def __init__(self) -> None:
        self.asked: list[str] = []

    async def request(self, *, tool_call_id: str, tool_name: str, detail: str) -> ApprovalDecision:
        self.asked.append(tool_name)
        return "APPROVED"


async def test_a_child_approval_is_unavailable(tmp_path: Path) -> None:
    """子会话问人得到 UNAVAILABLE：不继承父的一次性放行，也不等父代答（design D4）。"""
    entries = [
        tool_call_entry("subagent", "c1", task="改一个文件"),
        tool_call_entry("write", "c2", file_path="out.md", content="写进去\n"),
        DONE,
    ]

    gate = _RecordingGate()
    log, outcome = await run_fixture_session(
        tmp_path,
        "s-parent",
        entries,
        registry=delegation_registry(),
        prompt="父任务",
        approval="ask",
        approval_gate=gate,
    )

    assert outcome.stop_reason == "MODEL_COMPLETED"
    child = read_events(_child_paths(tmp_path)[0])
    assert [record.payload["outcome"] for record in child if record.type == "tool/result"] == [
        "DENIED_BY_APPROVAL"
    ]
    fence = next(record for record in child if record.type == "error/fence")
    assert fence.payload["code"] == "APPROVAL_UNAVAILABLE"
    assert not (tmp_path / "out.md").exists()
    # 子会话的提问没有转给父会话的问人门：父一次都没被问过。
    assert gate.asked == []
    # 子会话被拒也是父的结果：父回合继续，父日志那一条是 OK。
    parent_result = next(record for record in read_events(log.path) if record.type == "tool/result")
    assert parent_result.payload["outcome"] == "OK"
