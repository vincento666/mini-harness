# Spec Delta

## MODIFIED Requirements

### Requirement: Provider 失败是回合终止结果
当 Provider 无法产出合法回复时，系统 SHALL 写一条 `error/model` 记录（含 `code`）、写 `turn/end`（`stop_reason: PROVIDER_ERROR`）、写 `session/end`，并以退出码 1 结束；MUST NOT 抛出未捕获异常打断进程。`code` 取值：`PROVIDER_EXHAUSTED`、`PROVIDER_SCHEMA_INVALID`、`PROVIDER_HTTP_STATUS`、`PROVIDER_TIMEOUT`、`PROVIDER_TRANSPORT`、`PROVIDER_ABORTED`。前两个来自 mock 路径，后四个来自真实 provider 路径（HTTP 状态码不可接受且重试后仍失败 / 请求超时 / 连接层失败 / 取消信号已置位）。`PROVIDER_ABORTED` 与既有的取消路径不冲突：内核置位取消时走的仍是 `error/abort` 与退出码 5，这条只在 provider 侧兜住「信号已置位却仍被调用」。

#### Scenario: fixture 条目耗尽
- **WHEN** 需要的回合数超过 fixture 里的回复条目数
- **THEN** 日志写 `error/model`（`code: PROVIDER_EXHAUSTED`）与 `session/end`，退出码为 1

#### Scenario: HTTP 状态码不可接受
- **WHEN** 真实 provider 的请求重试一次后仍收到 5xx
- **THEN** 日志写 `error/model`（`code: PROVIDER_HTTP_STATUS`）、`turn/end`（`stop_reason: PROVIDER_ERROR`）与 `session/end`，退出码为 1

#### Scenario: 请求超时
- **WHEN** 真实 provider 的请求超时
- **THEN** 日志写 `error/model`（`code: PROVIDER_TIMEOUT`）与 `session/end`，退出码为 1，进程没有未捕获异常

#### Scenario: 连接层失败
- **WHEN** 真实 provider 的请求无法建立连接（端点没在监听）
- **THEN** 日志写 `error/model`（`code: PROVIDER_TRANSPORT`）与 `session/end`，退出码为 1，且没有 `model/retry`
