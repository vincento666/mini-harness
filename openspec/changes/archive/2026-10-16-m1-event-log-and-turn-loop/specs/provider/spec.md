# Spec Delta

## Purpose

定义模型层的对外契约：回合循环只依赖一个 Provider 方法，M1 用 JSON fixture 序列驱动的 mock Provider 提供可预期的回复，真实实现之后必须共用同一契约。

## ADDED Requirements

### Requirement: Provider 只有一个方法
系统 SHALL 通过唯一方法 `generate(messages, tools, signal)` 请求模型，返回 `AssistantTurn{content, tool_calls, usage, finish_reason}`；`signal` SHALL 用于传递取消。回合循环 MUST NOT 依赖具体 Provider 实现或调用其它方法。

#### Scenario: 循环只经由 generate
- **WHEN** 任意 mock 场景跑完
- **THEN** 循环对 Provider 的全部调用都是 `generate`，参数只有 messages、tools、signal

### Requirement: mock Provider 按 fixture 序列回复
系统 SHALL 支持由 JSON fixture 文件驱动的 mock Provider：fixture 是一个有序回复序列，第 i 次 `generate` 返回第 i 条条目，条目可声明 `content`、`tool_calls`、`usage`、`finish_reason`。

#### Scenario: 逐条回放 fixture
- **WHEN** fixture 含 3 条回复且 run 跑了 3 个回合
- **THEN** 三条 `model/response` 的 `content` 与 fixture 条目逐一对应

#### Scenario: fixture 声明工具调用
- **WHEN** 某条 fixture 条目含非空 `tool_calls`
- **THEN** 对应的 `model/response` 记录同样的工具调用，且该回合产生 `tool/call` 与 `tool/result`

### Requirement: fixture 不合法是参数错误
系统 SHALL 在 session 开始之前校验 `--fixture` 指向的文件存在、是合法 JSON、且是每条都符合 `AssistantTurn` 形状的数组；不合法 SHALL 以退出码 2 结束，stderr 含 `FIXTURE_INVALID` 与文件路径，且 MUST NOT 创建 session 日志。

#### Scenario: fixture 不是 JSON 数组
- **WHEN** `--fixture` 指向一个内容为 `{}` 的文件
- **THEN** 退出码为 2，stderr 含 `FIXTURE_INVALID`，且没有 session 日志

### Requirement: Provider 返回不合法是结果不是异常
系统 SHALL 校验 Provider 返回值符合 `AssistantTurn`；不符合时 SHALL 写 `error/model`（`code: PROVIDER_SCHEMA_INVALID`）、按 `PROVIDER_ERROR` 结束回合，并以退出码 1 结束 run。

#### Scenario: 返回缺少 finish_reason
- **WHEN** Provider 返回一个缺少 `finish_reason` 的对象
- **THEN** 日志写 `error/model`（`code: PROVIDER_SCHEMA_INVALID`），退出码为 1，进程没有未捕获异常

### Requirement: M1 只内置 mock Provider
系统 SHALL 在 M1 只接受 `--provider mock`（默认值）；其它取值 SHALL 以退出码 2 结束且 stderr 含 `UNKNOWN_PROVIDER`。真实模型调用、`parallel_tool_calls` 与 429/5xx 重试属后续里程碑，M1 MUST NOT 发起任何网络请求。

#### Scenario: 指定未实现的 provider
- **WHEN** 执行 `minihns run -p "x" --provider deepseek`
- **THEN** 退出码为 2，stderr 含 `UNKNOWN_PROVIDER`，且没有 session 日志
