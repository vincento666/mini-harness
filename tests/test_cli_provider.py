"""seam ⑥：provider 选择与密钥来源。假 server 只监听 loopback，判据不依赖 8300、不需要真实密钥。"""

from __future__ import annotations

import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from cli_blackbox import _cli

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


class _FakeEndpoint:
    """一个只监听 127.0.0.1 的 chat completions 端点：记下收到的请求，回放固定响应。"""

    def __init__(self, *, status: int, body: dict[str, Any]) -> None:
        self.requests: list[dict[str, Any]] = []
        endpoint = self

        class _Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:
                length = int(self.headers.get("content-length", "0"))
                payload = json.loads(self.rfile.read(length).decode("utf-8"))
                endpoint.requests.append(
                    {
                        "path": self.path,
                        "authorization": self.headers.get("authorization"),
                        "body": payload,
                    }
                )
                encoded = json.dumps(body).encode("utf-8")
                self.send_response(status)
                self.send_header("content-type", "application/json")
                self.send_header("content-length", str(len(encoded)))
                self.end_headers()
                self.wfile.write(encoded)

            def log_message(self, *args: Any) -> None:
                return

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    def __enter__(self) -> _FakeEndpoint:
        self._thread.start()
        return self

    def __exit__(self, *exc_info: object) -> None:
        self._server.shutdown()
        self._server.server_close()

    @property
    def base_url(self) -> str:
        host, port = self._server.server_address
        return f"http://{host}:{port}/v1"


def _run_openai(tmp_path: Path, base_url: str, *, key_env_value: str | None) -> Any:
    env = dict(os.environ)
    env.pop(_KEY_ENV, None)
    if key_env_value is not None:
        env[_KEY_ENV] = key_env_value
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


def test_an_unset_key_env_still_sends_the_request(tmp_path: Path) -> None:
    with _FakeEndpoint(status=401, body={"error": "unauthorized"}) as endpoint:
        result = _run_openai(tmp_path, endpoint.base_url, key_env_value=None)

    assert result.returncode == 1
    assert "PROVIDER_HTTP_STATUS" in result.stderr
    assert len(endpoint.requests) == 1
    assert endpoint.requests[0]["authorization"] is None
    records = _session_records(tmp_path)
    types = [record["type"] for record in records]
    assert "model/retry" not in types
    error = next(record for record in records if record["type"] == "error/model")
    assert error["payload"]["code"] == "PROVIDER_HTTP_STATUS"


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
