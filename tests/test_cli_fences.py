"""seam ⑥：围栏与 approval 的 CLI 黑盒——退出码、stderr、日志三处必须一致。"""

from __future__ import annotations

import json
from pathlib import Path

from cli_blackbox import _cli
from paths import (
    EDIT_FIVE_MD_SCENARIO,
    HELLO_SCENARIO,
    READ_THEN_WRITE_SCENARIO,
    TOOL_THEN_EXHAUST_SCENARIO,
    WRITE_OUTSIDE_SCENARIO,
    copy_repo_to,
)

_REVIEWED = "（已复核）"
_FIVE_MD = ["README.md", "notes/plan.md", "notes/meeting.md", "notes/retro.md", "notes/spec.md"]


class _Run:
    def __init__(
        self,
        name: str,
        fixture: Path,
        tmp_path: Path,
        *extra: str,
        stdin_text: str | None = None,
    ) -> None:
        root = tmp_path / name
        self.workspace = root / "ws"
        copy_repo_to(self.workspace)
        result = _cli(
            "run",
            "-p",
            "任务",
            "--provider",
            "mock",
            "--fixture",
            str(fixture),
            "--workspace",
            str(self.workspace),
            "--session-dir",
            str(root / "sessions"),
            *extra,
            cwd=tmp_path,
            stdin_text=stdin_text,
        )
        self.code = result.returncode
        self.stdout = result.stdout
        self.stderr = result.stderr
        files = sorted((root / "sessions").glob("*.jsonl"))
        self.events: list[dict[str, object]] = []
        if files:
            self.events = [
                json.loads(line) for line in files[0].read_text(encoding="utf-8").splitlines()
            ]

    def fence_codes(self) -> list[str]:
        return [
            str(event["payload"]["code"]) for event in self.events if event["type"] == "error/fence"
        ]

    def outcomes(self) -> list[str]:
        results = [event for event in self.events if event["type"] == "tool/result"]
        return [str(event["payload"]["outcome"]) for event in results]

    def asked(self) -> bool:
        return any(str(event["type"]).startswith("approval/") for event in self.events)


def test_yes_approves_every_edit_in_the_fixture_repo(tmp_path: Path) -> None:
    run = _Run("yes", EDIT_FIVE_MD_SCENARIO, tmp_path, "--yes", "--max-turns", "12")

    assert run.code == 0
    assert all(_REVIEWED in (run.workspace / name).read_text(encoding="utf-8") for name in _FIVE_MD)
    assert [event["type"] for event in run.events].count("tool/call") == 10
    assert run.outcomes() == ["OK"] * 10
    assert run.asked() is False


def test_a_write_outside_the_workspace_ends_with_code_three(tmp_path: Path) -> None:
    run = _Run("outside", WRITE_OUTSIDE_SCENARIO, tmp_path, "--yes")

    assert run.code == 3
    assert "outside.md" in run.stderr
    assert run.fence_codes() == ["OUTSIDE_WORKSPACE"]
    assert run.outcomes() == ["DENIED_BY_FENCE"]
    assert not (tmp_path / "outside.md").exists()


def test_a_write_with_no_human_to_ask_ends_with_code_three(tmp_path: Path) -> None:
    run = _Run("ask", READ_THEN_WRITE_SCENARIO, tmp_path)

    assert run.code == 3
    assert "APPROVAL_UNAVAILABLE" in run.stderr
    assert run.fence_codes() == ["APPROVAL_UNAVAILABLE"]
    assert run.outcomes() == ["OK", "DENIED_BY_APPROVAL"]
    decisions = [
        str(event["payload"]["decision"])
        for event in run.events
        if event["type"] == "approval/response"
    ]
    assert decisions == ["UNAVAILABLE"]


def test_answers_piped_into_stdin_are_not_a_human_to_ask(tmp_path: Path) -> None:
    """seam ②⑥：tty 检测在两端同形——管道里喂进来的 `y` 不是人。

    stdin 是管道就不是 tty，没有人可问：门给 `UNAVAILABLE`、写被拒、退出码 3。
    把管道里的 `y` 当成批准等于让任何能写 stdin 的东西替人点头，两端都不成立。
    """
    run = _Run("piped", READ_THEN_WRITE_SCENARIO, tmp_path, stdin_text="y\n")

    assert run.code == 3
    assert run.outcomes() == ["OK", "DENIED_BY_APPROVAL"]
    decisions = [
        str(event["payload"]["decision"])
        for event in run.events
        if event["type"] == "approval/response"
    ]
    assert decisions == ["UNAVAILABLE"]
    assert "重写过的计划" not in (run.workspace / "notes" / "plan.md").read_text(encoding="utf-8")


def test_yes_does_not_relax_the_read_only_level(tmp_path: Path) -> None:
    run = _Run("readonly", READ_THEN_WRITE_SCENARIO, tmp_path, "--sandbox", "read-only", "--yes")

    assert run.code == 3
    assert run.fence_codes() == ["SANDBOX_DENIES_WRITE"]
    assert run.asked() is False
    assert run.outcomes() == ["OK", "DENIED_BY_FENCE"]


def test_no_run_exits_with_the_reserved_four(tmp_path: Path) -> None:
    cases = [
        _Run("ok", HELLO_SCENARIO, tmp_path),
        _Run("edited", EDIT_FIVE_MD_SCENARIO, tmp_path, "--yes", "--max-turns", "12"),
        _Run("asked", READ_THEN_WRITE_SCENARIO, tmp_path),
        _Run("outside", WRITE_OUTSIDE_SCENARIO, tmp_path, "--yes"),
        _Run("readonly", READ_THEN_WRITE_SCENARIO, tmp_path, "--sandbox", "read-only", "--yes"),
        _Run("exhaust", TOOL_THEN_EXHAUST_SCENARIO, tmp_path),
    ]

    codes = [case.code for case in cases]
    assert codes == [0, 0, 3, 3, 3, 1]
    assert all(code != 4 for code in codes)

    for case in cases:
        if case.code == 2:
            continue
        if case.code != 0:
            assert any(str(event["type"]).startswith("error/") for event in case.events)


def test_events_jsonl_stdout_equals_the_log_line_by_line(tmp_path: Path) -> None:
    run = _Run("jsonl", READ_THEN_WRITE_SCENARIO, tmp_path, "--events", "jsonl")

    printed = [json.loads(line) for line in run.stdout.splitlines() if line.strip()]
    assert run.code == 3
    assert printed == run.events
    assert any(str(event["type"]) == "approval/request" for event in printed)
    assert any(str(event["type"]) == "error/fence" for event in printed)
