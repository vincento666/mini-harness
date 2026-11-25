# 任务：add-http-proxy

## 1 能力

- [x] 1.1 `OpenAICompatProvider` 增加 `proxy` 参数：给了就在 `generate` 里现建 `httpx.AsyncHTTPTransport(proxy=...)`；注入的 `transport=` 优先
- [x] 1.2 `config/layering.py`：`BUILTIN_DEFAULTS["proxy"] = None`、`EffectiveSettings.proxy`；`config/load.py` 的 `SETTINGS_FIELDS` 加 `proxy: (str,)`
- [x] 1.3 `session/assembly.py`：`AssemblyRequest.proxy`、`request_from_args`、装配期校验（scheme 白名单 + 主机非空）→ `INVALID_ARGUMENT`
- [x] 1.4 `cli/main.py` 的 `_add_shared_flags` 加 `--proxy`；`cli/host.py` 的 `_SESSION_STRING_FIELDS` 加 `proxy`

## 2 判据

- [x] 2.1 单测：给 `proxy` 且不注入 transport 时，构造 transport 用的就是这个 URL（monkeypatch `httpx.AsyncHTTPTransport`）；注入 transport 时不看 `proxy`——`test_the_proxy_url_becomes_the_transport`、`test_an_injected_transport_beats_the_proxy`
- [x] 2.2 黑盒：本地 CONNECT 桩收到 `CONNECT example.invalid:443` 后回 502，进程以 `PROVIDER_TRANSPORT` + 退出码 1 收尾（不是崩溃）——`test_the_run_reaches_the_given_proxy`
- [x] 2.3 配置：`proxy` 字符串被接受、`proxy = 7897` 被 `CONFIG_INVALID_VALUE` 拒——`test_proxy_comes_from_the_config_and_the_flag_wins`、`test_a_non_string_proxy_is_a_config_error`
- [x] 2.4 坏 shape：`--proxy socks5://127.0.0.1:1080` → 退出码 2、`不支持 socks`、不建日志——`test_a_socks_proxy_is_rejected_before_the_session_starts`
- [x] 2.5 真端点：经 `http://127.0.0.1:7897` 跑一次 `run`——会话 `27a99bb0…`，`session/end = {MODEL_COMPLETED, steps: 1}`，`session/start` 里没有 `proxy` 键

## 3 收尾

- [x] 3.1 全量门禁：ruff / mypy 绿；**886 passed / 7 skipped**；`openspec validate --all --strict` 绿
- [x] 3.2 文档：`docs/reference/verification-endpoint.md` 的调用形状补 `--proxy`；`docs/CURRENT.md` 记一条；`AGENTS.md` 若提到端点也同步
- [x] 3.3 Learning Gate：把「显式 transport 优于 trust_env」「大小写两份代理变量会互相覆盖」记进 `docs/lessons.md`（若可复用）
