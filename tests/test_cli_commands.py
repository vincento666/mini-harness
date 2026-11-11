"""seam ⑥：host 的命令面（M14）——与 CLI 同一份清单/正文，不开段。"""

from __future__ import annotations

from pathlib import Path

import httpx

from test_cli_host import (
    HOST_TOKEN,
    _create_session,
    _free_port,
    _headers,
    _mock_fixture,
    _start_host,
    _stop,
    _wait_for_health,
)


def _write_skill(workspace: Path) -> None:
    directory = workspace / ".minihns" / "skills" / "tdd"
    directory.mkdir(parents=True)
    (directory / "SKILL.md").write_text(
        "---\nname: tdd\ndescription: 先写判据\n---\n\n第一步：写红判据\n", encoding="utf-8"
    )


def test_host_commands_match_the_cli_and_do_not_open_a_segment(tmp_path: Path) -> None:
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
            assert text.count('"command/run"') == 3
            assert text.count('"command/done"') == 3
            assert '"segment/start"' not in text
    finally:
        _stop(process)
