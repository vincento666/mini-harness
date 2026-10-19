# Spec Delta

## MODIFIED Requirements

### Requirement: 超时、连接失败与取消是失败结果
系统 SHALL 在请求超时、连接层失败或取消信号已置位时停止请求。模型请求的超时 SHALL 是 120 秒（决策 15 锁定的数值；实现常量，MUST NOT 有命令行开关）。超时 SHALL 塌成 `error/model`（`code: PROVIDER_TIMEOUT`）；连接层失败（无法建立请求，例如端点没在监听）SHALL 塌成 `error/model`（`code: PROVIDER_TRANSPORT`）且 MUST NOT 重试；取消信号已置位时 MUST NOT 再发出新的请求，此时 SHALL 返回 `code: PROVIDER_ABORTED` 的失败结果而不是异常。

#### Scenario: 超时不抛异常
- **WHEN** 请求超时
- **THEN** 日志写 `error/model`（`code: PROVIDER_TIMEOUT`）与 `turn/end`（`stop_reason: PROVIDER_ERROR`），退出码为 1，进程没有未捕获异常

#### Scenario: 端点没在监听
- **WHEN** 请求无法建立连接
- **THEN** 日志写 `error/model`（`code: PROVIDER_TRANSPORT`），退出码为 1，且没有 `model/retry`

#### Scenario: 取消之后不再请求
- **WHEN** 取消信号在某个回合被置位
- **THEN** 该 session 之后没有任何新的模型请求发出
- **AND** `generate` 返回 `code: PROVIDER_ABORTED` 的失败结果（M3 的取消落在派发段，`generate` 在它之前，因此内核仍没有路径在 `generate` 期间置位该信号；这条只在 provider 侧兜住）

#### Scenario: 超时数值是 120 秒且没有开关
- **WHEN** 检查 provider 的超时配置与 CLI 的参数表
- **THEN** 模型请求的超时是 120 秒，且 `minihns run` 没有任何改变它的参数
