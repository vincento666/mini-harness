"""seam ⑥：配置层黑盒（子进程）。"""

from __future__ import annotations

import json
from pathlib import Path

from cli_blackbox import _cli
from paths import HELLO_SCENARIO


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
