# M4 变异测试轮（task 8.2）

基线：168 passed / 1 skipped，TOTAL 96%（931 语句 / 35 未覆盖）。做法：一处改坏 → 跑全量 `pytest -q`（不带覆盖率记账，约 36 秒）→ 记下变红的测试 → `git checkout -- <被改文件>` 还原；还原前先看 `git status --short`，别把本轮未提交的测试文件一起回滚。

刻意没跑的变异：语义等价的改法（比如把 `ensure_ascii=False` 改成默认——测试数据里没有非 ASCII 时它不会改变可观察行为），那是 dud mutant。

| 编号 | 变异（改法） | 结果 |
|---|---|---|
| A1 | 429 不重试：`status == 429 or status >= 500` → `status >= 500` | 杀：`test_a_429_then_200_retries_once_and_writes_one_model_retry` |
| A2 | 4xx 也重试：同上 → `status >= 400` | 杀 2 条：`test_a_400_is_not_retried`、`test_an_unset_key_env_still_sends_the_request`（401 被重试成两次请求） |
| A3 | 重试编号写死成 2：`ProviderAttempt(attempt=1, …)` → `attempt=2` | 杀：429 那条（断言 `attempt == 1`） |
| B1 | `model/retry` 根本不写：`for attempt in generated.attempts` → `for attempt in []` | 杀 2 条：429 那条、`test_two_500s_write_one_model_retry_then_error_model` |
| B2 | 重试 payload 的 `attempt` 写成 status | 杀：429 那条 |
| B3 | 重试 payload 的 `status` 写死 0 | 杀 2 条：429 那条、两次 500 那条 |
| C1 | 工具面不带 schema：`parameters=tool.args_model.model_json_schema()` → `parameters={}` | 杀：`test_the_parameter_schema_a_model_sees_comes_from_the_dispatch_side_model`。seam ⑤ 的桩自己构造 `ToolSpec`，不受这条影响——seam 分离在这里是对的 |
| C2 | 上线时丢参数：`"parameters": tool.parameters,` → `"parameters": {},` | 杀：`test_the_request_body_carries_model_messages_and_tools_with_schemas` |
| D1 | 密钥根本不读环境变量：`api_key=os.environ.get(args.api_key_env)` → `api_key=None` | 杀：`test_the_key_reaches_the_request_header_and_nowhere_else` |
| D2 | 鉴权头不带 `Bearer ` 前缀 | 杀 2 条：上面那条 + `test_the_authorization_header_is_present_only_when_a_key_is_given` |
| D3 | 密钥值漏进 payload：`api_key_env=args.api_key_env …` → `os.environ.get(args.api_key_env) …` | 杀 2 条：`test_the_key_reaches_the_request_header_and_nowhere_else`（断言日志里搜不到值）、`test_openai_run_records_base_url_model_and_the_key_variable_name` |
| E1 | 超时塌成错误的 code：`code="PROVIDER_TIMEOUT"` → `"PROVIDER_TRANSPORT"` | 杀：`test_a_timeout_is_a_provider_timeout_result` |
| E2 | 连接层捕获收窄：`except httpx.HTTPError` → `except httpx.ConnectError` | **第一轮存活**，补判据后被杀（见下） |
| E3 | 取消信号不查：`if signal.is_set():` → `if False:` | 杀：`test_a_set_cancel_signal_sends_no_request`（注入的 HTTP 层看见了请求） |
| E4 | 恢复 `trust_env=True` | 杀 3 条 CLI 判据——本机 `NO_PROXY` 带 `[::1]`，httpx 在构造客户端时就抛 `InvalidURL`，三条 openai 黑盒全红 |
| F1 | provider 词表里放进 `claude` | 杀：`test_unknown_provider_is_exit_2_and_creates_no_log` |
| F2 | `--provider openai` 带 fixture 不拦：`if fixture is not None:` → `if False:` | 杀：`test_openai_with_a_fixture_is_an_argument_error` |
| F3 | openai 的端点不进 payload：`if settings.provider_name == "openai":` → `if False:` | 杀 2 条：6.4 与 6.5 那两条 |

## 存活的那一条与补的判据

**E2 第一轮存活**：`PROVIDER_TRANSPORT` 这条捕获没有任何判据经过它——覆盖率也印证，当时 `provider/openai_compat.py` 的 85–86 行（`except httpx.HTTPError` 与它的 return）是未覆盖行。补三条判据：

- seam ⑤ `test_a_dead_endpoint_is_a_transport_result`：注入的 HTTP 层抛 `ConnectError` → `ProviderFailure(code="PROVIDER_TRANSPORT")`。**单靠它杀不死 E2**——`ConnectError` 仍在收窄后的捕获里。
- seam ⑤ `test_a_transport_failure_that_is_not_a_connect_error_is_still_a_result`：抛 `ReadError` → 同样是 `PROVIDER_TRANSPORT`。**这条才是杀 E2 的**。
- seam ⑥ `test_a_dead_endpoint_collapses_into_a_transport_result`：真子进程打 `http://127.0.0.1:9/v1`（没人监听）→ 退出码 1、stderr 含 `PROVIDER_TRANSPORT`、没有 `Traceback`、日志里 `error/model` 的 `code` 对、没有 `model/retry`、末条是 `session/end`。它钉的是 turn-loop delta 里「连接层失败」那条 scenario 的日志与退出码那一半，seam ⑤ 的两条钉不到。

重跑 E2：1 条变红（`ReadError` 那条）✓。补完 `openai_compat.py` 从 87% 到 89%。

## 结论

18 条变异：第一轮 17 条被杀，1 条（E2）存活并已补判据、重跑确认被杀。判据「每个变异都被至少一条测试杀死」达成。
