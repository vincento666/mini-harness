"""seam ⑥：配置层黑盒（子进程）。"""

from __future__ import annotations

import json
import os
from pathlib import Path

from cli_blackbox import _cli
from paths import HELLO_SCENARIO

_NO_KEY_ENV = "MINIHNS_CONFIG_TEST_KEY"


def _session_records(cwd: Path) -> list[dict[str, object]]:
    """读 cwd/sessions 下唯一那份日志的全部记录。"""
    path = next(iter(sorted((cwd / "sessions").glob("*.jsonl"))))
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]


def _start_payload(cwd: Path) -> dict[str, object]:
    records = _session_records(cwd)
    start = next(record for record in records if record["type"] == "session/start")
    payload = start["payload"]
    assert isinstance(payload, dict)
    return payload


def test_an_explicit_config_file_sets_the_settings(tmp_path: Path) -> None:
    root_config = tmp_path / "mini.config.toml"
    root_config.write_text("max_turns = 9\n", encoding="utf-8")
    explicit = tmp_path / "elsewhere" / "other.toml"
    explicit.parent.mkdir(parents=True)
    explicit.write_text("max_turns = 3\n", encoding="utf-8")

    result = _cli(
        "run",
        "-p",
        "任务",
        "--provider",
        "mock",
        "--fixture",
        str(HELLO_SCENARIO),
        "--config",
        str(explicit),
        "--yes",
        cwd=tmp_path,
    )

    assert result.returncode == 0, result.stderr
    assert _start_payload(tmp_path)["max_turns"] == 3


def test_no_config_file_means_builtin_defaults(tmp_path: Path) -> None:
    """守卫判据：没有配置文件时，有效参数就是内置默认，形状与 M5 之后逐字相同。"""
    result = _cli(
        "run",
        "-p",
        "任务",
        "--provider",
        "mock",
        "--fixture",
        str(HELLO_SCENARIO),
        "--yes",
        cwd=tmp_path,
    )

    assert result.returncode == 0, result.stderr
    payload = _start_payload(tmp_path)
    assert payload["provider"] == "mock"
    assert payload["max_turns"] == 8
    assert payload["window"] == 128000
    assert payload["reserve"] == 8192
    assert payload["sandbox"] == "workspace-write"
    assert payload["approval"] == "auto"
    assert payload["append_system_prompt"] == ""
    assert "base_url" not in payload
    assert "model" not in payload
    assert "api_key_env" not in payload
    assert payload["tools"] == ["read", "write", "edit", "glob", "grep", "bash"]


def test_the_workspace_root_config_file_is_picked_up(tmp_path: Path) -> None:
    (tmp_path / "mini.config.toml").write_text("max_turns = 3\n", encoding="utf-8")

    result = _cli(
        "run",
        "-p",
        "任务",
        "--provider",
        "mock",
        "--fixture",
        str(HELLO_SCENARIO),
        "--yes",
        cwd=tmp_path,
    )

    assert result.returncode == 0, result.stderr
    assert _start_payload(tmp_path)["max_turns"] == 3


def test_a_missing_explicit_config_file_is_an_argument_error(tmp_path: Path) -> None:
    missing = tmp_path / "absent.toml"

    result = _cli(
        "run",
        "-p",
        "任务",
        "--provider",
        "mock",
        "--fixture",
        str(HELLO_SCENARIO),
        "--config",
        str(missing),
        "--yes",
        cwd=tmp_path,
    )

    assert result.returncode == 2
    assert "INVALID_ARGUMENT" in result.stderr
    assert str(missing) in result.stderr
    assert list((tmp_path / "sessions").glob("*.jsonl")) == []


def test_a_malformed_config_file_is_an_argument_error(tmp_path: Path) -> None:
    config = tmp_path / "mini.config.toml"
    config.write_text("max_turns = = 3\n", encoding="utf-8")

    result = _cli(
        "run",
        "-p",
        "任务",
        "--provider",
        "mock",
        "--fixture",
        str(HELLO_SCENARIO),
        "--yes",
        cwd=tmp_path,
    )

    assert result.returncode == 2
    assert "INVALID_ARGUMENT" in result.stderr
    assert "line 1" in result.stderr
    assert list((tmp_path / "sessions").glob("*.jsonl")) == []


def test_an_unknown_key_is_an_argument_error(tmp_path: Path) -> None:
    config = tmp_path / "mini.config.toml"
    config.write_text('mode = "yolo"\n', encoding="utf-8")

    result = _cli(
        "run",
        "-p",
        "任务",
        "--provider",
        "mock",
        "--fixture",
        str(HELLO_SCENARIO),
        "--yes",
        cwd=tmp_path,
    )

    assert result.returncode == 2
    assert "INVALID_ARGUMENT" in result.stderr
    assert "mode" in result.stderr
    assert list((tmp_path / "sessions").glob("*.jsonl")) == []


def test_a_wrong_typed_value_is_an_argument_error(tmp_path: Path) -> None:
    config = tmp_path / "mini.config.toml"
    config.write_text('max_turns = "three"\n', encoding="utf-8")

    result = _cli(
        "run",
        "-p",
        "任务",
        "--provider",
        "mock",
        "--fixture",
        str(HELLO_SCENARIO),
        "--yes",
        cwd=tmp_path,
    )

    assert result.returncode == 2
    assert "INVALID_ARGUMENT" in result.stderr
    assert "max_turns" in result.stderr
    assert list((tmp_path / "sessions").glob("*.jsonl")) == []


def test_prompt_in_the_config_file_is_an_argument_error(tmp_path: Path) -> None:
    config = tmp_path / "mini.config.toml"
    config.write_text('prompt = "任务"\n', encoding="utf-8")

    result = _cli(
        "run",
        "-p",
        "另一个任务",
        "--provider",
        "mock",
        "--fixture",
        str(HELLO_SCENARIO),
        "--yes",
        cwd=tmp_path,
    )

    assert result.returncode == 2
    assert "INVALID_ARGUMENT" in result.stderr
    assert "prompt" in result.stderr
    assert list((tmp_path / "sessions").glob("*.jsonl")) == []


def test_a_literal_api_key_in_the_config_file_is_an_argument_error(tmp_path: Path) -> None:
    config = tmp_path / "mini.config.toml"
    config.write_text('api_key = "sk-secret"\n', encoding="utf-8")

    result = _cli(
        "run",
        "-p",
        "任务",
        "--provider",
        "mock",
        "--fixture",
        str(HELLO_SCENARIO),
        "--yes",
        cwd=tmp_path,
    )

    assert result.returncode == 2
    assert "INVALID_ARGUMENT" in result.stderr
    assert "api_key" in result.stderr
    assert list((tmp_path / "sessions").glob("*.jsonl")) == []


def test_an_empty_config_file_equals_no_config_file(tmp_path: Path) -> None:
    (tmp_path / "mini.config.toml").write_text("", encoding="utf-8")

    result = _cli(
        "run",
        "-p",
        "任务",
        "--provider",
        "mock",
        "--fixture",
        str(HELLO_SCENARIO),
        "--yes",
        cwd=tmp_path,
    )

    assert result.returncode == 0, result.stderr
    assert _start_payload(tmp_path)["max_turns"] == 8


def test_the_config_file_overrides_builtin_defaults(tmp_path: Path) -> None:
    (tmp_path / "mini.config.toml").write_text("max_turns = 3\n", encoding="utf-8")

    result = _cli(
        "run",
        "-p",
        "任务",
        "--provider",
        "mock",
        "--fixture",
        str(HELLO_SCENARIO),
        "--yes",
        cwd=tmp_path,
    )

    assert result.returncode == 0, result.stderr
    assert _start_payload(tmp_path)["max_turns"] == 3


def test_the_cli_flag_overrides_the_config_file(tmp_path: Path) -> None:
    (tmp_path / "mini.config.toml").write_text("max_turns = 3\n", encoding="utf-8")

    result = _cli(
        "run",
        "-p",
        "任务",
        "--provider",
        "mock",
        "--fixture",
        str(HELLO_SCENARIO),
        "--max-turns",
        "5",
        "--yes",
        cwd=tmp_path,
    )

    assert result.returncode == 0, result.stderr
    assert _start_payload(tmp_path)["max_turns"] == 5


def test_a_flag_equal_to_the_builtin_default_is_still_explicit(tmp_path: Path) -> None:
    """`--max-turns 8` 与「没给 flag 而内置默认也是 8」是两层不同的事实：显式给的那层赢。"""
    (tmp_path / "mini.config.toml").write_text("max_turns = 3\n", encoding="utf-8")

    result = _cli(
        "run",
        "-p",
        "任务",
        "--provider",
        "mock",
        "--fixture",
        str(HELLO_SCENARIO),
        "--max-turns",
        "8",
        "--yes",
        cwd=tmp_path,
    )

    assert result.returncode == 0, result.stderr
    assert _start_payload(tmp_path)["max_turns"] == 8


def test_a_config_value_below_a_bound_is_an_argument_error(tmp_path: Path) -> None:
    (tmp_path / "mini.config.toml").write_text("window = 0\n", encoding="utf-8")

    result = _cli(
        "run",
        "-p",
        "任务",
        "--provider",
        "mock",
        "--fixture",
        str(HELLO_SCENARIO),
        "--yes",
        cwd=tmp_path,
    )

    assert result.returncode == 2
    assert "INVALID_ARGUMENT" in result.stderr
    assert "window" in result.stderr
    assert list((tmp_path / "sessions").glob("*.jsonl")) == []


def test_a_config_file_setting_a_provider_selects_that_provider(tmp_path: Path) -> None:
    """配置写 `provider = "openai"` 且命令行没给 `--provider`：走的是 openai 那一支。

    判据用「openai 与 `--fixture` 互斥」这条错误来观察走了哪一支——它不需要真发请求。
    """
    (tmp_path / "mini.config.toml").write_text('provider = "openai"\n', encoding="utf-8")

    result = _cli(
        "run",
        "-p",
        "任务",
        "--fixture",
        str(HELLO_SCENARIO),
        "--yes",
        cwd=tmp_path,
    )

    assert result.returncode == 2
    assert "INVALID_ARGUMENT" in result.stderr
    assert "fixture" in result.stderr
    assert list((tmp_path / "sessions").glob("*.jsonl")) == []


def test_the_configured_tool_whitelist_reaches_payload_and_model_request(tmp_path: Path) -> None:
    (tmp_path / "mini.config.toml").write_text('tools = ["read", "grep"]\n', encoding="utf-8")

    result = _cli(
        "run",
        "-p",
        "任务",
        "--provider",
        "mock",
        "--fixture",
        str(HELLO_SCENARIO),
        "--yes",
        cwd=tmp_path,
    )

    assert result.returncode == 0, result.stderr
    records = _session_records(tmp_path)
    start = next(record for record in records if record["type"] == "session/start")
    request = next(record for record in records if record["type"] == "model/request")
    assert start["payload"]["tools"] == ["read", "grep"]
    assert request["payload"]["tools"] == ["read", "grep"]


def test_an_unknown_tool_name_in_the_config_is_an_argument_error(tmp_path: Path) -> None:
    (tmp_path / "mini.config.toml").write_text('tools = ["read", "web_search"]\n', encoding="utf-8")

    result = _cli(
        "run",
        "-p",
        "任务",
        "--provider",
        "mock",
        "--fixture",
        str(HELLO_SCENARIO),
        "--yes",
        cwd=tmp_path,
    )

    assert result.returncode == 2
    assert "INVALID_ARGUMENT" in result.stderr
    assert "web_search" in result.stderr
    assert list((tmp_path / "sessions").glob("*.jsonl")) == []


def test_a_boolean_where_a_number_is_expected_is_an_argument_error(tmp_path: Path) -> None:
    config = tmp_path / "mini.config.toml"
    config.write_text("max_turns = true\n", encoding="utf-8")

    result = _cli(
        "run",
        "-p",
        "任务",
        "--provider",
        "mock",
        "--fixture",
        str(HELLO_SCENARIO),
        "--yes",
        cwd=tmp_path,
    )

    assert result.returncode == 2
    assert "INVALID_ARGUMENT" in result.stderr
    assert "max_turns" in result.stderr
    assert list((tmp_path / "sessions").glob("*.jsonl")) == []


def test_the_same_cli_under_two_config_files_yields_different_payloads(tmp_path: Path) -> None:
    """完成判据：命令行一字不差，配置文件换一份，payload 就跟着换。"""
    with_config = tmp_path / "with-config"
    without_config = tmp_path / "no-config"
    with_config.mkdir()
    without_config.mkdir()
    (with_config / "mini.config.toml").write_text(
        'max_turns = 2\ntools = ["read"]\n', encoding="utf-8"
    )

    argv = (
        "run",
        "-p",
        "任务",
        "--provider",
        "mock",
        "--fixture",
        str(HELLO_SCENARIO),
        "--yes",
    )
    configured = _cli(*argv, cwd=with_config)
    plain = _cli(*argv, cwd=without_config)

    assert configured.returncode == 0, configured.stderr
    assert plain.returncode == 0, plain.stderr
    assert _start_payload(with_config)["max_turns"] == 2
    assert _start_payload(without_config)["max_turns"] == 8
    assert _start_payload(with_config)["tools"] == ["read"]
    assert _start_payload(without_config)["tools"] == [
        "read",
        "write",
        "edit",
        "glob",
        "grep",
        "bash",
    ]


def test_a_missing_required_item_leaves_no_log_file(tmp_path: Path) -> None:
    """完成判据：缺必需项时目录里一个文件都不多——既有的日志也不动。"""
    key_case = tmp_path / "key"
    toml_case = tmp_path / "toml"
    for directory in (key_case, toml_case):
        (directory / "sessions").mkdir(parents=True)
        (directory / "sessions" / "existing.jsonl").write_text(
            '{"type":"session/start"}\n', encoding="utf-8"
        )
    (toml_case / "mini.config.toml").write_text("max_turns = [1, 2", encoding="utf-8")

    before = sorted(path.relative_to(tmp_path).as_posix() for path in tmp_path.rglob("*"))

    env = dict(os.environ)
    env.pop(_NO_KEY_ENV, None)
    missing_key = _cli(
        "run",
        "-p",
        "任务",
        "--provider",
        "openai",
        "--base-url",
        "http://127.0.0.1:9/v1",
        "--api-key-env",
        _NO_KEY_ENV,
        "--yes",
        cwd=key_case,
        env=env,
    )
    broken_toml = _cli(
        "run",
        "-p",
        "任务",
        "--provider",
        "mock",
        "--fixture",
        str(HELLO_SCENARIO),
        "--yes",
        cwd=toml_case,
    )

    after = sorted(path.relative_to(tmp_path).as_posix() for path in tmp_path.rglob("*"))
    assert missing_key.returncode == 2
    assert "INVALID_ARGUMENT" in missing_key.stderr
    assert _NO_KEY_ENV in missing_key.stderr
    assert broken_toml.returncode == 2
    assert "INVALID_ARGUMENT" in broken_toml.stderr
    assert after == before
