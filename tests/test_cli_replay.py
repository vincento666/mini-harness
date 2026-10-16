"""seam ⑥：`minihns replay` 黑盒。"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from paths import HELLO_SCENARIO, TOOL_THEN_DONE_SCENARIO

_PREFIX = "final_context: "


def _cli(*args: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "mini_harness.cli.main", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def _run_once(tmp_path: Path, fixture: str = str(HELLO_SCENARIO)) -> tuple[str, Path]:
    result = _cli(
        "run", "-p", "任务", "--provider", "mock", "--fixture", fixture, cwd=tmp_path
    )
    session_id = result.stdout.strip()
    return session_id, tmp_path / "sessions" / f"{session_id}.jsonl"


def _recorded_contexts(log_path: Path) -> list[dict[str, object]]:
    return [
        json.loads(line)["payload"]
        for line in log_path.read_text(encoding="utf-8").splitlines()
        if json.loads(line)["type"] == "context/assembled"
    ]


def _printed_context(stdout: str) -> dict[str, object]:
    lines = [line for line in stdout.splitlines() if line.startswith(_PREFIX)]
    assert lines
    return json.loads(lines[-1][len(_PREFIX) :])


def test_replay_final_context_matches_the_recorded_context_assembled(tmp_path: Path) -> None:
    session_id, log_path = _run_once(tmp_path)
    recorded = _recorded_contexts(log_path)[-1]

    replay = _cli("replay", session_id, cwd=tmp_path)

    assert replay.returncode == 0
    assert _printed_context(replay.stdout) == recorded
    assert "model/request" not in replay.stdout


def test_replay_of_an_unknown_session_id_names_the_path_it_looked_for(tmp_path: Path) -> None:
    session_dir = tmp_path / "sessions"

    replay = _cli("replay", "does-not-exist", "--session-dir", str(session_dir), cwd=tmp_path)

    assert replay.returncode == 2
    assert "SESSION_NOT_FOUND" in replay.stderr
    assert str(session_dir) in replay.stderr


def test_replay_twice_leaves_the_log_bytes_untouched(tmp_path: Path) -> None:
    session_id, log_path = _run_once(tmp_path)
    before = log_path.read_bytes()

    _cli("replay", session_id, cwd=tmp_path)
    _cli("replay", session_id, cwd=tmp_path)

    assert log_path.read_bytes() == before


def test_replay_recomputes_and_verifies_every_assembly_point(tmp_path: Path) -> None:
    session_id, log_path = _run_once(tmp_path, str(TOOL_THEN_DONE_SCENARIO))
    recorded_seqs = [
        json.loads(line)["seq"]
        for line in log_path.read_text(encoding="utf-8").splitlines()
        if json.loads(line)["type"] == "context/assembled"
    ]
    assert len(recorded_seqs) == 2

    replay = _cli("replay", session_id, cwd=tmp_path)

    verified = [
        int(line.split("seq=")[1].split(":")[0])
        for line in replay.stdout.splitlines()
        if line.startswith("verified seq=")
    ]
    assert replay.returncode == 0
    assert verified == recorded_seqs


def test_replay_reports_a_mismatched_assembly_point_and_leaves_the_log_alone(
    tmp_path: Path,
) -> None:
    session_id, log_path = _run_once(tmp_path, str(TOOL_THEN_DONE_SCENARIO))
    records = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()]
    target = next(record for record in records if record["type"] == "context/assembled")
    tampered_seq = target["seq"]
    target["payload"]["messages"] = [{"role": "user", "content": "被篡改"}]
    log_path.write_text(
        "\n".join(json.dumps(record, ensure_ascii=False) for record in records) + "\n",
        encoding="utf-8",
    )
    before = log_path.read_bytes()

    replay = _cli("replay", session_id, cwd=tmp_path)

    assert replay.returncode == 1
    assert "error/replay" in replay.stderr
    assert "REPLAY_MISMATCH" in replay.stderr
    assert str(tampered_seq) in replay.stderr
    assert log_path.read_bytes() == before


def test_replay_of_a_corrupt_log_is_an_internal_error(tmp_path: Path) -> None:
    session_id, log_path = _run_once(tmp_path)
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write("{not json}\n")

    replay = _cli("replay", session_id, cwd=tmp_path)

    assert replay.returncode == 1
    assert "LOG_UNREADABLE" in replay.stderr
