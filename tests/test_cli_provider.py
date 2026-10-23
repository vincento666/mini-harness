"""seam ⑥：provider 选择与密钥来源。假 server 只监听 loopback，判据不依赖 8300、不需要真实密钥。"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from cli_blackbox import _cli, _FakeEndpoint
from paths import HELLO_SCENARIO

_KEY_ENV = "MINIHNS_TEST_KEY"
_KEY_VALUE = "sk-test-0123456789abcdef"

_STOP_BODY: dict[str, Any] = {
    "id": "chatcmpl-1",
    "choices": [
        {
            "index": 0,
            "message": {"role": "assistant", "content": "完成", "tool_calls": []},
            "finish_reason": "stop",
        }
    ],
    "usage": {"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5},
}


def _run_openai(
    tmp_path: Path,
    base_url: str,
    *,
    key_env_value: str | None,
    extra_env: dict[str, str] | None = None,
) -> Any:
    env = dict(os.environ)
    env.pop(_KEY_ENV, None)
    if key_env_value is not None:
        env[_KEY_ENV] = key_env_value
    for name, value in (extra_env or {}).items():
        env[name] = value
    return _cli(
        "run",
        "-p",
        "任务",
        "--provider",
        "openai",
        "--base-url",
        base_url,
        "--model",
        "test-model",
        "--api-key-env",
        _KEY_ENV,
        "--session-dir",
        str(tmp_path),
        "--yes",
        cwd=tmp_path,
        env=env,
    )


def _session_records(session_dir: Path) -> list[dict[str, Any]]:
    logs = list(session_dir.glob("*.jsonl"))
    assert len(logs) == 1, "应当只有一份 session 日志"
    return [json.loads(line) for line in logs[0].read_text(encoding="utf-8").splitlines() if line]


def test_unknown_provider_is_exit_2_and_creates_no_log(tmp_path: Path) -> None:
    result = _cli(
        "run", "-p", "x", "--provider", "claude", "--session-dir", str(tmp_path), cwd=tmp_path
    )

    assert result.returncode == 2
    assert "UNKNOWN_PROVIDER" in result.stderr
    assert "deepseek" in result.stderr
    assert list(tmp_path.glob("*.jsonl")) == []


def test_openai_with_a_fixture_is_an_argument_error(tmp_path: Path) -> None:
    fixture = tmp_path / "turns.json"
    fixture.write_text("[]", encoding="utf-8")

    result = _cli(
        "run",
        "-p",
        "任务",
        "--provider",
        "openai",
        "--fixture",
        str(fixture),
        "--session-dir",
        str(tmp_path),
        cwd=tmp_path,
    )

    assert result.returncode == 2
    assert "INVALID_ARGUMENT" in result.stderr
    assert list(tmp_path.glob("*.jsonl")) == []


def test_an_unset_key_env_is_an_argument_error(tmp_path: Path) -> None:
    """密钥是装配的必需项：变量未设就在 session 开始之前当场失败，一个请求都不发。"""
    with _FakeEndpoint(status=401, body={"error": "unauthorized"}) as endpoint:
        result = _run_openai(tmp_path, endpoint.base_url, key_env_value=None)

    assert result.returncode == 2
    assert "INVALID_ARGUMENT" in result.stderr
    assert _KEY_ENV in result.stderr
    assert list(tmp_path.glob("*.jsonl")) == []
    assert len(endpoint.requests) == 0


def test_an_empty_key_env_is_an_argument_error(tmp_path: Path) -> None:
    """「未设」与「设为空串」是同一条判据：空串不是密钥。"""
    with _FakeEndpoint(status=401, body={"error": "unauthorized"}) as endpoint:
        result = _run_openai(tmp_path, endpoint.base_url, key_env_value="")

    assert result.returncode == 2
    assert "INVALID_ARGUMENT" in result.stderr
    assert _KEY_ENV in result.stderr
    assert list(tmp_path.glob("*.jsonl")) == []
    assert len(endpoint.requests) == 0


def test_the_key_reaches_the_request_header_and_nowhere_else(tmp_path: Path) -> None:
    with _FakeEndpoint(status=200, body=_STOP_BODY) as endpoint:
        result = _run_openai(tmp_path, endpoint.base_url, key_env_value=_KEY_VALUE)

    assert result.returncode == 0
    assert endpoint.requests[0]["authorization"] == f"Bearer {_KEY_VALUE}"
    assert _KEY_VALUE not in result.stdout
    assert _KEY_VALUE not in result.stderr
    log_text = next(tmp_path.glob("*.jsonl")).read_text(encoding="utf-8")
    assert _KEY_VALUE not in log_text
    assert _KEY_ENV in log_text


def test_openai_run_records_base_url_model_and_the_key_variable_name(tmp_path: Path) -> None:
    with _FakeEndpoint(status=200, body=_STOP_BODY) as endpoint:
        result = _run_openai(tmp_path, endpoint.base_url, key_env_value=_KEY_VALUE)

    assert result.returncode == 0
    start = next(
        record for record in _session_records(tmp_path) if record["type"] == "session/start"
    )
    assert start["payload"]["provider"] == "openai"
    assert start["payload"]["base_url"] == endpoint.base_url
    assert start["payload"]["model"] == "test-model"
    assert start["payload"]["api_key_env"] == _KEY_ENV
    assert _KEY_VALUE not in json.dumps(start["payload"])


def test_the_cli_decides_the_endpoint_once(tmp_path: Path) -> None:
    """两条路径的 payload 差别出自装配处那一个判断：openai 那次三条齐，mock 那次三条都不在。"""
    openai_dir = tmp_path / "openai"
    mock_dir = tmp_path / "mock"
    openai_dir.mkdir()
    mock_dir.mkdir()

    with _FakeEndpoint(status=200, body=_STOP_BODY) as endpoint:
        openai_run = _run_openai(openai_dir, endpoint.base_url, key_env_value=_KEY_VALUE)
        mock_run = _cli(
            "run",
            "-p",
            "任务",
            "--provider",
            "mock",
            "--fixture",
            str(HELLO_SCENARIO),
            "--session-dir",
            str(mock_dir),
            "--yes",
            cwd=mock_dir,
        )

    assert openai_run.returncode == 0, openai_run.stderr
    assert mock_run.returncode == 0, mock_run.stderr
    openai_start = next(
        record for record in _session_records(openai_dir) if record["type"] == "session/start"
    )
    mock_start = next(
        record for record in _session_records(mock_dir) if record["type"] == "session/start"
    )
    endpoint_keys = {"base_url", "model", "api_key_env"}
    assert endpoint_keys <= set(openai_start["payload"])
    assert not endpoint_keys & set(mock_start["payload"])


def test_a_config_file_can_supply_the_endpoint(tmp_path: Path) -> None:
    """配置写端点三条、命令行一条都没给：payload 取自配置那一层。"""
    env = dict(os.environ)
    env.pop(_KEY_ENV, None)
    env[_KEY_ENV] = _KEY_VALUE

    with _FakeEndpoint(status=200, body=_STOP_BODY) as endpoint:
        (tmp_path / "mini.config.toml").write_text(
            f'provider = "openai"\nbase_url = "{endpoint.base_url}"\n'
            f'model = "config-model"\napi_key_env = "{_KEY_ENV}"\n',
            encoding="utf-8",
        )
        result = _cli(
            "run",
            "-p",
            "任务",
            "--session-dir",
            str(tmp_path),
            "--yes",
            cwd=tmp_path,
            env=env,
        )

    assert result.returncode == 0, result.stderr
    start = next(
        record for record in _session_records(tmp_path) if record["type"] == "session/start"
    )
    assert start["payload"]["provider"] == "openai"
    assert start["payload"]["base_url"] == endpoint.base_url
    assert start["payload"]["model"] == "config-model"
    assert start["payload"]["api_key_env"] == _KEY_ENV
    assert _KEY_VALUE not in json.dumps(start["payload"])


def test_a_config_supplied_provider_is_checked_the_same_way(tmp_path: Path) -> None:
    """必需项在层叠之后判：provider 取自配置文件时，密钥缺失同样是退出码 2、无日志、无请求。"""
    (tmp_path / "mini.config.toml").write_text(
        f'provider = "openai"\napi_key_env = "{_KEY_ENV}"\n',
        encoding="utf-8",
    )
    env = dict(os.environ)
    env.pop(_KEY_ENV, None)

    with _FakeEndpoint(status=401, body={"error": "unauthorized"}) as endpoint:
        result = _cli(
            "run",
            "-p",
            "任务",
            "--base-url",
            endpoint.base_url,
            "--session-dir",
            str(tmp_path),
            "--yes",
            cwd=tmp_path,
            env=env,
        )

    assert result.returncode == 2
    assert "INVALID_ARGUMENT" in result.stderr
    assert _KEY_ENV in result.stderr
    assert list(tmp_path.glob("*.jsonl")) == []
    assert len(endpoint.requests) == 0


def test_a_mock_run_needs_no_key(tmp_path: Path) -> None:
    """必需项只跟着走的那条路径：mock 这一支不碰密钥，变量未设照样跑完。"""
    env = dict(os.environ)
    env.pop(_KEY_ENV, None)

    result = _cli(
        "run",
        "-p",
        "任务",
        "--provider",
        "mock",
        "--fixture",
        str(HELLO_SCENARIO),
        "--session-dir",
        str(tmp_path),
        "--yes",
        cwd=tmp_path,
        env=env,
    )

    assert result.returncode == 0, result.stderr
    assert _KEY_ENV not in result.stderr


def test_a_dead_endpoint_collapses_into_a_transport_result(tmp_path: Path) -> None:
    """端点没在监听：退出码 1、`error/model` 是 `PROVIDER_TRANSPORT`、没有重试、没有 traceback。"""
    result = _run_openai(tmp_path, "http://127.0.0.1:9/v1", key_env_value=_KEY_VALUE)

    assert result.returncode == 1
    assert "PROVIDER_TRANSPORT" in result.stderr
    assert "Traceback" not in result.stderr
    records = _session_records(tmp_path)
    types = [record["type"] for record in records]
    assert "model/retry" not in types
    error = next(record for record in records if record["type"] == "error/model")
    assert error["payload"]["code"] == "PROVIDER_TRANSPORT"
    assert records[-1]["type"] == "session/end"


def test_a_malformed_base_url_is_an_argument_error(tmp_path: Path) -> None:
    """`--base-url` 形状不合法是参数错误：退出码 2、不建日志、不给 traceback。"""
    result = _run_openai(tmp_path, "http://[::1", key_env_value=None)

    assert result.returncode == 2
    assert "INVALID_ARGUMENT" in result.stderr
    assert "Traceback" not in result.stderr
    assert list(tmp_path.glob("*.jsonl")) == []


def test_a_hostile_no_proxy_does_not_stop_the_request(tmp_path: Path) -> None:
    """规格 scenario「主机的 NO_PROXY 里带方括号 IPv6」：判据自己设这个变量，不靠本机恰好有。"""
    with _FakeEndpoint(status=200, body=_STOP_BODY) as endpoint:
        result = _run_openai(
            tmp_path,
            endpoint.base_url,
            key_env_value=_KEY_VALUE,
            extra_env={
                "NO_PROXY": "localhost,127.0.0.1,::1,[::1]",
                "HTTP_PROXY": "http://127.0.0.1:7897",
            },
        )

    assert result.returncode == 0
    assert "Traceback" not in result.stderr
    assert len(endpoint.requests) == 1


def test_a_200_without_choices_is_a_schema_error_at_the_cli(tmp_path: Path) -> None:
    """规格 scenario「200 的响应体不是合法 chat completion」：日志与退出码那一层也要有判据。"""
    with _FakeEndpoint(status=200, body={"id": "chatcmpl-4"}) as endpoint:
        result = _run_openai(tmp_path, endpoint.base_url, key_env_value=_KEY_VALUE)

    assert result.returncode == 1
    assert "PROVIDER_SCHEMA_INVALID" in result.stderr
    records = _session_records(tmp_path)
    types = [record["type"] for record in records]
    assert "model/retry" not in types
    error = next(record for record in records if record["type"] == "error/model")
    assert error["payload"]["code"] == "PROVIDER_SCHEMA_INVALID"
    assert records[-1]["type"] == "session/end"
    assert len(endpoint.requests) == 1


def _env_without_default_key(**extra: str) -> dict[str, str]:
    """判默认 provider 的环境：先摘掉本机可能已有的那个变量，再按测试写假值。"""
    env = dict(os.environ)
    env.pop("MINIHNS_API_KEY", None)
    env.update(extra)
    return env


def test_a_bare_run_with_the_key_present_defaults_to_openai(tmp_path: Path) -> None:
    """delta「有密钥时裸跑的默认 provider 是 openai」：默认不再是 mock 那句 `--fixture`。"""
    result = _cli(
        "run",
        "-p",
        "任务",
        "--session-dir",
        str(tmp_path),
        cwd=tmp_path,
        env=_env_without_default_key(MINIHNS_API_KEY=_KEY_VALUE),
    )

    assert result.returncode == 2
    assert "INVALID_ARGUMENT" in result.stderr
    assert "--model" in result.stderr
    assert "--fixture" not in result.stderr
    assert list(tmp_path.glob("*.jsonl")) == []


def test_a_bare_run_without_the_key_still_defaults_to_mock(tmp_path: Path) -> None:
    """delta「没有密钥时裸跑的默认 provider 仍是 mock」：这一半的形状不许变。"""
    result = _cli(
        "run",
        "-p",
        "任务",
        "--session-dir",
        str(tmp_path),
        cwd=tmp_path,
        env=_env_without_default_key(),
    )

    assert result.returncode == 2
    assert "INVALID_ARGUMENT" in result.stderr
    assert "--fixture" in result.stderr
    assert list(tmp_path.glob("*.jsonl")) == []


def test_a_config_file_provider_does_not_look_at_the_key_presence(tmp_path: Path) -> None:
    """delta「配置文件指定的 provider 同样判」：写了 openai 就不看密钥在场，缺了当场失败。"""
    (tmp_path / "mini.config.toml").write_text('provider = "openai"\n', encoding="utf-8")

    result = _cli(
        "run",
        "-p",
        "任务",
        "--session-dir",
        str(tmp_path),
        cwd=tmp_path,
        env=_env_without_default_key(),
    )

    assert result.returncode == 2
    assert "INVALID_ARGUMENT" in result.stderr
    assert "MINIHNS_API_KEY" in result.stderr
    assert list(tmp_path.glob("*.jsonl")) == []


def test_the_deepseek_name_is_accepted_and_its_preset_is_recorded(tmp_path: Path) -> None:
    """delta「deepseek 预设走自己的默认变量」：名字进 payload，model 与变量名由预设填。

    「请求打到预设地址」那一半在 seam ② 判（`test_config_presets.py` 断言 `base_url` 就是
    `https://api.deepseek.com`）与真实端点判（tasks 6.2）：黑盒里要拿 loopback 假 server 就得给
    `--base-url`，给了就不叫预设。
    """
    with _FakeEndpoint(status=200, body=_STOP_BODY) as endpoint:
        result = _cli(
            "run",
            "-p",
            "任务",
            "--provider",
            "deepseek",
            "--base-url",
            endpoint.base_url,
            "--session-dir",
            str(tmp_path),
            "--yes",
            cwd=tmp_path,
            env=_env_without_default_key(DEEPSEEK_API_KEY=_KEY_VALUE),
        )

    assert result.returncode == 0, result.stderr
    payload = _session_records(tmp_path)[0]["payload"]
    assert payload["provider"] == "deepseek"
    assert payload["model"] == "deepseek-chat"
    assert payload["api_key_env"] == "DEEPSEEK_API_KEY"


def test_openai_without_a_base_url_does_not_run_on_the_deepseek_default(tmp_path: Path) -> None:
    """地雷的形状：`--provider openai` 不带 `--base-url` 不再静默连 deepseek 端点。

    黑盒判的是这句话指向哪一项——缺的是 `--model`（openai 预设不给它默认），不是别的东西；
    生效地址本身在 seam ② 判（`test_the_openai_preset_is_openai_not_deepseek`）。
    """
    result = _cli(
        "run",
        "-p",
        "任务",
        "--provider",
        "openai",
        "--session-dir",
        str(tmp_path),
        cwd=tmp_path,
        env=_env_without_default_key(MINIHNS_API_KEY=_KEY_VALUE),
    )

    assert result.returncode == 2
    assert "INVALID_ARGUMENT" in result.stderr
    assert "--model" in result.stderr
    assert list(tmp_path.glob("*.jsonl")) == []


def test_a_missing_model_fails_before_any_request_is_sent(tmp_path: Path) -> None:
    """delta「openai 预设缺 model 当场失败」：一个请求都不发，一个文件都不多。"""
    with _FakeEndpoint(status=200, body=_STOP_BODY) as endpoint:
        result = _cli(
            "run",
            "-p",
            "任务",
            "--provider",
            "openai",
            "--base-url",
            endpoint.base_url,
            "--api-key-env",
            _KEY_ENV,
            "--session-dir",
            str(tmp_path),
            cwd=tmp_path,
            env=_env_without_default_key(**{_KEY_ENV: _KEY_VALUE}),
        )

    assert result.returncode == 2
    assert "INVALID_ARGUMENT" in result.stderr
    assert "--model" in result.stderr
    assert list(tmp_path.glob("*.jsonl")) == []
    assert len(endpoint.requests) == 0
