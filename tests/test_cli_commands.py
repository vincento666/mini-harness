"""seam ⑥：host 的命令面（M14）——与 CLI 同一份清单/正文，不开段。"""

from __future__ import annotations

import json
import time
from pathlib import Path

import httpx

from test_cli_host import (
    HOST_TOKEN,
    _create_session,
    _free_port,
    _headers,
    _mock_fixture,
    _slow_fixture,
    _start_host,
    _stop,
    _wait_for_health,
    _wait_for_log,
    _wait_until_idle,
)


def _write_skill(workspace: Path) -> None:
    directory = workspace / ".minihns" / "skills" / "tdd"
    directory.mkdir(parents=True)
    (directory / "SKILL.md").write_text(
        "---\nname: tdd\ndescription: 先写判据\n---\n\n第一步：写红判据\n", encoding="utf-8"
    )


def test_host_commands_match_the_cli_and_open_a_segment_for_skills(tmp_path: Path) -> None:
    session_dir = tmp_path / "sessions"
    workspace = tmp_path / "workspace"
    _write_skill(workspace)
    port = _free_port()
    process = _start_host(tmp_path, port, HOST_TOKEN, "--session-dir", str(session_dir))
    try:
        _wait_for_health(port)
        with httpx.Client(
            trust_env=False, base_url=f"http://127.0.0.1:{port}", timeout=10.0
        ) as client:
            session_id = _create_session(client, workspace, _mock_fixture(tmp_path))

            commands = client.get("/commands", headers=_headers()).json()["commands"]
            assert {command["name"] for command in commands} >= {"skills", "skill"}
            # 不带会话时只有内置命令：技能是会话级发现，不该泄漏成进程级清单。
            assert "tdd" not in {command["name"] for command in commands}

            session_commands = client.get(
                f"/commands?session_id={session_id}", headers=_headers()
            ).json()["commands"]
            assert "tdd" in {command["name"] for command in session_commands}

            listed = client.post(
                f"/sessions/{session_id}/commands",
                headers=_headers(),
                json={"name": "skills"},
            )
            assert listed.status_code == 200, listed.text
            assert "tdd" in listed.json()["output"]

            loaded = client.post(
                f"/sessions/{session_id}/commands",
                headers=_headers(),
                json={"name": "skill", "arguments": "tdd"},
            )
            assert loaded.status_code == 200, loaded.text
            assert "第一步：写红判据" in loaded.json()["output"]

            direct = client.post(
                f"/sessions/{session_id}/commands",
                headers=_headers(),
                json={"name": "tdd"},
            )
            assert direct.status_code == 202, direct.text
            assert direct.json()["queued"] is False
            _wait_until_idle(client, session_id)

            expanded = client.post(
                f"/sessions/{session_id}/commands",
                headers=_headers(),
                json={"name": "tdd", "arguments": "帮我改个函数"},
            )
            assert expanded.status_code == 202, expanded.text
            assert expanded.json()["queued"] is False
            log = session_dir / f"{session_id}.jsonl"
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline:
                if '"user/message"' in log.read_text(encoding="utf-8"):
                    break
                time.sleep(0.05)
            text = log.read_text(encoding="utf-8")
            users = [
                record["payload"]
                for record in map(json.loads, text.splitlines())
                if record["type"] == "user/message"
            ]
            assert "第一步：写红判据" in users[0]["content"]
            assert "请按技能执行" in users[0]["content"]
            assert "帮我改个函数" in users[-1]["content"]

            unknown = client.post(
                f"/sessions/{session_id}/commands",
                headers=_headers(),
                json={"name": "nope"},
            )
            assert unknown.status_code == 400

            bad_argument = client.post(
                f"/sessions/{session_id}/commands",
                headers=_headers(),
                json={"name": "skill", "arguments": "ghost"},
            )
            assert bad_argument.status_code == 200
            assert bad_argument.json()["ok"] is False

            log = session_dir / f"{session_id}.jsonl"
            text = log.read_text(encoding="utf-8")
            assert text.count('"command/run"') == 5
            assert text.count('"command/done"') == 5
            # 两条技能命令各展开成一个段；其余命令都不开段。
            assert text.count('"segment/start"') == 2
    finally:
        _stop(process)


def test_the_host_command_face_sees_a_skill_added_mid_session(tmp_path: Path) -> None:
    """命令面读注册表快照：会话建立之后写进去的技能，下一条命令就能看见。"""
    session_dir = tmp_path / "sessions"
    workspace = tmp_path / "workspace"
    _write_skill(workspace)
    port = _free_port()
    process = _start_host(tmp_path, port, HOST_TOKEN, "--session-dir", str(session_dir))
    try:
        _wait_for_health(port)
        with httpx.Client(
            trust_env=False, base_url=f"http://127.0.0.1:{port}", timeout=10.0
        ) as client:
            session_id = _create_session(client, workspace, _mock_fixture(tmp_path))
            late = workspace / ".minihns" / "skills" / "review"
            late.mkdir()
            (late / "SKILL.md").write_text(
                "---\nname: review\ndescription: 复核\n---\n正文\n", encoding="utf-8"
            )

            commands = client.get(
                f"/commands?session_id={session_id}", headers=_headers()
            ).json()["commands"]
            assert "review" in {command["name"] for command in commands}

            listed = client.post(
                f"/sessions/{session_id}/commands",
                headers=_headers(),
                json={"name": "skills"},
            )
            assert listed.status_code == 200, listed.text
            assert "review" in listed.json()["output"]
    finally:
        _stop(process)


def test_a_skill_command_with_instruction_queues_while_running(tmp_path: Path) -> None:
    """带指令的技能命令走消息同一条队列：段进行中投递是 202 + queued=true。"""
    session_dir = tmp_path / "sessions"
    workspace = tmp_path / "workspace"
    _write_skill(workspace)
    fixture = _slow_fixture(workspace, tmp_path)
    port = _free_port()
    process = _start_host(
        tmp_path, port, HOST_TOKEN, "--session-dir", str(session_dir), "--allow-auto-approval"
    )
    try:
        _wait_for_health(port)
        with httpx.Client(
            trust_env=False, base_url=f"http://127.0.0.1:{port}", timeout=10.0
        ) as client:
            session_id = _create_session(
                client, workspace, fixture, provider="mock", approval="auto"
            )
            client.post(
                f"/sessions/{session_id}/messages",
                headers=_headers(),
                json={"content": "第一句"},
            )
            log = session_dir / f"{session_id}.jsonl"
            _wait_for_log(log, '"tool/call"')

            queued = client.post(
                f"/sessions/{session_id}/commands",
                headers=_headers(),
                json={"name": "tdd", "arguments": "帮我改个函数"},
            )
            assert queued.status_code == 202, queued.text
            assert queued.json()["queued"] is True
    finally:
        _stop(process)
