# provider Specification

## Purpose

定义模型层的对外契约：回合循环只依赖一个 Provider 方法，M1 用 JSON fixture 序列驱动的 mock Provider 提供可预期的回复，真实实现之后必须共用同一契约。

## Requirements

### Requirement: Provider 只有一个方法
系统 SHALL 通过唯一方法 `generate(messages, tools, signal)` 请求模型，返回 `AssistantTurn{content, tool_calls, usage, finish_reason}`；`signal` SHALL 用于传递取消。回合循环 MUST NOT 依赖具体 Provider 实现或调用其它方法。

#### Scenario: 循环只经由 generate
- **WHEN** 任意 mock 场景跑完
- **THEN** 循环对 Provider 的全部调用都是 `generate`，参数只有 messages、tools、signal

### Requirement: mock Provider 按 fixture 序列回复
系统 SHALL 支持由 JSON fixture 文件驱动的 mock Provider：fixture 是一个有序回复序列，第 i 次 `generate` 返回第 i 条条目，条目可声明 `content`、`tool_calls`、`usage`、`finish_reason`。`mock` 路径 MUST NOT 发起网络请求。

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
系统 SHALL 校验 Provider 返回值符合 `AssistantTurn`；不符合时 SHALL 写 `error/model`（`code: PROVIDER_SCHEMA_INVALID`）、按 `PROVIDER_ERROR` 结束回合，并以退出码 1 结束 run。真实 provider 收到**状态码合法但响应体形状不合法**的回复时，SHALL 走同一条路径。

#### Scenario: 返回缺少 finish_reason
- **WHEN** Provider 返回一个缺少 `finish_reason` 的对象
- **THEN** 日志写 `error/model`（`code: PROVIDER_SCHEMA_INVALID`），退出码为 1，进程没有未捕获异常

#### Scenario: 200 的响应体不是合法 chat completion
- **WHEN** openai provider 收到 200 但响应体缺少 `choices`
- **THEN** 日志写 `error/model`（`code: PROVIDER_SCHEMA_INVALID`），退出码为 1，且没有重试记录

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

### Requirement: 上下文超限的回复是溢出结果
当真实 provider 返回 4xx（429 除外，它走既有的重试）且响应 JSON 里的错误对象指向「提示词装不进上下文」时，系统 SHALL 产出 `code: PROVIDER_CONTEXT_OVERFLOW` 的失败结果：MUST NOT 为它重试（它不是 429 也不是 5xx），MUST NOT 塌成 `PROVIDER_HTTP_STATUS`。指向它有两种形状：错误对象的 `code` 为 `context_length_exceeded`；或错误对象的 `message` 含固定短语表里的某一条（大小写不敏感）。两者都不指向时仍按既有的「状态码不可接受」路径走；塌成溢出只发生在不可重试的 4xx，5xx 与 429 的正文里恰好出现短语表里的话时 MUST NOT 塌成溢出。

#### Scenario: 上下文超限的 400 不重试
- **WHEN** 假端点对一次请求返回 400 且 `error.code` 为 `context_length_exceeded`
- **THEN** `generate` 返回 `code: PROVIDER_CONTEXT_OVERFLOW` 的失败结果，且没有任何 `model/retry` 记录

#### Scenario: 413 报同一个 code 也塌成溢出
- **WHEN** 假端点返回 413 且 `error.code` 为 `context_length_exceeded`
- **THEN** `generate` 返回 `code: PROVIDER_CONTEXT_OVERFLOW` 的失败结果，且没有任何 `model/retry` 记录

#### Scenario: 正文说装不下时也塌成溢出
- **WHEN** 假端点返回 400、错误对象没有 `code`，但 `message` 是 `prompt (222233 tokens) leaves no room to answer in the context (196608); requests are never truncated`
- **THEN** `generate` 返回 `code: PROVIDER_CONTEXT_OVERFLOW` 的失败结果，且没有任何 `model/retry` 记录

#### Scenario: 其它 400 仍走既有路径
- **WHEN** 假端点返回 400 且 `error.code` 是别的值（例如 `invalid_request_error`）、`error.message` 不含固定短语表里的任何一条
- **THEN** `generate` 返回 `code: PROVIDER_HTTP_STATUS` 的失败结果

#### Scenario: 500 的正文里恰好有短语表里的话仍走既有路径
- **WHEN** 假端点两次都返回 500 且 `error.message` 含 `context length exceeded`
- **THEN** `generate` 返回 `code: PROVIDER_HTTP_STATUS` 的失败结果，且恰有一条重试

#### Scenario: 429 的正文里恰好有短语表里的话仍走既有路径
- **WHEN** 假端点两次都返回 429 且 `error.message` 含 `prompt is too long`
- **THEN** `generate` 返回 `code: PROVIDER_HTTP_STATUS` 的失败结果，且恰有一条重试

### Requirement: 失败结果带上提供方说的那句话
当一次模型请求得到 4xx 或 5xx 的回复时，失败结果的 `detail` SHALL 同时含状态码与响应正文的有界摘要：单行（换行压成空格）、整条至多 200 字符、取自响应 JSON 里错误对象的 `message`（取不到时取正文本身），正文为空或读不出时只有状态码。该摘要 SHALL 写进 `error/model` 的 payload，也 SHALL NOT 改变失败结果的 `code`。

#### Scenario: 正文里那句话进 detail
- **WHEN** 假端点返回 400 且响应 JSON 是 `{"error": {"type": "invalid_request_error", "message": "prompt leaves no room to answer"}}`
- **THEN** 失败结果的 `detail` 含 `HTTP 400` 与 `prompt leaves no room to answer`

#### Scenario: 正文不是 JSON 时取正文本身
- **WHEN** 假端点返回 502 且正文是一段以 `<` 开头的 HTML
- **THEN** 失败结果的 `detail` 含 `HTTP 502` 与该正文的开头，且不超过 200 字符

#### Scenario: 空正文不制造空话
- **WHEN** 假端点返回 400 且正文为空
- **THEN** 失败结果的 `detail` 就是 `HTTP 400`
