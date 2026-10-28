"""seam ②：配置层——装配的一部分，判的是 `ConfigFailure` 的 `code`。

seam ⑥ 的黑盒判据分不开「禁用的键」与「未知的键」：两者的退出码、stderr 前缀、有无日志都一样。
这条区分只在 `code` 上，所以在 ② 判。
"""

from __future__ import annotations

import argparse
from pathlib import Path

from mini_harness.config import (
    CONFIG_CODES,
    ConfigFailure,
    build_registry,
    layer_settings,
    load_config,
    validate_config,
)


def test_compaction_ratio_accepts_float_and_int() -> None:
    assert validate_config({"compaction_retain_ratio": 0.10}) is None
    assert validate_config({"compaction_retain_ratio": 1}) is None


def test_compaction_bool_is_not_a_number() -> None:
    failure = validate_config({"compaction_retain_tokens": True})

    assert isinstance(failure, ConfigFailure)
    assert failure.code == "CONFIG_INVALID_VALUE"


def test_an_old_config_without_compaction_keys_is_still_valid() -> None:
    assert validate_config({"window": 70000, "reserve": 100}) is None
    assert validate_config({"mode": "yolo"}) == ConfigFailure(
        "CONFIG_UNKNOWN_KEY", "配置文件里有未知的键：mode"
    )


def test_a_prompt_is_forbidden_not_merely_unknown() -> None:
    failure = validate_config({"prompt": "任务"})

    assert isinstance(failure, ConfigFailure)
    assert failure.code == "CONFIG_FORBIDDEN_KEY"


def test_an_unknown_key_is_a_distinct_failure() -> None:
    failure = validate_config({"mode": "yolo"})

    assert isinstance(failure, ConfigFailure)
    assert failure.code == "CONFIG_UNKNOWN_KEY"


def test_the_platform_facts_are_not_configurable() -> None:
    """平台事实是事实不是设置：配置文件里写它就是那条「未知的键」（ADR-0029）。"""
    failure = validate_config({"platform": {"os": "posix", "shell": "/bin/sh -c"}})

    assert isinstance(failure, ConfigFailure)
    assert failure.code == "CONFIG_UNKNOWN_KEY"
    assert "platform" in failure.detail


def test_a_wrong_typed_value_is_a_distinct_failure() -> None:
    failure = validate_config({"max_turns": "three"})

    assert isinstance(failure, ConfigFailure)
    assert failure.code == "CONFIG_INVALID_VALUE"


def test_a_settings_shaped_config_validates() -> None:
    assert validate_config({"max_turns": 3, "tools": ["read", "bash"]}) is None


def test_an_integer_ratio_is_normalized_to_float() -> None:
    effective = layer_settings(
        argparse.Namespace(),
        {"compaction_retain_ratio": 1, "compaction_threshold_ratio": 1},
        {},
    )

    assert isinstance(effective.compaction_retain_ratio, float)
    assert isinstance(effective.compaction_threshold_ratio, float)


def test_every_config_failure_code_is_reachable(tmp_path: Path) -> None:
    """失败码表不是装饰：词表里每个码逐个构造一次，构造不出来的那个就是死码。

    判据比的是「跑出来的集合 == 词表」：往 `ConfigCode` 里加一个取值而没人能跑到它，这条就红。
    """

    def code_of(result: object) -> str:
        assert isinstance(result, ConfigFailure)
        return result.code

    broken = tmp_path / "broken.toml"
    broken.write_text("max_turns = [1, 2", encoding="utf-8")

    reached = {
        code_of(load_config(tmp_path / "nope.toml")),
        code_of(load_config(broken)),
        code_of(validate_config({"mode": "yolo"})),
        code_of(validate_config({"max_turns": "three"})),
        code_of(validate_config({"prompt": "任务"})),
        code_of(build_registry(["web_search"])),
    }
    assert reached == CONFIG_CODES
