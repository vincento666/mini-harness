# 变异测试：add-http-proxy

**日期**：2026-11-25。
**基线**：`tests/test_provider_openai.py`、`tests/test_cli_run.py`、`tests/test_config_layering.py` 的相关子集 10 passed。
**方法**：逐条改坏实现 → 跑相关测试 → 记录哪些变红 → 用 Edit 反向改回 → 确认回到基线（`git diff --stat src/` 为空）。

## 变异

| # | 变异 | 改法 | 结果 |
|---|---|---|---|
| M1 | 改回读环境代理 | `openai_compat.py` 的 `AsyncClient(..., trust_env=False)` 改成 `trust_env=True` | **第一轮存活**：`test_a_hostile_no_proxy_does_not_stop_the_request` 仍绿——因为那条用例的 `NO_PROXY` 恰好豁免了端点主机，环境代理本来就不生效。**补判据后杀死**：新增 `test_a_proxy_in_the_environment_does_not_change_the_exit`（`HTTP_PROXY=http://127.0.0.1:1` + `NO_PROXY` 清空），在变异下报 `PROVIDER_TRANSPORT: All connection attempts failed`、退出码 1 |
| M2 | 跳过形状校验 | `validate_proxy` 函数体改成 `return None` | **杀死 1 条**：`test_a_socks_proxy_is_rejected_before_the_session_starts`（stderr 变成「密钥未设置」，说明校验顺序也被这条判据钉住了） |
| M3 | proxy 顶掉注入的 transport | `if transport is None and self._proxy is not None:` 改成 `if self._proxy is not None:` | **杀死 1 条**：`test_an_injected_transport_beats_the_proxy` |

## 存活与不可构造

- **M1 的存活是本轮最有价值的发现**：原判据的名字像在守 `trust_env`，实际守的是「`NO_PROXY` 里的 `[::1]` 不会让 httpx 在构造客户端时崩」。这条判据本身有效（它守 ADR-0006 的具体症状），但不能替代「环境代理不得生效」。两条判据都要在。
- **「proxy 写进 `session/start`」不可构造**：`SessionSettings` 没有 `proxy` 字段，代理 URL 在装配期直接交给 provider，payload 拿不到它。这是结构性保证，不是判据保证——契约里已如实写明。

## 还原

三条都用 Edit 反向改回；`git diff --stat src/` 为空，相关子集 `10 passed`，确认回到基线。新增的那条判据留在代码里（它杀死了一个真实变异）。
