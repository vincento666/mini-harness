"""seam ③：`bash` 的执行契约——档位拒绝、cwd 固定工作区根、超时入参的数值边界。"""

from __future__ import annotations

import asyncio
from pathlib import Path

from mini_harness.events import read_events
from mini_harness.tools import ToolRegistry
from mini_harness.tools.bash_tools import OUTPUT_LIMIT_BYTES, TRUNCATION_MARK, bash_tool_definitions
from mini_harness.tools.fences import ApprovalDecision
from mini_harness.tools.file_tools import file_tool_definitions
from tool_harness import DONE, dispatch_call, run_fixture_session, tool_call_entry

_MARKER = "open('made.md', 'w').close()\n"

_TICKER = (
    "import time\n\n"
    "with open('ticking.txt', 'a', encoding='utf-8') as handle:\n"
    "    for _ in range(200):\n"
    "        handle.write('tick\\n')\n"
    "        handle.flush()\n"
    "        time.sleep(0.2)\n"
)

_SPAWNS_CHILD = (
    "import subprocess\nimport sys\nimport time\n\n"
    "subprocess.Popen(\n"
    "    [sys.executable, 'child.py'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL\n"
    ")\n"
    "time.sleep(30)\n"
)


class _RecordingGate:
    """记下提问里展示了什么：`bash` 的关键参数是命令本身。"""

    def __init__(self) -> None:
        self.details: list[str] = []

    def request(self, *, tool_name: str, detail: str) -> ApprovalDecision:
        self.details.append(detail)
        return "DENIED"


def _registry() -> ToolRegistry:
    """六个工具的注册表：`bash` 与五个文件工具同批。"""
    return ToolRegistry([*file_tool_definitions(), *bash_tool_definitions()])


def _script(workspace: Path, name: str, body: str) -> str:
    """把一段 Python 落成工作区里的脚本，返回给模型的命令。

    两端的判据只依赖 `python <文件>`：`-c` 的引号在 `cmd.exe` 与 `/bin/sh` 里语义不同，
    用它判到的就不是工具契约而是 shell 方言。
    """
    (workspace / name).write_text(body, encoding="utf-8")
    return f"python {name}"


async def test_read_only_denies_bash_and_the_command_never_runs(tmp_path: Path) -> None:
    command = _script(tmp_path, "make_marker.py", _MARKER)
    outcome = await dispatch_call(
        tmp_path, "bash", {"command": command}, sandbox="read-only", registry=_registry()
    )

    assert outcome.result.outcome == "DENIED_BY_FENCE"
    assert outcome.fence_code == "SANDBOX_DENIES_WRITE"
    assert outcome.path is None
    assert outcome.raw_path is None
    assert not (tmp_path / "made.md").exists()


async def test_read_only_bash_ends_the_run_with_a_fence_record(tmp_path: Path) -> None:
    command = _script(tmp_path, "make_marker.py", _MARKER)
    log, outcome = await run_fixture_session(
        tmp_path,
        "s-bash-read-only",
        [tool_call_entry("bash", "c1", command=command), DONE],
        sandbox="read-only",
        registry=_registry(),
    )

    fence = next(record for record in read_events(log.path) if record.type == "error/fence")
    assert fence.payload["code"] == "SANDBOX_DENIES_WRITE"
    assert fence.payload["path"] is None
    assert fence.payload["raw_path"] is None
    assert outcome.stop_reason == "FENCE_DENIED"
    assert not (tmp_path / "made.md").exists()


async def test_the_command_runs_in_the_workspace_root(tmp_path: Path) -> None:
    command = _script(tmp_path, "make_marker.py", _MARKER)
    outcome = await dispatch_call(tmp_path, "bash", {"command": command}, registry=_registry())

    assert outcome.result.outcome == "OK"
    assert (tmp_path / "made.md").exists()

    read_back = await dispatch_call(
        tmp_path, "read", {"file_path": "made.md"}, registry=_registry()
    )
    assert read_back.result.outcome == "OK"


async def test_timeout_seconds_above_the_cap_is_an_invalid_args_result(tmp_path: Path) -> None:
    command = _script(tmp_path, "make_marker.py", _MARKER)
    outcome = await dispatch_call(
        tmp_path,
        "bash",
        {"command": command, "timeout_seconds": 601},
        registry=_registry(),
    )

    assert outcome.result.outcome == "TOOL_ARGS_INVALID"
    assert not (tmp_path / "made.md").exists()


async def test_timeout_seconds_must_be_positive(tmp_path: Path) -> None:
    command = _script(tmp_path, "make_marker.py", _MARKER)
    outcome = await dispatch_call(
        tmp_path, "bash", {"command": command, "timeout_seconds": 0}, registry=_registry()
    )

    assert outcome.result.outcome == "TOOL_ARGS_INVALID"
    assert not (tmp_path / "made.md").exists()


async def test_the_approval_question_for_bash_shows_the_command(tmp_path: Path) -> None:
    command = _script(tmp_path, "make_marker.py", _MARKER)
    gate = _RecordingGate()
    outcome = await dispatch_call(
        tmp_path,
        "bash",
        {"command": command},
        approval="ask",
        registry=_registry(),
        approval_gate=gate,
    )

    assert outcome.result.outcome == "DENIED_BY_APPROVAL"
    assert gate.details == [command]
    assert not (tmp_path / "made.md").exists()


async def test_a_failing_command_is_ok_with_its_exit_code_in_the_content(tmp_path: Path) -> None:
    command = _script(
        tmp_path,
        "fail.py",
        "import sys\n\nprint('boom on stderr', file=sys.stderr)\nsys.exit(1)\n",
    )
    outcome = await dispatch_call(tmp_path, "bash", {"command": command}, registry=_registry())

    assert outcome.result.outcome == "OK"
    assert outcome.result.content.startswith("退出码 1")
    assert "boom on stderr" in outcome.result.content


async def test_oversized_output_is_truncated_and_marked(tmp_path: Path) -> None:
    chatter = "for index in range(4000):\n    print('x' * 40, index)\n"
    command = _script(tmp_path, "chatter.py", chatter)
    outcome = await dispatch_call(tmp_path, "bash", {"command": command}, registry=_registry())

    assert outcome.result.outcome == "OK"
    assert TRUNCATION_MARK in outcome.result.content
    assert OUTPUT_LIMIT_BYTES == 16 * 1024
    limit = OUTPUT_LIMIT_BYTES + len(TRUNCATION_MARK.encode("utf-8"))
    assert len(outcome.result.content.encode("utf-8")) <= limit


async def test_a_timed_out_command_leaves_no_descendant_still_writing(tmp_path: Path) -> None:
    """判据只看后果：超时之后那个后代进程不再往工作区写。终止手段是实现细节。"""
    _script(tmp_path, "child.py", _TICKER)
    command = _script(tmp_path, "parent.py", _SPAWNS_CHILD)

    outcome = await dispatch_call(
        tmp_path, "bash", {"command": command, "timeout_seconds": 2}, registry=_registry()
    )

    assert outcome.result.outcome == "TOOL_TIMEOUT"
    ticking = tmp_path / "ticking.txt"
    first = ticking.read_text(encoding="utf-8")
    await asyncio.sleep(1.5)
    assert ticking.read_text(encoding="utf-8") == first
