"""1.3：fixture 仓库路径常量能解析到最小 mock fixture。"""

from __future__ import annotations

import json

from paths import HELLO_SCENARIO


def test_hello_scenario_fixture_is_resolvable_and_is_one_plain_reply() -> None:
    assert HELLO_SCENARIO.is_file(), f"missing fixture: {HELLO_SCENARIO}"
    entries = json.loads(HELLO_SCENARIO.read_text(encoding="utf-8"))
    assert isinstance(entries, list)
    assert len(entries) == 1
    assert entries[0]["content"] == "hello from fixture"
    assert entries[0]["finish_reason"] == "stop"
