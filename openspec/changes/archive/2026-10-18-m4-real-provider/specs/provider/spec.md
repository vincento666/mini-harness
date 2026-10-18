# Spec Delta

## ADDED Requirements

### Requirement: OpenAI 兼容 provider 按 chat completions 形状请求
系统 SHALL 提供 `openai` provider：向 `<base-url>/chat/completions` 发一次**非流式** POST，请求体含 `model`、`messages`、`tools`（每个工具带参数 JSON Schema）；成功时 SHALL 把回复转成 `AssistantTurn{content, tool_calls, usage, finish_reason}`。它 MUST 实现与 mock 相同的 `generate` 契约，回合循环 MUST NOT 因 provider 不同而改变行为。

#### Scenario: 两种 provider 走同一入口
- **WHEN** 同一个场景分别用 mock fixture 与 openai provider（对着注入的假 HTTP 层）跑
- **THEN** 两条日志的 `model/response`、`tool/call`、`tool/result` 序列一致，且回合循环没有 provider 分支

#### Scenario: 一轮多个工具调用
- **WHEN** 响应的 `message.tool_calls` 含两个调用
- **THEN** 该回合产生两条 `tool/call` 与两条 `tool/result`，`turn/end` 的 `stop_reason` 为 `TOOL_CALLS`

### Requirement: 工具面带参数 JSON Schema 且由注册表派生
系统 SHALL 在送给模型的工具面里为每个工具带上参数 JSON Schema。该 schema MUST 由该工具在注册表里的参数模型派生，MUST NOT 是手搓的第二份描述。

#### Scenario: 模型看到的参数形状与派发侧同源
- **WHEN** 一次 run 装配工具面并送进 provider
- **THEN** 每个工具的参数 schema 的字段名与必填项与该工具派发侧参数模型的 JSON Schema 一致

### Requirement: 适配器不继承代理环境变量
系统 SHALL 以不读取环境的方式发出请求：`HTTP_PROXY`、`HTTPS_PROXY`、`NO_PROXY`、netrc MUST NOT 影响 provider 的请求。代价（处在公司代理之后的用户无法经代理访问远端端点）记进 `docs/adr/`。

#### Scenario: 主机的 NO_PROXY 里带方括号 IPv6
- **WHEN** 进程环境里 `NO_PROXY` 含 `[::1]`，执行一次 `--provider openai` 的 run
- **THEN** 请求照常发出，进程没有未捕获异常

### Requirement: 429 与 5xx 重试一次
系统 SHALL 在收到 HTTP 429 或 5xx 时重试一次，且**只重试一次**；每次重试 SHALL 写一条 `model/retry` 记录。重试后仍失败 SHALL 塌成失败结果。4xx（429 之外）MUST NOT 重试。

#### Scenario: 429 之后第二次成功
- **WHEN** 第一次请求返回 429、第二次返回 200 且响应合法
- **THEN** 日志含一条 `model/retry`，run 以退出码 0 结束

#### Scenario: 两次都 500
- **WHEN** 两次请求都返回 500
- **THEN** 日志含一条 `model/retry` 与一条 `error/model`（`code: PROVIDER_HTTP_STATUS`），`turn/end` 的 `stop_reason` 为 `PROVIDER_ERROR`，退出码为 1

#### Scenario: 400 不重试
- **WHEN** 请求返回 400
- **THEN** 日志里没有 `model/retry`，`error/model` 的 `code` 为 `PROVIDER_HTTP_STATUS`，退出码为 1

#### Scenario: 缺密钥的 401 不重试
- **WHEN** 密钥环境变量未设因而请求不带鉴权头，服务端返回 401
- **THEN** 日志里没有 `model/retry`，`error/model` 的 `code` 为 `PROVIDER_HTTP_STATUS`，退出码为 1

### Requirement: 超时、连接失败与取消是失败结果
系统 SHALL 在请求超时、连接层失败或取消信号已置位时停止请求：超时 SHALL 塌成 `error/model`（`code: PROVIDER_TIMEOUT`）；连接层失败（无法建立请求，例如端点没在监听）SHALL 塌成 `error/model`（`code: PROVIDER_TRANSPORT`）且 MUST NOT 重试；取消信号已置位时 MUST NOT 再发出新的请求，此时 SHALL 返回 `code: PROVIDER_ABORTED` 的失败结果而不是异常。

#### Scenario: 超时不抛异常
- **WHEN** 请求超时
- **THEN** 日志写 `error/model`（`code: PROVIDER_TIMEOUT`）与 `turn/end`（`stop_reason: PROVIDER_ERROR`），退出码为 1，进程没有未捕获异常

#### Scenario: 端点没在监听
- **WHEN** 请求无法建立连接
- **THEN** 日志写 `error/model`（`code: PROVIDER_TRANSPORT`），退出码为 1，且没有 `model/retry`

#### Scenario: 取消之后不再请求
- **WHEN** 取消信号在某个回合被置位
- **THEN** 该 session 之后没有任何新的模型请求发出
- **AND** `generate` 返回 `code: PROVIDER_ABORTED` 的失败结果（M4 里内核没有任何路径置位该信号，这条只在 provider 侧兜住）

## MODIFIED Requirements

### Requirement: Provider 返回不合法是结果不是异常
系统 SHALL 校验 Provider 返回值符合 `AssistantTurn`；不符合时 SHALL 写 `error/model`（`code: PROVIDER_SCHEMA_INVALID`）、按 `PROVIDER_ERROR` 结束回合，并以退出码 1 结束 run。真实 provider 收到**状态码合法但响应体形状不合法**的回复时，SHALL 走同一条路径。

#### Scenario: 返回缺少 finish_reason
- **WHEN** Provider 返回一个缺少 `finish_reason` 的对象
- **THEN** 日志写 `error/model`（`code: PROVIDER_SCHEMA_INVALID`），退出码为 1，进程没有未捕获异常

#### Scenario: 200 的响应体不是合法 chat completion
- **WHEN** openai provider 收到 200 但响应体缺少 `choices`
- **THEN** 日志写 `error/model`（`code: PROVIDER_SCHEMA_INVALID`），退出码为 1，且没有重试记录

## REMOVED Requirements

### Requirement: M1 只内置 mock Provider
**Reason**: M4 引入真实 provider，「只接受 `--provider mock`」这条限制被 provider 选择规则取代（见 `specs/cli/spec.md`）。
**Migration**: 未知 provider 取值仍是退出码 2 且 stderr 含 `UNKNOWN_PROVIDER`；`--provider` 不写时默认仍是 `mock`，既有 mock 判据不变。MUST NOT 发起网络请求这条约束从「M1 全程」收窄为「mock provider 路径 MUST NOT 发起网络请求」。
