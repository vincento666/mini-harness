# Spec Delta

## ADDED Requirements

### Requirement: assistant message 是有序 content blocks

`AssistantTurn` SHALL 提供 `blocks: list[Block]`，块类型至少 `reasoning` / `text` / `tool-call`；顺序 SHALL 保留模型返回顺序。`content` 与 `tool_calls` MAY 保留为 blocks 的派生投影，但 MUST NOT 成为第二真源。没有 reasoning 的 provider MUST 继续产出等价的 text/tool-call blocks，旧日志读法不变。

#### Scenario: reasoning 与 text 交错保序

- **WHEN** provider 返回 reasoning → tool-call → reasoning → text
- **THEN** `model/response.blocks` 按同一顺序保存四块

#### Scenario: 旧 provider 只有正文

- **WHEN** provider 只返回 `content="你好"`
- **THEN** `blocks` 是单个 text 块，`content` 投影仍是 `你好`

### Requirement: reasoning 只以 ephemeral delta 实时输出

系统 SHALL 提供 `reasoning/delta` SSE 事件：`turn_id`、`index`、`text`；MUST NOT 写日志、MUST NOT 带 durable `id`、MUST NOT 参与 `Last-Event-ID` 游标。正文 `model/delta` 保持不变；reasoning MUST NOT 混进 `model/delta`。

#### Scenario: 思考与正文分开

- **WHEN** provider 先发 reasoning delta、再发正文 delta
- **THEN** SSE 依次出现 `reasoning/delta` 与 `model/delta`，两者都无 durable id

#### Scenario: delta 不进日志

- **WHEN** 一次带 reasoning 的回合结束
- **THEN** 日志里没有 `reasoning/delta` 记录，只有最终 `model/response`

### Requirement: 一次调用仍只有一条 durable response

一次成功 attempt SHALL 只追加一条 `model/response`，payload 带 `blocks`、`usage`、`finish_reason`；完整 reasoning 文本 SHALL 保存在 blocks 里，不按 delta 逐条落账。失败/取消 MUST NOT 写半条 `model/response`。

#### Scenario: 完整 reasoning 可重放

- **WHEN** 一次响应含 reasoning 与 text
- **THEN** 日志只有一条 `model/response`，`blocks` 里能读出完整 reasoning

#### Scenario: 取消不写半条

- **WHEN** 流式中途取消
- **THEN** 没有 `model/response`，按现有 ABORTED 收尾

### Requirement: Provider sink 分流

Provider SHALL 接受独立的 `ReasoningSink`；正文 `on_delta` 只收 `text` 块，reasoning 只走 `ReasoningSink`。适配器 MUST NOT 把 reasoning 拼进正文，也不得把正文拼进 reasoning。

#### Scenario: 正文 sink 不含 reasoning

- **WHEN** 适配器收到 reasoning 与正文片段
- **THEN** 正文 sink 只收到正文片段，reasoning sink 只收到 reasoning 片段

### Requirement: 思考强度是请求配置

系统 SHALL 支持 `reasoning_effort = off|low|high|max`；不支持的档位 SHALL 在发起网络 I/O 之前失败，错误码 `UNSUPPORTED_REASONING_EFFORT`。`off` MUST 把 reasoning 关掉；其余档位按 provider 协议映射。

#### Scenario: 不支持的档位在 I/O 前失败

- **WHEN** 配置 `reasoning_effort=ultra`
- **THEN** 不发出 HTTP 请求，session 以参数错误结束

#### Scenario: off 不产生 reasoning

- **WHEN** `reasoning_effort=off`
- **THEN** 响应没有 reasoning 块或 reasoning delta

### Requirement: reasoning tokens 是 output 的子集

`usage.reasoning_tokens` SHALL 是 `output_tokens` 的子集；成本/计量 MUST NOT 把 reasoning tokens 再加一遍。回传的 reasoning 文本进入后续上下文时，按普通文本计入上下文预算。

#### Scenario: 不重复计

- **WHEN** usage 为 `output_tokens=50`、`reasoning_tokens=30`
- **THEN** 计量总额按 50 计，不按 80

#### Scenario: 回传计入上下文

- **WHEN** 后续请求带上一轮的 reasoning 块
- **THEN** 预算估算把它当普通文本计入

### Requirement: fold 与 replay 保序

`fold` SHALL 从 `model/response.blocks` 重建有序 `Message`；旧日志没有 blocks 时 SHALL 退化为现有 content/tool_calls 行为，逐点重放不变。Provider 历史回传 MUST 保留 reasoning/text/tool-call 的顺序；不支持块级回传的适配器 SHALL 显式降级并记录，MUST NOT 把 reasoning 当普通 content 静默塞回。

#### Scenario: 两种日志都逐点重放

- **WHEN** 旧日志（无 blocks）与新日志（有 reasoning blocks）各自 replay
- **THEN** 两次 `context/assembled` 与各自原 run 逐点相等

#### Scenario: 无 reasoning 模型行为不变

- **WHEN** provider 不返回 reasoning
- **THEN** 日志、fold、SSE 除新空字段外与今天逐点相同
