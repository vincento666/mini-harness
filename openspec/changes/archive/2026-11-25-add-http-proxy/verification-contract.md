# 验证契约

**日期**：2026-11-25（补记：本 change 的 apply 期没有落契约文件，归档前按已完成的实现与判据回写，不新增行为）。

## 目标

给 provider 一条**显式**出口：`--proxy http://127.0.0.1:7897` 让请求经代理发出，同时保持「不读环境代理变量」这条既有不变量。本机直连 OpenRouter 的推理请求返回 400 `Request path cannot be relayed`，没有这条出口就没有可用的真实端点。

## 可观察行为

1. **代理 URL 变成 transport**：给了 `proxy` 且没有注入 transport 时，构造的就是 `httpx.AsyncHTTPTransport(proxy=<url>)`；注入了 transport（测试桩）时 MUST NOT 再看 `proxy`。
2. **请求真的经代理**：CLI 黑盒里本地 CONNECT 桩收到 `CONNECT <host>:443`，进程以 `PROVIDER_TRANSPORT` + 退出码 1 收尾（不是崩溃）。
3. **配置与 flag 的优先级**：`--proxy` > 配置文件 `proxy` > 直连；配置文件里 `proxy = 7897`（非字符串）是 `CONFIG_INVALID_VALUE`。
4. **坏形状当场拒绝**：`socks5://` 或没有主机的值在装配期以 `INVALID_ARGUMENT`（退出码 2）失败，不建日志、不发请求。
5. **环境代理始终无效**：`HTTP_PROXY` / `http_proxy` 在场（且 `NO_PROXY` 清空）时，请求仍直连端点；`trust_env` 恒为 `False`。
6. **代理不进日志**：`session/start` 的键集合与不给 `--proxy` 时完全相同。

## 判据（seam 映射）

| 行为 | 判据 |
|---|---|
| 1 | `test_the_proxy_url_becomes_the_transport`、`test_an_injected_transport_beats_the_proxy`（`tests/test_provider_openai.py`） |
| 2 | `test_the_run_reaches_the_given_proxy`（`tests/test_cli_run.py`，CONNECT 桩回 502 → `PROVIDER_TRANSPORT` + 退出码 1） |
| 3 | `test_proxy_comes_from_the_config_and_the_flag_wins`、`test_a_non_string_proxy_is_a_config_error`（`tests/test_config_layering.py`） |
| 4 | `test_a_socks_proxy_is_rejected_before_the_session_starts`（`tests/test_cli_run.py`）；UAT 场次 2 的实测退出码 2 |
| 5 | `test_a_proxy_in_the_environment_does_not_change_the_exit`（`tests/test_cli_provider.py`，**2026-11-25 补**：环境给 `HTTP_PROXY=http://127.0.0.1:1`、`NO_PROXY` 清空 → 仍直连成功）；`test_a_hostile_no_proxy_does_not_stop_the_request` 守 `NO_PROXY=[::1]` 那一条 |
| 6 | `test_the_run_reaches_the_given_proxy` 的 payload 键断言；真实端点会话 `27a99bb0…` 的 `session/start` 无 `proxy` 键 |

真实端点那一半：`docs/verification/add-http-proxy-uat.md` 场次 1（经 `127.0.0.1:7897` 跑通，`session/end = {MODEL_COMPLETED, steps: 1}`）。

## 坏法清单（变异种子，2026-11-25 实跑）

1. **改回读环境**：`trust_env=True` → 行为 5 红（新补的判据；旧的 `NO_PROXY` 判据杀不死它，见 mutation 记录）。
2. **跳过形状校验**：`validate_proxy` 直接 `return None` → 行为 4 红（`socks5://` 不再报「不支持 socks」，错误被密钥校验抢先）。
3. **proxy 顶掉注入的 transport**：`if transport is None and self._proxy is not None` 改成只看 `proxy` → 行为 1 红。
4. **proxy 写进日志**（**不可构造**）：`SessionSettings` 里根本没有 `proxy` 字段，provider 在装配期直接拿到 URL，payload 无从写它——这条由结构保证，不是判据保证。

## 不验什么

- **不做 SOCKS**：需要 `httpx[socks]`，等真有需要再立项。`socks5://` 是「坏形状」的一个实例，不是待支持的能力。
- **不做连接复用**：`generate` 每次新建 client，transport 也随之新建（`AsyncClient.aclose()` 会关掉传入的 transport，复用会撞「transport is closed」）。
- **不改默认值**：没有 `proxy` 就是直连，与加这个能力之前完全一致。
- **不把 `proxy` 写进 `session/start`**：代理 URL 可能带凭据，日志是长期资产；它也不影响 replay 的确定性。
