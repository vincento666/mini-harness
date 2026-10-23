"""seam ⑥：`minihns replay` 黑盒。"""

from __future__ import annotations

import asyncio
import json
import shutil
from pathlib import Path
from typing import Any

from cli_blackbox import _cli
from mini_harness.events import EventLog, EventRecord, read_events
from mini_harness.events.fold import assembled_payload, fold
from mini_harness.provider import FixtureProvider, load_fixture_provider
from paths import (
    COMPACTION_SCENARIO,
    HELLO_SCENARIO,
    READ_THEN_WRITE_SCENARIO,
    TOOL_THEN_DONE_SCENARIO,
    copy_repo_to,
)
from tool_harness import (
    DONE,
    Intervals,
    cancel_after,
    file_registry,
    run_session_fixture,
    timed_registry,
    tool_call,
    turn_entry,
)

_PREFIX = "final_context: "


def _run_once(tmp_path: Path, fixture: str = str(HELLO_SCENARIO)) -> tuple[str, Path]:
    result = _cli("run", "-p", "任务", "--provider", "mock", "--fixture", fixture, cwd=tmp_path)
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


def test_replay_does_not_use_events_after_the_assembly_point(tmp_path: Path) -> None:
    session_id, log_path = _run_once(tmp_path, str(TOOL_THEN_DONE_SCENARIO))
    records = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()]
    request = next(record for record in records if record["type"] == "model/request")
    request["payload"]["tools"] = ["read", "write"]
    log_path.write_text(
        "\n".join(json.dumps(record, ensure_ascii=False) for record in records) + "\n",
        encoding="utf-8",
    )

    replay = _cli("replay", session_id, cwd=tmp_path)

    assert replay.returncode == 0
    assert "REPLAY_MISMATCH" not in replay.stderr


def test_replay_of_a_corrupt_log_is_an_internal_error(tmp_path: Path) -> None:
    session_id, log_path = _run_once(tmp_path)
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write("{not json}\n")

    replay = _cli("replay", session_id, cwd=tmp_path)

    assert replay.returncode == 1
    assert "LOG_UNREADABLE" in replay.stderr


def _run_in_workspace(tmp_path: Path, fixture: Path, *extra: str) -> tuple[str, Path, Path]:
    """在复制出来的 fixture 仓库里跑一次 run，返回 (session_id, 日志路径, 工作区)。"""
    workspace = tmp_path / "ws"
    copy_repo_to(workspace)
    result = _cli(
        "run",
        "-p",
        "任务",
        "--provider",
        "mock",
        "--fixture",
        str(fixture),
        "--workspace",
        str(workspace),
        *extra,
        cwd=tmp_path,
    )
    session_id = result.stdout.strip()
    return session_id, tmp_path / "sessions" / f"{session_id}.jsonl", workspace


def _recorded_seqs(log_path: Path) -> list[int]:
    return [
        json.loads(line)["seq"]
        for line in log_path.read_text(encoding="utf-8").splitlines()
        if json.loads(line)["type"] == "context/assembled"
    ]


def _verified_seqs(stdout: str) -> list[int]:
    return [
        int(line.split("seq=")[1].split(":")[0])
        for line in stdout.splitlines()
        if line.startswith("verified seq=")
    ]


def _snapshot(workspace: Path) -> dict[str, tuple[int, bytes]]:
    return {
        str(path.relative_to(workspace)): (path.stat().st_mtime_ns, path.read_bytes())
        for path in sorted(workspace.rglob("*"))
        if path.is_file()
    }


def test_replay_verifies_a_log_that_carries_approval_and_fence_events(tmp_path: Path) -> None:
    session_id, log_path, _workspace = _run_in_workspace(tmp_path, READ_THEN_WRITE_SCENARIO)
    types = [json.loads(line)["type"] for line in log_path.read_text(encoding="utf-8").splitlines()]
    assert "approval/request" in types
    assert "approval/response" in types
    assert "error/fence" in types

    replay = _cli("replay", session_id, cwd=tmp_path)

    assert replay.returncode == 0
    assert _verified_seqs(replay.stdout) == _recorded_seqs(log_path)


def test_replay_touches_no_file_and_loads_no_provider(tmp_path: Path) -> None:
    fixture_copy = tmp_path / "turns.json"
    shutil.copyfile(READ_THEN_WRITE_SCENARIO, fixture_copy)
    session_id, log_path, workspace = _run_in_workspace(tmp_path, fixture_copy, "--yes")
    assert (workspace / "notes" / "plan.md").read_text(encoding="utf-8") == "重写过的计划\n"

    before = _snapshot(workspace)
    log_before = log_path.read_bytes()
    fixture_copy.unlink()

    replay = _cli("replay", session_id, cwd=tmp_path)

    assert replay.returncode == 0
    assert _snapshot(workspace) == before
    assert log_path.read_bytes() == log_before
    assert "model/request" not in replay.stdout


def test_replay_of_a_half_log_derives_the_closer_without_touching_the_log(tmp_path: Path) -> None:
    """规格 scenario「闭合不被重放成事件」：闭合只在折叠结果里，日志一个字节都不变。

    手搓的半截日志：`call-1` 的 `tool/call` 落了盘却没有结果，之后另有一个回合开始并装配过一次
    上下文——那次装配的结果里带着派生闭合，日志里却没有这样一条记录。
    """
    session_dir = tmp_path / "sessions"
    log = EventLog.create(session_dir, session_id="s-half")
    assert isinstance(log, EventLog)

    def emit(event_type: str, payload: dict[str, Any]) -> EventRecord:
        appended = log.append(event_type, payload)
        assert isinstance(appended, EventRecord)
        return appended

    written: list[EventRecord] = []
    written.append(emit("session/start", {"prompt": "任务", "tools": ["read"]}))
    written.append(emit("turn/start", {"turn_id": "t1"}))
    written.append(emit("context/assembled", assembled_payload("t1", fold(written))))
    written.append(
        emit(
            "model/response",
            {
                "turn_id": "t1",
                "content": "读一个文件",
                "tool_calls": [
                    {"id": "call-1", "name": "read", "arguments": {"file_path": "a.md"}}
                ],
                "finish_reason": "tool_calls",
            },
        )
    )
    written.append(emit("tool/call", {"turn_id": "t1", "tool_call_id": "call-1", "name": "read"}))
    written.append(emit("turn/start", {"turn_id": "t2"}))
    emit("context/assembled", assembled_payload("t2", fold(written)))
    log_before = log.path.read_bytes()

    replay = _cli("replay", "s-half", "--session-dir", str(session_dir), cwd=tmp_path)

    assert replay.returncode == 0
    assert log.path.read_bytes() == log_before
    types = [json.loads(line)["type"] for line in log_before.decode("utf-8").splitlines()]
    assert "tool/result" not in types, "闭合不是事件：日志里没有一条结果记录配这个调用"
    assert "TOOL_OUTCOME_UNKNOWN" in replay.stdout


async def test_a_log_that_ends_in_aborted_replays_without_a_derived_closer(tmp_path: Path) -> None:
    """规格 scenario「取消收尾的日志前缀是完整的」的后半句：那份日志可被逐点重放，读方闭合不出现。

    日志由 seam ① 的一次真实取消 run 产出（不是手搓的），再喂给 seam ⑥ 的 `replay` 黑盒。
    与上一条的分别在那儿：半截日志的折叠要补闭合，重放出来的上下文里就有 `TOOL_OUTCOME_UNKNOWN`；
    取消收尾的日志每条声明过的调用都有配对结果，折叠不需要补，重放也不该出现它。
    """
    session_dir = tmp_path / "sessions"
    (tmp_path / "a.md").write_text("甲\n", encoding="utf-8")
    observed: Intervals = []
    cancel = asyncio.Event()
    watcher = asyncio.create_task(cancel_after(cancel, 0.5))

    _, outcome = await run_session_fixture(
        tmp_path,
        "s-aborted-replay",
        FixtureProvider(
            entries=[
                turn_entry(
                    tool_call("read", "c1", file_path="a.md"),
                    tool_call("write", "c2", file_path="new.md", content="新\n"),
                    tool_call("write", "c3", file_path="other.md", content="新\n"),
                ),
                DONE,
            ]
        ),
        session_dir=session_dir,
        registry=timed_registry(observed, delays={"new.md": 2.0}),
        max_turns=4,
        cancel=cancel,
    )
    await watcher
    assert outcome.stop_reason == "ABORTED"

    log_path = session_dir / "s-aborted-replay.jsonl"
    replay = _cli("replay", "s-aborted-replay", "--session-dir", str(session_dir), cwd=tmp_path)

    assert replay.returncode == 0
    assert _verified_seqs(replay.stdout) == _recorded_seqs(log_path)
    assert "REPLAY_MISMATCH" not in replay.stderr
    records = read_events(log_path)
    assert isinstance(records, list)
    contents = [str(message.content) for message in fold(records).messages]
    assert "TOOL_OUTCOME_UNKNOWN" not in contents


async def test_a_log_that_went_through_compaction_replays_pointwise(tmp_path: Path) -> None:
    """发生过压缩的日志逐点重放：每条 `context/assembled` 都等于它自己前缀的重算结果。

    日志由 seam ① 的一次真 run 产出（窗口 70000：触发线 4364、保留预算 11200），
    遮蔽范围写在 `compaction/summary` 里；重放方只从日志读这条记录，不另算一份。
    """
    session_dir = tmp_path / "sessions"
    # 50000 个字符 ≈ 12500 个估算 token：比保留预算大一倍，所以它该被遮蔽。
    (tmp_path / "long.md").write_text("长" * 50000, encoding="utf-8")

    _, outcome = await run_session_fixture(
        tmp_path,
        "s-compacted",
        load_fixture_provider(COMPACTION_SCENARIO),
        session_dir=session_dir,
        registry=file_registry(),
        max_turns=4,
        window=70000,
        reserve=100,
    )
    assert outcome.stop_reason == "MODEL_COMPLETED"

    log_path = session_dir / "s-compacted.jsonl"
    records = read_events(log_path)
    assert isinstance(records, list)
    assert "compaction/summary" in [record.type for record in records]

    replay = _cli("replay", "s-compacted", "--session-dir", str(session_dir), cwd=tmp_path)

    assert replay.returncode == 0
    assert _verified_seqs(replay.stdout) == _recorded_seqs(log_path)
    assert "REPLAY_MISMATCH" not in replay.stderr
    assert "长" * 50000 not in replay.stdout


async def test_a_log_that_ended_in_overflow_replays_pointwise(tmp_path: Path) -> None:
    """溢出收尾的日志照样逐点重放、退出码 0：收尾是结果，不是把日志弄坏（不变量 A 与 F）。

    窗口 70000 / 预留 100 的压力预算是 69900 个 token：压缩发生一次，摘要自己 75000 个 token，
    压缩之后仍装不下。
    """
    session_dir = tmp_path / "sessions"

    _, outcome = await run_session_fixture(
        tmp_path,
        "s-overflow-replay",
        FixtureProvider(
            entries=[
                {
                    "content": "x" * 100000,
                    "finish_reason": "tool_calls",
                    "tool_calls": [
                        {"id": "c1", "name": "read", "arguments": {"file_path": "a.md"}},
                    ],
                },
                {"content": "y" * 300000, "finish_reason": "stop"},
            ],
        ),
        session_dir=session_dir,
        registry=file_registry(),
        max_turns=3,
        window=70000,
        reserve=100,
    )
    assert outcome.stop_reason == "CONTEXT_WINDOW_EXCEEDED"

    log_path = session_dir / "s-overflow-replay.jsonl"
    records = read_events(log_path)
    assert isinstance(records, list)
    assert [record.type for record in records][-4:] == [
        "error/context",
        "turn/end",
        "segment/end",
        "session/end",
    ]

    replay = _cli("replay", "s-overflow-replay", "--session-dir", str(session_dir), cwd=tmp_path)

    assert replay.returncode == 0
    assert _verified_seqs(replay.stdout) == _recorded_seqs(log_path)
    assert "REPLAY_MISMATCH" not in replay.stderr
