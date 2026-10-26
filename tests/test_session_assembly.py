"""seam ②：装配从 CLI 私有函数抽成库——四个入口共用同一条装配路（H1 design D2）。

判据只碰 `assemble` 的返回值，不碰 CLI 的退出码表：退出码是入口的事，装配只回答
「材料齐不齐、失败是什么码」。
"""

from __future__ import annotations

import json
from pathlib import Path

from mini_harness.session.assembly import AssemblyRequest, Prepared, assemble


def test_assemble_returns_a_prepared_for_a_mock_request(tmp_path: Path) -> None:
    fixture = tmp_path / "turns.json"
    fixture.write_text(
        json.dumps([{"content": "好", "finish_reason": "stop"}], ensure_ascii=False),
        encoding="utf-8",
    )
    session_dir = tmp_path / "sessions"

    prepared = assemble(
        AssemblyRequest(
            provider="mock",
            fixture=str(fixture),
            session_dir=str(session_dir),
        ),
        {},
    )

    assert isinstance(prepared, Prepared)
    assert prepared.settings.provider_name == "mock"
    assert prepared.log.path.parent == session_dir
    assert prepared.log.path.is_file()
    assert prepared.log.path.read_text(encoding="utf-8") == ""
    assert [spec.name for spec in prepared.registry.specs()] == [
        "read",
        "write",
        "edit",
        "glob",
        "grep",
        "bash",
    ]
