"""seam ⑥：runner 不可用时的真实子进程退出码与 fence 记录。"""

from __future__ import annotations

import json
import subprocess
import sys
import textwrap
from pathlib import Path

from mini_harness.events import read_events


def test_unavailable_runner_exits_3_in_a_real_subprocess(tmp_path: Path) -> None:
    fixture = tmp_path / "turns.json"
    fixture.write_text(
        json.dumps(
            [
                {
                    "content": "",
                    "finish_reason": "tool_calls",
                    "tool_calls": [
                        {"id": "c1", "name": "bash", "arguments": {"command": "echo hi"}}
                    ],
                },
                {"content": "done", "finish_reason": "stop"},
            ]
        ),
        encoding="utf-8",
    )
    driver = textwrap.dedent(
        f"""
        import sys
        from mini_harness.tools import ToolRegistry
        from mini_harness.tools.bash_tools import bash_tool_definitions
        from mini_harness.tools.command_runner import SandboxUnavailable
        from mini_harness.tools.file_tools import file_tool_definitions
        import mini_harness.session.assembly as assembly

        class Unavailable:
            platform = "test"
            async def run(self, command, *, cwd, timeout_seconds):
                raise SandboxUnavailable("no runner")

        def build_registry(*args, **kwargs):
            return ToolRegistry([
                *file_tool_definitions(),
                *bash_tool_definitions(runner=Unavailable()),
            ])

        assembly.build_registry = build_registry
        from mini_harness.cli.main import main
        sys.exit(main(["run", "-p", "任务", "--provider", "mock",
                       "--fixture", {str(fixture)!r},
                       "--session-dir", {str(tmp_path / "sessions")!r},
                       "--yes"]))
        """
    )

    result = subprocess.run(
        [sys.executable, "-c", driver],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
    )

    assert result.returncode == 3, result.stderr
    logs = list((tmp_path / "sessions").glob("*.jsonl"))
    assert logs
    records = read_events(logs[0])
    assert isinstance(records, list)
    fences = [record for record in records if record.type == "error/fence"]
    assert fences
    assert fences[0].payload["code"] == "SANDBOX_UNAVAILABLE"
