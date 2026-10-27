# Spec Delta

## MODIFIED Requirements

### Requirement: Provider 只有一个方法

系统 SHALL 通过唯一方法 `generate(messages, tools, signal, on_delta=None)` 请求模型，返回 `AssistantTurn{content, tool_calls, usage, finish_reason}`；`signal` SHALL 用于传递取消。`on_delta` 是可选的增量回调；没有它时行为与不流式逐点相同。回合循环 MUST NOT 依赖具体 Provider 实现或调用其它方法。

#### Scenario: 循环只经由 generate
- **WHEN** 任意 mock 场景跑完
- **THEN** 循环对 Provider 的全部调用都是 `generate`，没有额外方法

#### Scenario: 没有 delta sink 时行为不变
- **WHEN** 同一个 fixture 分别带与不带 `on_delta` 跑
- **THEN** 两次的 `model/response`、`tool/call`、`tool/result` 序列逐点相同，且不带 sink 时没有任何 `model/delta` 帧

### Requirement: mock Provider 按 fixture 序列回复

系统 SHALL 支持由 JSON fixture 文件驱动的 mock Provider：fixture 是一个有序回复序列，第 i 次 `generate` 返回第 i 条条目，条目可声明 `content`、`tool_calls`、`usage`、`finish_reason`，并可声明可选的 `deltas`（字符串数组）。给了 `deltas` 且调用方提供 delta sink 时，mock SHALL 依次发出这些增量、再返回最终条目；没有 `deltas` 时 mock 不制造增量。`mock` 路径 MUST NOT 发起网络请求。

#### Scenario: 逐条回放 fixture
- **WHEN** fixture 含 3 条回复且 run 跑了 3 个回合
- **THEN** 三条 `model/response` 的 `content` 与 fixture 条目逐一对应

#### Scenario: fixture 声明工具调用
- **WHEN** 某条 fixture 条目含非空 `tool_calls`
- **THEN** 对应的 `model/response` 记录同样的工具调用，且该回合产生 `tool/call` 与 `tool/result`

#### Scenario: mock 发出 fixture 的增量
- **WHEN** fixture 条目声明 `deltas: ["你", "好"]` 且调用方提供 delta sink
- **THEN** sink 依次收到 `你`、`好`，最终 `model/response.content` 是 `你好`

### Requirement: 429 与 5xx 重试一次

系统 SHALL 在收到 HTTP 429 或 5xx 时重试一次，且**只重试一次**；每次重试 SHALL 写一条 `model/retry` 记录。重试后仍失败 SHALL 塌成失败结果。4xx（429 之外）MUST NOT 重试。已经向 delta sink 发出过任何增量的请求 MUST NOT 重试：该次调用 SHALL 塌成 `PROVIDER_ERROR`，避免屏幕上出现两遍开头。

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

#### Scenario: 首 delta 之后不重试
- **WHEN** 流式响应已经发出至少一个 delta 后连接中断
- **THEN** 不写 `model/retry`，不重发请求，该回合以 `PROVIDER_ERROR` 收尾

### Requirement: OpenAI 兼容 provider 按 chat completions 形状请求

系统 SHALL 提供 `openai` provider：向 `<base-url>/chat/completions` 发 POST，请求体含 `model`、`messages`、`tools`（每个工具带参数 JSON Schema）；默认是非流式，调用方给 delta sink 时 SHALL 使用流式请求。成功时 SHALL 把回复转成 `AssistantTurn{content, tool_calls, usage, finish_reason}`。它 MUST 实现与 mock 相同的 `generate` 契约，回合循环 MUST NOT 因 provider 不同而改变行为。

#### Scenario: 两种 provider 走同一入口
- **WHEN** 同一个场景分别用 mock fixture 与 openai provider（对着注入的假 HTTP 层）跑
- **THEN** 两条日志的 `model/response`、`tool/call`、`tool/result` 序列一致，且回合循环没有 provider 分支

#### Scenario: 一轮多个工具调用
- **WHEN** 响应的 `message.tool_calls` 含两个调用
- **THEN** 该回合产生两条 `tool/call` 与两条 `tool/result`，`turn/end` 的 `stop_reason` 为 `TOOL_CALLS`

## ADDED Requirements

### Requirement: OpenAI 兼容 provider 解析流式 SSE

给 delta sink 时，适配器 SHALL 发 `stream: true` 请求，解析 `data: {...}` 行直到 `[DONE]`；每个 `choices[].delta.content` 非空片段 SHALL 作为一个增量交给 sink。它 MAY 带 `stream_options: {"include_usage": true}`；端点不支持时 SHALL 退回不带它，usage 允许缺。MUST NOT 把增量写进日志。

#### Scenario: 正文增量拼接等于最终 content
- **WHEN** 假端点依次发 `你`、`好`，然后 `[DONE]`
- **THEN** sink 收到两个增量，最终 `model/response.content` 是 `你好`，日志里没有逐字记录

#### Scenario: usage 缺失
- **WHEN** 流式响应没有 usage 块
- **THEN** `AssistantTurn.usage` 是零值，run 正常收尾，不因缺 usage 失败

### Requirement: 流式工具调用按 index 拼装

流式响应里的 `tool_calls` SHALL 按 `index` 聚合 `id`、`function.name` 与 `function.arguments`，拼成与非流式相同的 `ToolCall` 列表；拼装中的参数片段 MUST NOT 作为 delta 正文交给 sink。

#### Scenario: 两个工具调用流式拼装
- **WHEN** 流式响应分片给出两个 `tool_calls` 的 id、name 与 arguments
- **THEN** 最终 `AssistantTurn.tool_calls` 是两条完整调用，`tool/call` 与 `tool/result` 各两条

### Requirement: 流式读取中断是失败结果

流式响应在 `[DONE]` 之前断开（连接错误、超时、取消）SHALL 塌成失败结果，而不是抛出未捕获异常；已经交给 sink 的增量不补、不改写日志。取消 SHALL 照常由回合循环写 `error/abort` / `turn/end(ABORTED)`。

#### Scenario: 流中断
- **WHEN** 假端点在第一个 delta 后关闭连接
- **THEN** `generate` 返回 `PROVIDER_ERROR` 结果，`model/response` 不出现，日志里没有半条 `model/response`

#### Scenario: 流式调用被取消
- **WHEN** 流式读取期间取消事件置位
- **THEN** 适配器停止读流，回合以 `ABORTED` 收尾，不写 `model/response`
